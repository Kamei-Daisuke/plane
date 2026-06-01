#!/usr/bin/env python3
"""Bulk re-convert: for every page whose Confluence body contains an
info/note/tip/warning macro, re-generate Plane TipTap HTML with those
macros rendered as callout-component divs in their original position.

v2: Properly handle nested macros (e.g. info containing a code macro)
via a balanced scanner instead of non-greedy regex.
"""
import base64
import html as html_mod
import io
import json
import os
import re
import sys
import unicodedata
import uuid as uuidlib
from collections import defaultdict
from datetime import datetime, timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.production")
sys.path.insert(0, "/code")

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402
from django.utils import timezone as dj_timezone  # noqa: E402
from django_redis import get_redis_connection  # noqa: E402

from plane.db.models import Page  # noqa: E402


CONF = os.environ.get("CONFLUENCE_BODIES", "/tmp/conf_bodies_latest.tsv")
PLANE_BASE = os.environ.get("PLANE_BASE", "https://plane.keis-software.com")
WORKSPACE_SLUG = os.environ.get("WORKSPACE_SLUG", "keis")
JIRA_BASE = os.environ.get("JIRA_BASE", "https://jira.aruhi-corp.co.jp")

P_CLASS = "editor-paragraph-block"
H_CLASS = "editor-heading-block"

# Accept both `<ac:structured-macro>` (modern) and `<ac:macro>` (legacy; seen on
# older Confluence pages, e.g. view-file embeds).
STRUCTURED_OPEN_RE = re.compile(r'<ac:(?:structured-)?macro\b([^>]*)>')
STRUCTURED_OPEN_OR_CLOSE = re.compile(r'<(/?)ac:(?:structured-)?macro\b[^>]*/?>')
CALLOUT_MACRO_NAMES = {"info", "note", "tip", "warning"}
CODE_MACRO_NAMES = {"code", "noformat"}
ICON_BY_TYPE = {"info": "128161", "note": "128221", "tip": "128161", "warning": "9888"}

# Populated by build_title_maps() at main()
TITLE_TO_PLANE_URL: dict = {}
# Populated by build_title_maps() — plane_page_id → Plane page name (used for link
# text when an author pasted a bare URL and we want a human-readable label).
PLANE_ID_TO_NAME: dict = {}
# Populated by build_title_maps() — plane_page_id → full URL.
PLANE_ID_TO_URL: dict = {}
# Populated by build_title_maps() — plane_page_id → sorted list of child page ids.
PLANE_CHILDREN: dict = {}
# Populated by build_title_maps() — uppercased project identifier ("GUDO" etc.)
# set; used to decide whether a Jira key like "GUDO-4" maps to a migrated Plane
# project and should be rewritten to /browse/GUDO-4/.
PLANE_PROJECT_IDENTIFIERS: set = set()
# Populated by build_title_maps() — uppercase identifier OR lower-case name → project_id
# so we can map a JQL clause like `project = "ARUHI ID"` or `project = GUDO` to a
# Plane project's issues page.
PLANE_PROJECT_LOOKUP: dict = {}
# Set by main() before each page's convert_page_body call; read by convert_macro
# to render children/pagetree macros into a real child-page list, and by
# resolve_confluence_url to rewrite /download/attachments URLs via the
# per-page asset map.
_CURRENT_PAGE_ID: str | None = None
_CURRENT_ASSET_MAP: dict | None = None
# Populated by build_cid_to_plane() at main() — for Confluence pageId → Plane URL resolution
CID_TO_PLANE_URL: dict = {}

# S3/object-storage access for embedding spreadsheet macros (excel/spreadsheets/
# viewxls) as real HTML tables. Populated by main().
_S3_CLIENT = None
_S3_BUCKET: str | None = None
_ASSET_KEY: dict = {}  # asset_id → storage key (file_assets.asset)


def resolve_confluence_url(url: str) -> str:
    """Convert a Confluence or Jira URL to the equivalent Plane URL if possible."""
    # Jira browse: jira.aruhi-corp.co.jp/browse/IDENT-N → /{slug}/browse/IDENT-N/
    jira_m = re.search(
        r"jira\.aruhi-corp\.co\.jp/browse/([A-Z][A-Z0-9_]*)-(\d+)\b",
        url,
    )
    if jira_m:
        ident = jira_m.group(1).upper()
        if ident in PLANE_PROJECT_IDENTIFIERS:
            return f"{PLANE_BASE}/{WORKSPACE_SLUG}/browse/{jira_m.group(1)}-{jira_m.group(2)}/"
        return url
    if "confluence.aruhi-corp.co.jp" not in url:
        return url
    # /download/attachments/PAGE_ID/FILENAME(?params) → Plane file_asset URL
    dl_m = re.search(
        r"confluence\.aruhi-corp\.co\.jp/download/attachments/\d+/([^?\s\"']+)",
        url,
    )
    if dl_m:
        import urllib.parse as _urlparse

        fname = norm(_urlparse.unquote(dl_m.group(1)))
        if _CURRENT_ASSET_MAP is not None:
            aid = _CURRENT_ASSET_MAP.get(fname)
            if aid:
                return f"{PLANE_BASE}/api/assets/v2/workspaces/{WORKSPACE_SLUG}/{aid}/"
        return url
    deamp = url.replace("&amp;", "&")
    # pageId=XXX pattern
    import re as _re

    m = _re.search(r"[?&]pageId=(\d+)", deamp)
    if m:
        try:
            cid = int(m.group(1))
        except ValueError:
            return url
        plane = CID_TO_PLANE_URL.get(cid)
        return plane if plane else url
    # /display/<SPACE>/<Title>
    m = _re.search(r"/display/([^/]+)/([^?#&\s]+)", deamp)
    if m:
        import urllib.parse

        space = m.group(1)
        title = urllib.parse.unquote_plus(m.group(2))
        plane = TITLE_TO_PLANE_URL.get((space, title)) or TITLE_TO_PLANE_URL.get((None, title))
        return plane if plane else url
    return url


def build_title_maps(cur):
    """Build (space, title) → Plane page URL from Confluence page map.

    Loaded from:
      - /tmp/conf_bodies_latest.tsv: CONTENTID per page (latest version)
      - CONTENT table via DB: (CONTENTID, TITLE, SPACEKEY) — but we
        don't have Confluence DB here; instead use the jsonl that
        includes space + title.
    """
    import os

    jsonl = "/tmp/confluence_pages.jsonl"
    title_to_cid = {}
    if os.path.exists(jsonl):
        with open(jsonl, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                cid = d.get("id")
                title = d.get("title")
                space = d.get("space")
                if cid and title:
                    title_to_cid[(space, title)] = int(cid)
                    title_to_cid[(None, title)] = int(cid)  # fallback w/o space
    # cid → plane page info, pid → name / URL, parent_id → [children]
    cur.execute(
        "SELECT pages.external_id, pages.id::text, pp.project_id::text, pages.name, "
        "pages.parent_id::text, pages.sort_order FROM pages "
        "LEFT JOIN project_pages pp ON pp.page_id = pages.id "
        "WHERE pages.external_source='confluence' AND pages.deleted_at IS NULL"
    )
    cid_to_plane = {}
    global PLANE_ID_TO_NAME, PLANE_ID_TO_URL, PLANE_CHILDREN
    PLANE_ID_TO_NAME = {}
    PLANE_ID_TO_URL = {}
    PLANE_CHILDREN = {}
    # Collect (parent, sort_order, pid) so we can sort children by order.
    _children_tmp: dict[str, list] = {}
    for ext, pid, proj, name, parent_id, sort_order in cur.fetchall():
        if name:
            PLANE_ID_TO_NAME[pid] = name
        if proj:
            PLANE_ID_TO_URL[pid] = f"{PLANE_BASE}/{WORKSPACE_SLUG}/projects/{proj}/pages/{pid}/"
        if parent_id and parent_id != "None":
            _children_tmp.setdefault(parent_id, []).append((sort_order or 0, name or "", pid))
        try:
            cid = int(ext)
        except (TypeError, ValueError):
            continue
        cid_to_plane[cid] = (pid, proj)
    for parent_id, rows in _children_tmp.items():
        rows.sort()
        PLANE_CHILDREN[parent_id] = [pid for _, _, pid in rows]

    # Plane project identifiers (for Jira key → /browse/ rewrite) and
    # project lookup (for JQL `project = "..."` rewrite).
    global PLANE_PROJECT_IDENTIFIERS, PLANE_PROJECT_LOOKUP
    cur.execute("SELECT id::text, identifier, name FROM projects WHERE identifier IS NOT NULL")
    PLANE_PROJECT_IDENTIFIERS = set()
    PLANE_PROJECT_LOOKUP = {}
    for proj_id, ident, pname in cur.fetchall():
        if ident:
            PLANE_PROJECT_IDENTIFIERS.add(ident.upper())
            PLANE_PROJECT_LOOKUP.setdefault(ident.upper(), proj_id)
        if pname:
            PLANE_PROJECT_LOOKUP.setdefault(pname.strip().lower(), proj_id)

    global TITLE_TO_PLANE_URL, CID_TO_PLANE_URL
    TITLE_TO_PLANE_URL = {}
    CID_TO_PLANE_URL = {}
    for (space, title), cid in title_to_cid.items():
        if cid not in cid_to_plane:
            continue
        pid, proj = cid_to_plane[cid]
        if not proj:
            continue
        url = f"{PLANE_BASE}/{WORKSPACE_SLUG}/projects/{proj}/pages/{pid}/"
        TITLE_TO_PLANE_URL[(space, title)] = url
        CID_TO_PLANE_URL[cid] = url
    return len(TITLE_TO_PLANE_URL)


def norm(s):
    return unicodedata.normalize("NFC", s) if s else s


def find_structured_macro_spans(body: str):
    """Yield (start, end, open_attrs, inner_html) for every top-level-ish
    structured-macro, correctly handling nested macros via depth counting.

    Returns matches with their full span; callers decide what to do."""
    pos = 0
    results = []
    while True:
        open_m = STRUCTURED_OPEN_RE.search(body, pos)
        if not open_m:
            break
        # Self-closing?
        if body[open_m.end() - 2:open_m.end()] == "/>":
            results.append((open_m.start(), open_m.end(), open_m.group(1), ""))
            pos = open_m.end()
            continue
        # Walk forward, counting depth
        depth = 1
        scan = open_m.end()
        end = None
        for m in STRUCTURED_OPEN_OR_CLOSE.finditer(body, scan):
            is_close = m.group(1) == "/"
            self_close = m.group(0).rstrip(">").rstrip().endswith("/")
            if is_close:
                depth -= 1
                if depth == 0:
                    end = m.end()
                    scan = m.end()
                    break
            elif not self_close:
                depth += 1
        if end is None:
            # Malformed, bail out of this opener
            pos = open_m.end()
            continue
        inner_start = open_m.end()
        # strip the actual </ac:(structured-)?macro> at the end
        close_m_iter = list(
            re.finditer(r'</ac:(?:structured-)?macro\s*>', body[inner_start:end])
        )
        if not close_m_iter:
            pos = end
            continue
        # Last close in range is the one that finalized
        inner = body[inner_start:end - len(close_m_iter[-1].group(0))]
        results.append((open_m.start(), end, open_m.group(1), inner))
        pos = end
    return results


def get_macro_name(attrs: str) -> str | None:
    m = re.search(r'ac:name="([^"]+)"', attrs)
    return m.group(1) if m else None


def make_callout_wrapper(inner_html_converted: str, macro_type: str) -> str:
    icon = ICON_BY_TYPE.get(macro_type, "128161")
    open_tag = (
        f'<div data-block-type="callout-component" data-logo-in-use="emoji" '
        f'data-emoji-unicode="{icon}" '
        f'data-emoji-url="https://cdn.jsdelivr.net/npm/emoji-datasource-apple/img/apple/64/1f4a1.png" '
        f'id="{uuidlib.uuid4()}">'
    )
    return f"{open_tag}{inner_html_converted}</div>"


def make_code_block(lang: str, code: str) -> str:
    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
    la = f' class="language-{lang}"' if lang else ""
    return f'<pre data-code-content="{encoded}"><code{la}>​</code></pre>'


def _xlsx_cell_str(v) -> str:
    """Render an openpyxl cell value as a plain table-cell string."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, datetime):
        if v.hour or v.minute or v.second:
            return v.strftime("%Y-%m-%d %H:%M")
        return v.strftime("%Y-%m-%d")
    return str(v)


def xlsx_to_table_html(aid: str) -> str | None:
    """Fetch an xlsx asset from object storage and render each sheet as a plain
    <table> (finalize_html adds colwidth afterwards). Returns None on any
    fetch/parse failure so the caller can fall back to a download link."""
    if not aid or _S3_CLIENT is None:
        return None
    key = _ASSET_KEY.get(aid)
    if not key:
        return None
    try:
        data = _S3_CLIENT.get_object(Bucket=_S3_BUCKET, Key=key)["Body"].read()
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    except Exception as e:  # noqa: BLE001
        print(f"  xlsx parse failed for {aid}: {e}", file=sys.stderr)
        return None
    tables = []
    for ws in wb.worksheets:
        # Merged cells → colspan/rowspan on the top-left cell; skip covered cells.
        covered = set()
        span = {}
        for rng in ws.merged_cells.ranges:
            span[(rng.min_row, rng.min_col)] = (
                rng.max_col - rng.min_col + 1,
                rng.max_row - rng.min_row + 1,
            )
            for rr in range(rng.min_row, rng.max_row + 1):
                for cc in range(rng.min_col, rng.max_col + 1):
                    if (rr, cc) != (rng.min_row, rng.min_col):
                        covered.add((rr, cc))
        grid = [[_xlsx_cell_str(c.value) for c in row] for row in ws.iter_rows()]
        last_row = max(
            (r for r, row in enumerate(grid) if any(v.strip() for v in row)),
            default=-1,
        )
        last_col = max(
            (c for row in grid for c, v in enumerate(row) if v.strip()),
            default=-1,
        )
        if last_row < 0 or last_col < 0:
            continue
        trs = []
        for r in range(last_row + 1):
            cells = []
            for c in range(last_col + 1):
                rr, cc = r + 1, c + 1  # openpyxl is 1-indexed
                if (rr, cc) in covered:
                    continue
                tag = "th" if r == 0 else "td"
                attrs = ""
                if (rr, cc) in span:
                    cs, rs = span[(rr, cc)]
                    if cs > 1:
                        attrs += f' colspan="{cs}"'
                    if rs > 1:
                        attrs += f' rowspan="{rs}"'
                val = grid[r][c] if c < len(grid[r]) else ""
                text = html_mod.escape(val).replace("\n", "<br>")
                cells.append(f"<{tag}{attrs}>{text}</{tag}>")
            trs.append("<tr>" + "".join(cells) + "</tr>")
        if trs:
            tables.append("<table><tbody>" + "".join(trs) + "</tbody></table>")
    wb.close()
    return "".join(tables) if tables else None


def get_param(inner: str, key: str) -> str:
    m = re.search(
        r'<ac:parameter\b[^>]*ac:name="' + re.escape(key) + r'"[^>]*>(.*?)</ac:parameter>',
        inner,
        re.DOTALL,
    )
    return m.group(1) if m else ""


def convert_macro(attrs: str, inner: str, asset_map: dict) -> str:
    name = get_macro_name(attrs) or ""
    # toc → inline note pointing to the outline pane (Plane renders the
    # real outline in the right-side navigation pane automatically)
    if name == "toc":
        return (
            f'<p class="{P_CLASS}"><em>※ 目次はページ右側のアウトラインペインに自動表示されます。</em></p>'
        )

    # jira macro → link to the Plane work item (if the project was migrated)
    # or fall back to the original Jira browse URL.
    if name == "jira":
        key = html_mod.unescape(get_param(inner, "key").strip())
        jql = html_mod.unescape(get_param(inner, "jqlQuery").strip())
        if key:
            ident_m = re.match(r"([A-Z][A-Z0-9_]*)-(\d+)", key)
            if ident_m and ident_m.group(1).upper() in PLANE_PROJECT_IDENTIFIERS:
                href = f"{PLANE_BASE}/{WORKSPACE_SLUG}/browse/{html_mod.escape(key)}/"
            else:
                href = f"{JIRA_BASE}/browse/{html_mod.escape(key)}"
            return (
                f'<p class="{P_CLASS}">'
                f'<a href="{href}" target="_blank" rel="noopener noreferrer">'
                f'🎫 {html_mod.escape(key)}</a>'
                f"</p>"
            )
        if jql:
            # Try to map `project = "NAME"` or `project = IDENT` (or with `IN (..)`)
            # from the JQL to a migrated Plane project. If found, link to that
            # project's work-items page; otherwise fall back to workspace-views.
            proj_id = None
            proj_m = re.search(
                r'project\s*=\s*"([^"]+)"|project\s*=\s*([A-Za-z][A-Za-z0-9_]*)',
                jql,
            )
            if proj_m:
                raw = (proj_m.group(1) or proj_m.group(2) or "").strip()
                proj_id = PLANE_PROJECT_LOOKUP.get(raw.upper()) or PLANE_PROJECT_LOOKUP.get(raw.lower())
            if proj_id:
                href = f"{PLANE_BASE}/{WORKSPACE_SLUG}/projects/{proj_id}/issues/"
                label = "🎫 Plane プロジェクトの課題一覧"
            else:
                href = f"{PLANE_BASE}/{WORKSPACE_SLUG}/workspace-views/all-issues/"
                label = "🎫 Plane 全課題（元 Jira JQL に相当する絞り込み不可）"
            return (
                f'<p class="{P_CLASS}">'
                f'<a href="{href}" target="_blank" rel="noopener noreferrer">'
                f"{label}</a>"
                f"<br><em>元 JQL: {html_mod.escape(jql)[:200]}</em>"
                f"</p>"
            )
        return f'<p class="{P_CLASS}"><em>🎫 元 Jira 埋め込み（情報不足で復元不可）</em></p>'

    # include → link to included page. The nested ac:link was already
    # rewritten to <a href> by convert_ac_links(); re-use that link.
    if name == "include":
        a_m = re.search(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', inner, re.DOTALL)
        if a_m:
            href = a_m.group(1)
            text = a_m.group(2).strip()
            return (
                f'<p class="{P_CLASS}">'
                f'📄 <a href="{href}">{text}</a>'
                f' <em>(元 Confluence の include マクロ)</em>'
                f"</p>"
            )
        # Unresolved span (ac:link that didn't resolve)
        span_m = re.search(r'<span[^>]*title="未解決[^"]*"[^>]*>(.*?)</span>', inner, re.DOTALL)
        if span_m:
            return (
                f'<p class="{P_CLASS}">'
                f'📄 <em>未解決 include: {span_m.group(1).strip()}</em>'
                f"</p>"
            )
        # Still fall back to raw scan (robust)
        rp = re.search(r'ri:content-title="([^"]+)"', inner)
        if rp:
            title = html_mod.unescape(rp.group(1))
            return (
                f'<p class="{P_CLASS}">'
                f'📄 <em>未解決 include: {html_mod.escape(title)}</em>'
                f"</p>"
            )
        return ""

    # expand → bold title + content
    if name == "expand":
        title = html_mod.unescape(get_param(inner, "title").strip())
        rtb_match = re.search(r"<ac:rich-text-body>(.*)</ac:rich-text-body>", inner, re.DOTALL)
        content_html = convert_all_macros(rtb_match.group(1), asset_map) if rtb_match else ""
        title_html = ""
        if title:
            title_html = f'<p class="{P_CLASS}"><strong>▼ {html_mod.escape(title)}</strong></p>'
        return title_html + content_html

    # panel → callout (emoji varies by bg color)
    if name == "panel":
        rtb_match = re.search(r"<ac:rich-text-body>(.*)</ac:rich-text-body>", inner, re.DOTALL)
        content_html = convert_all_macros(rtb_match.group(1), asset_map) if rtb_match else ""
        title = html_mod.unescape(get_param(inner, "title").strip())
        title_html = ""
        if title:
            title_html = f'<p class="{P_CLASS}"><strong>{html_mod.escape(title)}</strong></p>'
        return make_callout_wrapper(title_html + content_html, "info")

    # status → bold inline text
    if name == "status":
        title = html_mod.unescape(get_param(inner, "title").strip())
        if not title:
            return ""
        return f'<strong>[{html_mod.escape(title)}]</strong>'

    # File embed macros (view-file, excel, spreadsheets, viewxls, viewppt)
    # → link to the attached file.
    # Confluence stores the filename either as a nested <ri:attachment/>
    # reference (modern) or as an <ac:parameter ac:name="name">FILE</ac:parameter>
    # (legacy <ac:macro> form).
    if name in {"view-file", "excel", "spreadsheets", "viewxls", "viewppt", "viewdoc", "viewpdf"}:
        fname = None
        att_m = re.search(r'<ri:attachment\b([^/]*)/>', inner)
        if att_m:
            fn_m = re.search(r'ri:filename="([^"]+)"', att_m.group(1))
            if fn_m:
                fname = html_mod.unescape(fn_m.group(1))
        if not fname:
            # Legacy <ac:macro> stores the filename in a "name" or "file" param.
            # The "file" form (excel macro) often carries a leading "^" meaning
            # "an attachment on the current page". The Stiltsoft "spreadsheets"
            # macro instead uses "documentId" pointing at a .ssc document.
            fname_raw = (
                get_param(inner, "name").strip()
                or get_param(inner, "file").strip()
                or get_param(inner, "documentId").strip()
            )
            if fname_raw:
                fname = html_mod.unescape(fname_raw)
        if fname:
            fname = norm(fname.lstrip("^").strip())
            # Stiltsoft stores a .ssc document id; the real attachment is the
            # underlying xlsx ("X.xlsx.ssc" -> "X.xlsx", "名前.ssc" -> "名前.xlsx").
            if fname.endswith(".ssc"):
                fname = fname[:-4]
                if not fname.lower().endswith((".xlsx", ".xls")):
                    fname += ".xlsx"
            aid = asset_map.get(fname)
            icon = "📊" if name in {"excel", "spreadsheets", "viewxls"} else (
                "📽" if name == "viewppt" else "📄"
            )
            # Spreadsheet embeds: render the actual sheet inline as a table, then
            # a download link to the original xlsx (preserves formatting/formulas).
            table_html = ""
            if name in {"excel", "spreadsheets", "viewxls"} and aid:
                table_html = xlsx_to_table_html(aid) or ""
            if aid:
                url = f"{PLANE_BASE}/api/assets/v2/workspaces/{WORKSPACE_SLUG}/{aid}/"
                link = (
                    f'<p class="{P_CLASS}">{icon} '
                    f'<a href="{url}" target="_blank" rel="noopener noreferrer">'
                    f'{html_mod.escape(fname)}</a></p>'
                )
                return table_html + link
            return (
                f'<p class="{P_CLASS}">{icon} '
                f'<em>未解決 embed: {html_mod.escape(fname)}</em></p>'
            )
        return ""

    # children / pagetree → render the current page's direct children as a
    # bullet list of links. This replaces a misleading "check the sidebar"
    # note that didn't reflect where Plane actually shows subpages.
    if name in {"children", "pagetree", "pagetreesearch"}:
        if not _CURRENT_PAGE_ID:
            return ""
        kids = PLANE_CHILDREN.get(_CURRENT_PAGE_ID, [])
        if not kids:
            return ""
        items = []
        for kid in kids:
            kname = PLANE_ID_TO_NAME.get(kid) or kid
            kurl = PLANE_ID_TO_URL.get(kid)
            if not kurl:
                continue
            items.append(
                f'<li class="editor-list-item-block">'
                f'<p class="{P_CLASS}"><a href="{kurl}">{html_mod.escape(kname)}</a></p>'
                f"</li>"
            )
        if not items:
            return ""
        return f'<ul class="editor-list-block">{"".join(items)}</ul>'

    # anchor macro — emits nothing visible (TipTap auto-adds heading anchors)
    if name == "anchor":
        return ""

    # gliffy → image-component referencing the uploaded PNG preview
    if name == "gliffy":
        diag_name_m = re.search(
            r'<ac:parameter\s+ac:name="name">([^<]+)</ac:parameter>', inner
        )
        if not diag_name_m:
            return ""
        diag_name = norm(html_mod.unescape(diag_name_m.group(1).strip()))
        aid = asset_map.get(norm(diag_name + ".png"))
        if not aid:
            return f'<p class="{P_CLASS}"><em>🖼 未解決 Gliffy: {html_mod.escape(diag_name)}</em></p>'
        abs_url = f"{PLANE_BASE}/api/assets/v2/workspaces/{WORKSPACE_SLUG}/{aid}/"
        new_id = str(uuidlib.uuid4())
        return (
            f'<image-component src="{abs_url}" id="{new_id}" data-id="{new_id}" '
            f'width="200%" height="auto" alignment="left" status="uploaded"></image-component>'
        )

    # Pure dynamic widgets → drop silently
    if name in {
        "change-history", "recently-updated", "contributors",
        "content-report-table", "tasks-report-macro", "contentbylabel",
        "livesearch", "listlabels", "blog-posts", "calendar",
        "create-from-template", "roadmap", "profile-picture",
        "jirachart", "gadget", "attachments",
    }:
        return ""

    if name in CODE_MACRO_NAMES:
        lang_m = re.search(r'<ac:parameter[^>]*ac:name="language">([^<]+)', inner)
        lang = lang_m.group(1).strip() if lang_m else ""
        body_m = re.search(
            r"<ac:plain-text-body>\s*<!\[CDATA\[(.*?)\]\]>\s*</ac:plain-text-body>",
            inner,
            re.DOTALL,
        )
        code = body_m.group(1) if body_m else ""
        return make_code_block(lang, code)

    if name in CALLOUT_MACRO_NAMES:
        # Extract rich-text-body
        rtb_match = re.search(r"<ac:rich-text-body>(.*)</ac:rich-text-body>", inner, re.DOTALL)
        rtb = rtb_match.group(1) if rtb_match else ""
        # Include title parameter as a bold heading inside the callout
        title_m = re.search(r'<ac:parameter[^>]*ac:name="title">([^<]*)</ac:parameter>', inner)
        title_html = ""
        if title_m and title_m.group(1).strip():
            safe_title = html_mod.escape(title_m.group(1).strip())
            title_html = f'<p class="{P_CLASS}"><strong>{safe_title}</strong></p>'
        converted = convert_all_macros(rtb, asset_map)
        return make_callout_wrapper(title_html + converted, name)

    # Other structured macros: unwrap rich-text-body if any; else drop
    rtb_match = re.search(r"<ac:rich-text-body>(.*)</ac:rich-text-body>", inner, re.DOTALL)
    if rtb_match:
        return convert_all_macros(rtb_match.group(1), asset_map)
    # Plain-text-body → treat as code block without language
    ptb_match = re.search(
        r"<ac:plain-text-body>\s*<!\[CDATA\[(.*?)\]\]>\s*</ac:plain-text-body>",
        inner,
        re.DOTALL,
    )
    if ptb_match:
        return make_code_block("", ptb_match.group(1))
    return ""


def convert_all_macros(fragment: str, asset_map: dict) -> str:
    """Recursively convert every structured-macro in `fragment` via
    convert_macro, preserving surrounding text."""
    out = []
    pos = 0
    spans = find_structured_macro_spans(fragment)
    for start, end, attrs, inner in spans:
        if start > pos:
            out.append(fragment[pos:start])
        out.append(convert_macro(attrs, inner, asset_map))
        pos = end
    if pos < len(fragment):
        out.append(fragment[pos:])
    return "".join(out)


AC_LINK_RE = re.compile(r"<ac:link\b([^>]*)>(.*?)</ac:link>", re.DOTALL)


def convert_ac_links(h: str, asset_map: dict, current_space: str | None = None) -> str:
    """Resolve <ac:link> to <a href=…>text</a>.

    - <ri:page content-title=… space-key=…> → Plane page URL via TITLE_TO_PLANE_URL
    - <ri:url value=…> → direct href
    - <ri:attachment filename=…> → /api/assets/v2/workspaces/keis/<asset_id>/
    - Display text: <ac:plain-text-link-body>CDATA</ac:plain-text-link-body>
                  | <ac:link-body>html</ac:link-body>
                  | fallback to page title / url
    """

    def extract_text(link_inner: str, fallback: str) -> str:
        ptb = re.search(
            r"<ac:plain-text-link-body>\s*<!\[CDATA\[(.*?)\]\]>\s*</ac:plain-text-link-body>",
            link_inner,
            re.DOTALL,
        )
        if ptb:
            return html_mod.escape(ptb.group(1))
        lb = re.search(r"<ac:link-body>(.*?)</ac:link-body>", link_inner, re.DOTALL)
        if lb:
            return lb.group(1).strip() or html_mod.escape(fallback)
        return html_mod.escape(fallback)

    def repl(match):
        attrs = match.group(1)
        inner = match.group(2)
        anchor_m = re.search(r'ac:anchor="([^"]+)"', attrs)
        anchor = html_mod.unescape(anchor_m.group(1)) if anchor_m else None

        ri_page = re.search(r'<ri:page\b([^/]*)/?>', inner)
        ri_url = re.search(r'<ri:url\b([^/]*)/>', inner)
        ri_att = re.search(r'<ri:attachment\b([^/]*)/>', inner)

        if ri_page:
            a = ri_page.group(1)
            title_m = re.search(r'ri:content-title="([^"]+)"', a)
            space_m = re.search(r'ri:space-key="([^"]+)"', a)
            title = html_mod.unescape(title_m.group(1)) if title_m else None
            space = space_m.group(1) if space_m else current_space
            if title:
                url = TITLE_TO_PLANE_URL.get((space, title)) or TITLE_TO_PLANE_URL.get((None, title))
                if url:
                    if anchor:
                        url = url.rstrip("/") + f"#{anchor}"
                    text = extract_text(inner, title)
                    return f'<a href="{url}">{text}</a>'
                # Unresolved — keep as plain text
                text = extract_text(inner, title)
                return f'<span title="未解決 Confluence link">{text}</span>'

        if ri_url:
            a = ri_url.group(1)
            url_m = re.search(r'ri:value="([^"]+)"', a)
            if url_m:
                orig_url = html_mod.unescape(url_m.group(1))
                url = resolve_confluence_url(orig_url)
                text = extract_text(inner, url)
                # If body text is the bare original URL, prefer the target
                # Plane page's title (falling back to the new URL) so migrated
                # links read naturally instead of showing stale URLs.
                if html_mod.unescape(text).strip() == orig_url:
                    text = html_mod.escape(_link_label_for_url(url))
                return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{text}</a>'

        if ri_att:
            a = ri_att.group(1)
            fn_m = re.search(r'ri:filename="([^"]+)"', a)
            if fn_m:
                fname = norm(html_mod.unescape(fn_m.group(1)))
                asset_id = asset_map.get(fname)
                if asset_id:
                    url = f"{PLANE_BASE}/api/assets/v2/workspaces/{WORKSPACE_SLUG}/{asset_id}/"
                    text = extract_text(inner, fname)
                    return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{text}</a>'
                text = extract_text(inner, fname)
                return f'<span title="未解決 Confluence attachment">{text}</span>'

        # Fallback
        return extract_text(inner, "")

    return AC_LINK_RE.sub(repl, h)


def convert_task_lists(h: str) -> str:
    """Convert <ac:task-list>…</ac:task-list> with <ac:task> children to
    TipTap task list format (<ul data-type="taskList"><li data-checked="…">)."""
    TASK_LIST_RE = re.compile(r"<ac:task-list[^>]*>(.*?)</ac:task-list>", re.DOTALL)
    TASK_RE = re.compile(r"<ac:task\b[^>]*>(.*?)</ac:task>", re.DOTALL)
    STATUS_RE = re.compile(r"<ac:task-status>([^<]+)</ac:task-status>")
    BODY_RE = re.compile(r"<ac:task-body[^>]*>(.*?)</ac:task-body>", re.DOTALL)

    def strip_task_id(inner):
        return re.sub(r"<ac:task-id>[^<]*</ac:task-id>", "", inner)

    def repl_list(m):
        inner = strip_task_id(m.group(1))
        items = []
        for tm in TASK_RE.finditer(inner):
            task_inner = tm.group(1)
            status = (STATUS_RE.search(task_inner) or re.match("", "")).group(1) if STATUS_RE.search(task_inner) else "incomplete"
            body_m = BODY_RE.search(task_inner)
            body_html = body_m.group(1).strip() if body_m else ""
            # Unwrap trivial <pre> / <div> wrappers and convert to <p>
            body_html = re.sub(r"^<div[^>]*>|</div>$", "", body_html).strip()
            if body_html.startswith("<pre"):
                inner_pre = re.sub(r"<pre[^>]*>|</pre>", "", body_html)
                body_html = html_mod.escape(inner_pre.strip())
                body_html = f'<p class="{P_CLASS}">{body_html}</p>'
            elif not body_html.startswith("<p"):
                body_html = f'<p class="{P_CLASS}">{body_html}</p>'
            checked = "true" if status.lower() == "complete" else "false"
            items.append(f'<li data-checked="{checked}" data-type="taskItem">{body_html}</li>')
        return '<ul data-type="taskList">' + "".join(items) + "</ul>"

    return TASK_LIST_RE.sub(repl_list, h)


def _repair_orphan_table_fragments(h: str) -> str:
    """An upstream macro/layout transform can drop a table's opening
    <table><tbody><tr> while leaving the cell run and its </tbody></table>.
    ProseMirror/TipTap then discards EVERY table in the document. Detect a
    </table> that has no matching <table> before it and wrap the orphan
    cell-run in a fresh <table><tbody><tr> (adding <td> if the run starts with
    a closing cell) so it parses as a real table. Balanced tables are untouched.
    """
    if h.count("</table>") <= len(re.findall(r"<table\b", h)):
        return h
    tag_re = re.compile(r"<table\b[^>]*>|</table>")
    out = []
    last = 0
    depth = 0
    for m in tag_re.finditer(h):
        if m.group(0) == "</table>":
            if depth > 0:
                depth -= 1
                continue
            # Orphan close: the run from `last` to here lost its <table> opener.
            seg = h[last : m.end()]
            cm = re.search(r"</?(?:td|th|tr|tbody|thead)\b", seg)
            if cm is None:
                out.append(seg)
            else:
                before = seg[: cm.start()]
                cells = seg[cm.start() : -len("</table>")]
                opener = "<table><tbody><tr>"
                if re.match(r"</(?:td|th)\b", cells):
                    opener += "<td>"
                out.append(before + opener + cells + "</table>")
            last = m.end()
        else:
            depth += 1
    out.append(h[last:])
    return "".join(out)


def finalize_html(h: str, asset_map: dict) -> str:
    # Images
    def replace_image(m):
        content = m.group(0)
        att_m = re.search(r'ri:attachment\s+ri:filename="([^"]*)"', content)
        url_m = re.search(r'ri:url\s+ri:value="([^"]*)"', content)
        if att_m:
            aid = asset_map.get(norm(html_mod.unescape(att_m.group(1))))
            if aid:
                abs_url = f"{PLANE_BASE}/api/assets/v2/workspaces/{WORKSPACE_SLUG}/{aid}/"
                new_id = str(uuidlib.uuid4())
                return (
                    f'<image-component src="{abs_url}" id="{new_id}" data-id="{new_id}" '
                    f'width="200%" height="auto" alignment="left" status="uploaded"></image-component>'
                )
            return ""
        if url_m:
            return f'<img src="{url_m.group(1)}" />'
        return ""

    h = re.sub(r"<ac:image[^>]*>.*?</ac:image>", replace_image, h, flags=re.DOTALL)
    h = re.sub(r"<ac:image[^>]*/>", "", h)

    # ac:layout passthrough
    h = re.sub(r"<ac:layout[^>]*>", "", h)
    h = h.replace("</ac:layout>", "")
    h = re.sub(r"<ac:layout-section[^>]*>", "", h)
    h = h.replace("</ac:layout-section>", "")
    h = re.sub(r"<ac:layout-cell[^>]*>", "", h)
    h = h.replace("</ac:layout-cell>", "")

    # Drop remaining ac:/ri:
    h = re.sub(r"</?ac:[a-z-]+[^>]*>", "", h)
    h = re.sub(r"</?ri:[a-z-]+[^>]*/?>", "", h)

    # Recover orphan table fragments (opening <table><tbody><tr> lost upstream)
    # before colwidth assignment, so the recovered table is styled too.
    h = _repair_orphan_table_fragments(h)

    # Table: always assign colwidth = EDITOR_WIDTH / num_cols so the editor
    # renders full-width tables. Handles nested tables correctly by processing
    # innermost tables first via a placeholder round-trip.
    EDITOR_WIDTH = 720

    def _process_table_inner(table_body: str) -> str:
        first_row = re.search(r'<tr[^>]*>(.*?)</tr>', table_body, re.DOTALL)
        if not first_row:
            return f"<table>{table_body}</table>"
        num_cols = len(re.findall(r"<t[hd]\b", first_row.group(1)))
        if num_cols == 0:
            return f"<table>{table_body}</table>"
        col_w = max(50, EDITOR_WIDTH // num_cols)

        def _add_colwidth(cell_m):
            tag = cell_m.group(0)
            if "colwidth" in tag:
                return tag
            return tag[:-1] + f' colwidth="{col_w}">'

        new_body = re.sub(r"<(t[hd])\b([^>]*)>", _add_colwidth, table_body)
        return f"<table>{new_body}</table>"

    table_tokens: list[str] = []
    INNER_TABLE_RE = re.compile(
        r"<table([^>]*)>((?:(?!<table).)*?)</table>", re.DOTALL
    )
    while True:
        m = INNER_TABLE_RE.search(h)
        if not m:
            break
        processed = _process_table_inner(m.group(2))
        token = f"\x00TBL{len(table_tokens)}\x00"
        table_tokens.append(processed)
        h = h[: m.start()] + token + h[m.end() :]
    for i in range(len(table_tokens) - 1, -1, -1):
        h = h.replace(f"\x00TBL{i}\x00", table_tokens[i])

    # hr → TipTap horizontalRule div (otherwise raw <hr> disrupts block nesting)
    h = re.sub(
        r"<hr\s*/?>",
        '<div class="py-4 border-strong-1" data-type="horizontalRule"><div></div></div>',
        h,
    )

    # Color span: <span ... style="...color..."> → <span data-text-color/data-background-color>
    # Without this, zeed-dom (server-side TipTap DOM) breaks parseHTML on styled
    # spans (tiptap #5352) → colored text/highlights lose their formatting.
    # Matches style attribute regardless of position; preserves other attrs.
    def _fix_color_span(m):
        before = m.group(1)
        style = m.group(2)
        after = m.group(3)
        color_m = re.search(r'(?:^|;|\s)color:\s*([^;]+)', style)
        bg_m = re.search(r'background-color:\s*([^;]+)', style)
        if not (color_m or bg_m):
            return m.group(0)
        data = ""
        if color_m:
            data += f' data-text-color="{html_mod.escape(color_m.group(1).strip())}"'
        if bg_m:
            data += f' data-background-color="{html_mod.escape(bg_m.group(1).strip())}"'
        other = (before + after).strip()
        other = re.sub(r"\s+", " ", other)
        if other:
            return f"<span {other}{data}>"
        return f"<span{data}>"

    h = re.sub(
        r'<span\b([^>]*?)style="([^"]*(?:color|background)[^"]*)"([^>]*?)>',
        _fix_color_span,
        h,
    )

    # Editor classes
    h = re.sub(r"<h([1-6])>", r'<h\1 class="' + H_CLASS + r'">', h)
    h = re.sub(r"<p>", f'<p class="{P_CLASS}">', h)
    return h


def build_page_asset_map(cur, page_id: str, global_map: dict) -> dict:
    """Return {filename → asset_id} preferring PAGE_DESCRIPTION assets
    attached to this page, then falling back to the global map (which
    is already pre-sorted to prefer PAGE_DESCRIPTION across all pages,
    then other entity types)."""
    cur.execute(
        "SELECT attributes->>'name', id::text FROM file_assets "
        "WHERE entity_identifier = %s AND entity_type = 'PAGE_DESCRIPTION' AND is_uploaded = true",
        [page_id],
    )
    same_page = {}
    for name, aid in cur.fetchall():
        if name:
            same_page[norm(name)] = aid
    # Merge with global fallback (same-page wins)
    merged = dict(global_map)
    merged.update(same_page)
    return merged


_PLANE_PAGE_URL_RE = re.compile(
    r"/pages/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/?"
)


def _link_label_for_url(new_url: str) -> str:
    """Return the Plane page name if new_url points at one, else the URL itself."""
    m = _PLANE_PAGE_URL_RE.search(new_url)
    if m:
        name = PLANE_ID_TO_NAME.get(m.group(1))
        if name:
            return name
    return new_url


def rewrite_plain_confluence_hrefs(h: str) -> str:
    """Post-process any plain <a href="https://confluence...">text</a>.
    Rewrites href to the Plane equivalent. If the visible text is the bare
    old URL (common authoring pattern: pasted URL as both href and text),
    rewrites the text to the target Plane page's title (or the new URL if
    the target is not a Plane page), so users don't see stale confluence.aruhi
    URLs pointing to Plane pages."""
    def repl(m):
        full = m.group(0)
        url = m.group(1)
        inner = m.group(2)
        new_url = resolve_confluence_url(html_mod.unescape(url))
        if new_url == url:
            return full
        new_full = full.replace(url, html_mod.escape(new_url), 1)
        if html_mod.unescape(inner).strip() == html_mod.unescape(url).strip():
            label = _link_label_for_url(new_url)
            new_full = re.sub(
                r"(<a\b[^>]*>).*?(</a>)",
                lambda mm: mm.group(1) + html_mod.escape(label) + mm.group(2),
                new_full,
                count=1,
                flags=re.DOTALL,
            )
        return new_full

    h = re.sub(
        r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        repl,
        h,
        flags=re.DOTALL,
    )

    # Also rewrite <img src="https://confluence.../download/attachments/...">.
    # These bypass <ac:image>, usually because the author pasted the raw URL.
    def _img_repl(m):
        tag = m.group(0)
        src = m.group(1)
        new_src = resolve_confluence_url(html_mod.unescape(src))
        if new_src == src:
            return tag
        return tag.replace(src, html_mod.escape(new_src), 1)

    h = re.sub(r'<img\b[^>]*src="([^"]+)"[^>]*/?>', _img_repl, h)
    return h


def convert_page_body(body: str, asset_map: dict, space: str | None = None) -> str:
    # Order matters:
    #   1. ac:link → <a> (before ac: strip in finalize_html)
    #   2. ac:task-list → TipTap tasklist
    #   3. Macros (info, expand, code, etc.)
    #   4. Finalize (images, layout strip, class decoration)
    #   5. Rewrite any remaining Confluence hrefs to Plane URLs
    # Confluence wraps the spreadsheet macro in a <p>; since we now emit a
    # <table> for excel/spreadsheets/viewxls, strip that wrapping <p> first —
    # a <table> nested inside a <p> is invalid and TipTap drops it.
    body = re.sub(
        r'<p>\s*(<ac:(?:structured-)?macro\b[^>]*\bac:name="'
        r'(?:excel|spreadsheets|viewxls)"[^>]*>.*?</ac:(?:structured-)?macro>)\s*</p>',
        r"\1",
        body,
        flags=re.DOTALL,
    )
    body = convert_ac_links(body, asset_map, space)
    body = convert_task_lists(body)
    converted = convert_all_macros(body, asset_map)
    finalized = finalize_html(converted, asset_map)
    return rewrite_plain_confluence_hrefs(finalized)


def main():
    args = sys.argv[1:]
    dry_run = "--apply" not in args
    dump_path = None
    if "--dump" in args:
        i = args.index("--dump")
        if i + 1 < len(args):
            dump_path = args[i + 1]
            args = args[:i] + args[i + 2 :]
    target_ids = [a for a in args if a != "--apply"]

    cur = connection.cursor()
    # Priority order: PAGE_DESCRIPTION > COMMENT_DESCRIPTION > others
    cur.execute(
        "SELECT id::text, attributes->>'name', entity_type, asset FROM file_assets WHERE is_uploaded=true "
        "ORDER BY CASE entity_type WHEN 'PAGE_DESCRIPTION' THEN 0 "
        "WHEN 'COMMENT_DESCRIPTION' THEN 1 "
        "WHEN 'ISSUE_DESCRIPTION' THEN 2 "
        "WHEN 'ISSUE_ATTACHMENT' THEN 3 ELSE 9 END"
    )
    asset_map = {}
    global _ASSET_KEY, _S3_CLIENT, _S3_BUCKET
    for aid, name, _etype, key in cur.fetchall():
        _ASSET_KEY[aid] = key
        if not name:
            continue
        # First-wins with the priority ordering above
        asset_map.setdefault(norm(name), aid)
    print(f"Loaded {len(asset_map)} filename → asset_id entries (PAGE_DESCRIPTION prioritized)", file=sys.stderr)

    # S3 client for embedding spreadsheet macros as inline tables.
    try:
        import boto3
        from django.conf import settings

        _S3_BUCKET = getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)
        _S3_CLIENT = boto3.client(
            "s3",
            endpoint_url=getattr(settings, "AWS_S3_ENDPOINT_URL", None),
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
            region_name=getattr(settings, "AWS_REGION", None) or "us-east-1",
        )
    except Exception as e:  # noqa: BLE001
        print(f"S3 client init failed (spreadsheet embedding disabled): {e}", file=sys.stderr)

    cur.execute(
        "SELECT id::text, external_id FROM pages "
        "WHERE external_source='confluence' AND deleted_at IS NULL AND external_id IS NOT NULL"
    )
    ext_to_plane = {}
    for pid, ext in cur.fetchall():
        try:
            ext_to_plane[int(ext)] = pid
        except (TypeError, ValueError):
            continue

    n_titles = build_title_maps(cur)
    print(f"Loaded {n_titles} (space, title) → Plane URL entries", file=sys.stderr)

    # Build ext_id → space for current-space fallback on ac:link resolution
    ext_to_space = {}
    if os.path.exists("/tmp/confluence_pages.jsonl"):
        with open("/tmp/confluence_pages.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("id") and d.get("space"):
                    ext_to_space[int(d["id"])] = d["space"]

    updates = []
    stats = defaultdict(int)
    HAS_TARGET = re.compile(
        r'ac:name="(info|note|tip|warning|toc|jira|expand|include|panel|status'
        r'|view-file|excel|spreadsheets|viewxls|viewppt|viewdoc|viewpdf'
        r'|children|pagetree|pagetreesearch|anchor|gliffy)"'
        r'|<ac:task-list\b|<ac:link\b|<table\b'
    )

    with open(CONF, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 2:
                continue
            try:
                ext = int(parts[0])
                body = bytes.fromhex(parts[1]).decode("utf-8", errors="replace")
            except Exception:
                stats["decode_error"] += 1
                continue
            if not HAS_TARGET.search(body):
                continue
            page_id = ext_to_plane.get(ext)
            if not page_id:
                stats["no_plane_page"] += 1
                continue
            if target_ids and page_id not in target_ids:
                continue
            space = ext_to_space.get(ext)
            # Per-page asset map: same-page PAGE_DESCRIPTION wins, then global priority
            per_page_map = build_page_asset_map(cur, page_id, asset_map)
            global _CURRENT_PAGE_ID, _CURRENT_ASSET_MAP
            _CURRENT_PAGE_ID = page_id
            _CURRENT_ASSET_MAP = per_page_map
            new_html = convert_page_body(body, per_page_map, space)
            # Drop lingering migration-footer markers/content
            new_html = re.sub(
                r"<!--\s*migration:[a-z-]+\s*-->.*?(?=<!--\s*migration:|\Z)",
                "",
                new_html,
                flags=re.DOTALL,
            )
            callout_count = new_html.count('data-block-type="callout-component"')
            task_list_count = new_html.count('data-type="taskList"')
            toc_note_count = new_html.count("アウトラインペイン")
            jira_count = new_html.count("/browse/") + new_html.count("/issues/?jql=")
            include_count = new_html.count("元 Confluence の include マクロ")
            updates.append((page_id, new_html, callout_count + task_list_count + toc_note_count))
            stats["pages"] += 1
            stats["callouts"] += callout_count
            stats["task_lists"] += task_list_count
            stats["toc_notes"] += toc_note_count
            stats["jira_refs"] += jira_count
            stats["includes"] += include_count

    print("Stats:", file=sys.stderr)
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}", file=sys.stderr)
    print(f"\n{'Would update' if dry_run else 'Updating'} {len(updates)} pages", file=sys.stderr)

    if dump_path:
        with open(dump_path, "w", encoding="utf-8") as out:
            for pid, new_html, _ in updates:
                out.write(json.dumps({"id": pid, "html": new_html}, ensure_ascii=False) + "\n")
        print(f"Wrote {len(updates)} proposed HTMLs to {dump_path}", file=sys.stderr)
        return

    if dry_run:
        for pid, _, n in updates[:5]:
            print(f"  {pid}: {n}", file=sys.stderr)
        if len(updates) > 5:
            print(f"  ... and {len(updates)-5} more", file=sys.stderr)
        return

    for i, (pid, new_html, _) in enumerate(updates, 1):
        Page.objects.filter(id=pid).update(
            description_html=new_html,
            description_binary=b"",
            updated_at=dj_timezone.now(),
        )
        if i % 200 == 0:
            print(f"  ...updated {i}/{len(updates)}", file=sys.stderr)
    print(f"Applied {len(updates)} page updates", file=sys.stderr)

    rc = get_redis_connection("default")
    ts = datetime.now(timezone.utc).isoformat()
    recv = 0
    for pid, _, _ in updates:
        recv += rc.publish(
            "plane:admin",
            json.dumps(
                {
                    "command": "force_close",
                    "docId": pid,
                    "reason": "corruption_detected",
                    "code": 4000,
                    "timestamp": ts,
                }
            ),
        )
    print(f"force_close receivers total: {recv}", file=sys.stderr)


if __name__ == "__main__":
    main()

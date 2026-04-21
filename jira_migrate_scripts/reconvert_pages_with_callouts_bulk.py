#!/usr/bin/env python3
"""Bulk re-convert: for every page whose Confluence body contains an
info/note/tip/warning macro, re-generate Plane TipTap HTML with those
macros rendered as callout-component divs in their original position.

v2: Properly handle nested macros (e.g. info containing a code macro)
via a balanced scanner instead of non-greedy regex.
"""
import base64
import html as html_mod
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

STRUCTURED_OPEN_RE = re.compile(r'<ac:structured-macro\b([^>]*)>')
STRUCTURED_OPEN_OR_CLOSE = re.compile(r'<(/?)ac:structured-macro\b[^>]*/?>')
CALLOUT_MACRO_NAMES = {"info", "note", "tip", "warning"}
CODE_MACRO_NAMES = {"code", "noformat"}
ICON_BY_TYPE = {"info": "128161", "note": "128221", "tip": "128161", "warning": "9888"}

# Populated by build_title_maps() at main()
TITLE_TO_PLANE_URL: dict = {}


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
    # cid → plane page info
    cur.execute(
        "SELECT pages.external_id, pages.id::text, pp.project_id::text FROM pages "
        "LEFT JOIN project_pages pp ON pp.page_id = pages.id "
        "WHERE pages.external_source='confluence' AND pages.deleted_at IS NULL"
    )
    cid_to_plane = {}
    for ext, pid, proj in cur.fetchall():
        try:
            cid = int(ext)
        except (TypeError, ValueError):
            continue
        cid_to_plane[cid] = (pid, proj)

    global TITLE_TO_PLANE_URL
    TITLE_TO_PLANE_URL = {}
    for (space, title), cid in title_to_cid.items():
        if cid not in cid_to_plane:
            continue
        pid, proj = cid_to_plane[cid]
        if not proj:
            continue
        TITLE_TO_PLANE_URL[(space, title)] = f"{PLANE_BASE}/{WORKSPACE_SLUG}/projects/{proj}/pages/{pid}/"
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
        # strip the actual </ac:structured-macro> at the end
        close_m_iter = list(re.finditer(r'</ac:structured-macro\s*>', body[inner_start:end]))
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

    # jira macro → link to original Jira
    if name == "jira":
        key = html_mod.unescape(get_param(inner, "key").strip())
        jql = html_mod.unescape(get_param(inner, "jqlQuery").strip())
        if key:
            return (
                f'<p class="{P_CLASS}">'
                f'<a href="{JIRA_BASE}/browse/{html_mod.escape(key)}" target="_blank" rel="noopener noreferrer">'
                f'🎫 {html_mod.escape(key)}</a>'
                f"</p>"
            )
        if jql:
            import urllib.parse

            encoded = urllib.parse.quote(jql)
            return (
                f'<p class="{P_CLASS}">'
                f'<a href="{JIRA_BASE}/issues/?jql={encoded}" target="_blank" rel="noopener noreferrer">'
                f"🎫 元 Jira クエリ結果を表示</a>"
                f"<br><em>JQL: {html_mod.escape(jql)[:200]}</em>"
                f"</p>"
            )
        return f'<p class="{P_CLASS}"><em>🎫 元 Jira 埋め込み（情報不足で復元不可）</em></p>'

    # include → link to included page
    if name == "include":
        include_link_m = re.search(
            r'<ac:link[^>]*>\s*<ri:page\b([^/]*)/>', inner, re.DOTALL
        )
        if include_link_m:
            a = include_link_m.group(1)
            title_m = re.search(r'ri:content-title="([^"]+)"', a)
            space_m = re.search(r'ri:space-key="([^"]+)"', a)
            title = html_mod.unescape(title_m.group(1)) if title_m else None
            space = space_m.group(1) if space_m else None
            if title:
                url = TITLE_TO_PLANE_URL.get((space, title)) or TITLE_TO_PLANE_URL.get((None, title))
                display = html_mod.escape(title)
                if url:
                    return (
                        f'<p class="{P_CLASS}">'
                        f'📄 <a href="{url}">{display}</a>'
                        f" <em>(元 Confluence の include マクロ)</em>"
                        f"</p>"
                    )
                return (
                    f'<p class="{P_CLASS}">'
                    f"📄 <em>未解決 include: {display}</em>"
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
                url = html_mod.unescape(url_m.group(1))
                text = extract_text(inner, url)
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
                    f'width="80%" height="auto" alignment="center" status="uploaded"></image-component>'
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

    # Editor classes
    h = re.sub(r"<h([1-6])>", r'<h\1 class="' + H_CLASS + r'">', h)
    h = re.sub(r"<p>", f'<p class="{P_CLASS}">', h)
    return h


def convert_page_body(body: str, asset_map: dict, space: str | None = None) -> str:
    # Order matters:
    #   1. ac:link → <a> (before ac: strip in finalize_html)
    #   2. ac:task-list → TipTap tasklist
    #   3. Macros (info, expand, code, etc.)
    #   4. Finalize (images, layout strip, class decoration)
    body = convert_ac_links(body, asset_map, space)
    body = convert_task_lists(body)
    converted = convert_all_macros(body, asset_map)
    return finalize_html(converted, asset_map)


def main():
    dry_run = "--apply" not in sys.argv
    target_ids = [a for a in sys.argv[1:] if a != "--apply"]

    cur = connection.cursor()
    cur.execute("SELECT id::text, attributes->>'name' FROM file_assets WHERE is_uploaded=true")
    asset_map = {}
    for aid, name in cur.fetchall():
        if not name:
            continue
        asset_map.setdefault(norm(name), aid)
    print(f"Loaded {len(asset_map)} filename → asset_id entries", file=sys.stderr)

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
        r'ac:name="(info|note|tip|warning|toc|jira|expand|include|panel|status)"'
        r'|<ac:task-list\b|<ac:link\b'
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
            new_html = convert_page_body(body, asset_map, space)
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

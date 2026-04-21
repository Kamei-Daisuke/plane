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

P_CLASS = "editor-paragraph-block"
H_CLASS = "editor-heading-block"

STRUCTURED_OPEN_RE = re.compile(r'<ac:structured-macro\b([^>]*)>')
STRUCTURED_OPEN_OR_CLOSE = re.compile(r'<(/?)ac:structured-macro\b[^>]*/?>')
CALLOUT_MACRO_NAMES = {"info", "note", "tip", "warning"}
CODE_MACRO_NAMES = {"code", "noformat"}
ICON_BY_TYPE = {"info": "128161", "note": "128221", "tip": "128161", "warning": "9888"}


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


def convert_macro(attrs: str, inner: str, asset_map: dict) -> str:
    name = get_macro_name(attrs) or ""
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


def convert_page_body(body: str, asset_map: dict) -> str:
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

    updates = []
    stats = defaultdict(int)
    HAS_CALLOUT_MACRO = re.compile(r'ac:name="(info|note|tip|warning)"')

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
            if not HAS_CALLOUT_MACRO.search(body):
                continue
            page_id = ext_to_plane.get(ext)
            if not page_id:
                stats["no_plane_page"] += 1
                continue
            if target_ids and page_id not in target_ids:
                continue
            new_html = convert_page_body(body, asset_map)
            # Drop lingering migration-footer markers/content
            new_html = re.sub(
                r"<!--\s*migration:[a-z-]+\s*-->.*?(?=<!--\s*migration:|\Z)",
                "",
                new_html,
                flags=re.DOTALL,
            )
            callout_count = new_html.count('data-block-type="callout-component"')
            if callout_count == 0:
                stats["no_callouts_produced"] += 1
                continue
            updates.append((page_id, new_html, callout_count))
            stats["pages"] += 1
            stats["callouts"] += callout_count

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

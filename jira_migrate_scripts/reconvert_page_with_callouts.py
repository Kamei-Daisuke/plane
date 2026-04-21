#!/usr/bin/env python3
"""Re-convert one page's Confluence body → Plane TipTap HTML with info
macros rendered as callout-component divs in their original position.

Uses the same XHTML→TipTap logic as convert_final.py but with
additional info macro → callout handling. Writes the new HTML to
description_html, clears description_binary, force_closes.

Run (inside api container):
    docker exec <api> python /tmp/reconvert_page_with_callouts.py PAGE_UUID [--apply]

Assumes live is stopped + Redis flushed for a clean rebuild.
"""
import base64
import html as html_mod
import json
import os
import re
import sys
import uuid as uuidlib
from datetime import datetime, timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.production")
sys.path.insert(0, "/code")

import django  # noqa: E402

django.setup()

from django.utils import timezone as dj_timezone  # noqa: E402
from django_redis import get_redis_connection  # noqa: E402

from plane.db.models import Page  # noqa: E402


CONF = os.environ.get("CONFLUENCE_BODIES", "/tmp/conf_bodies_latest.tsv")
PLANE_BASE = os.environ.get("PLANE_BASE", "https://plane.keis-software.com")
WORKSPACE_SLUG = os.environ.get("WORKSPACE_SLUG", "keis")


def load_body(ext_id: int) -> str | None:
    with open(CONF, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 2:
                continue
            try:
                cid = int(parts[0])
                if cid == ext_id:
                    return bytes.fromhex(parts[1]).decode("utf-8", errors="replace")
            except Exception:
                continue
    return None


def make_callout_open(icon_unicode="128161"):
    return (
        f'<div data-block-type="callout-component" data-logo-in-use="emoji" '
        f'data-emoji-unicode="{icon_unicode}" '
        f'data-emoji-url="https://cdn.jsdelivr.net/npm/emoji-datasource-apple/img/apple/64/1f4a1.png" '
        f'id="{uuidlib.uuid4()}">'
    )


def transform_info_macros(body: str) -> str:
    """Replace <ac:structured-macro ac:name='info|note|tip|warning'>...
    <ac:rich-text-body>INNER</ac:rich-text-body>...</ac:structured-macro>
    with <div data-block-type='callout-component' ...>INNER</div>.

    INNER is kept as-is (still Confluence storage format); later passes
    will convert any remaining ac: tags to plain HTML."""
    macro_re = re.compile(
        r'<ac:structured-macro[^>]*ac:name="(info|note|tip|warning)"[^>]*>(.*?)</ac:structured-macro>',
        re.DOTALL,
    )
    icon_by_type = {"info": "128161", "note": "128221", "tip": "128161", "warning": "9888"}

    def repl(m):
        macro_type = m.group(1)
        content = m.group(2)
        rtb = re.search(r"<ac:rich-text-body>(.*?)</ac:rich-text-body>", content, re.DOTALL)
        inner = rtb.group(1) if rtb else ""
        return f"{make_callout_open(icon_by_type.get(macro_type, '128161'))}{inner}</div>"

    return macro_re.sub(repl, body)


# --- below: minimal convert_final-style XHTML → TipTap HTML ---

P = "editor-paragraph-block"
H = "editor-heading-block"


def convert_xhtml(xhtml: str, asset_map: dict) -> str:
    h = xhtml

    # Images
    def replace_image(m):
        content = m.group(0)
        att_m = re.search(r'ri:attachment\s+ri:filename="([^"]*)"', content)
        url_m = re.search(r'ri:url\s+ri:value="([^"]*)"', content)
        if att_m:
            aid = asset_map.get(html_mod.unescape(att_m.group(1)))
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

    # Code blocks (ac:name="code")
    def replace_code(m):
        body = m.group(1)
        lang_m = re.search(r'<ac:parameter[^>]*ac:name="language">([^<]+)', body)
        lang = lang_m.group(1) if lang_m else ""
        body_m = re.search(r"<ac:plain-text-body>\s*<!\[CDATA\[(.*?)\]\]>\s*</ac:plain-text-body>", body, re.DOTALL)
        code = body_m.group(1) if body_m else ""
        # Use data-code-content so ProseMirror preserves on parse
        encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
        la = f' class="language-{lang}"' if lang else ""
        return f'<pre data-code-content="{encoded}"><code{la}>​</code></pre>'

    h = re.sub(
        r'<ac:structured-macro[^>]*ac:name="code"[^>]*>(.*?)</ac:structured-macro>',
        replace_code,
        h,
        flags=re.DOTALL,
    )

    # Strip/unwrap remaining structured-macros (including toc, etc.)
    for _ in range(10):
        new = re.sub(
            r'<ac:structured-macro[^>]*>((?:(?!<ac:structured-macro).)*?)</ac:structured-macro>',
            lambda mm: (
                (rtb := re.search(r"<ac:rich-text-body>(.*)</ac:rich-text-body>", mm.group(1), re.DOTALL))
                and rtb.group(1)
                or ""
            ),
            h,
            flags=re.DOTALL,
        )
        if new == h:
            break
        h = new

    # ac:layout → pass through as divs
    h = re.sub(r"<ac:layout[^>]*>", "", h)
    h = h.replace("</ac:layout>", "")
    h = re.sub(r"<ac:layout-section[^>]*>", "", h)
    h = h.replace("</ac:layout-section>", "")
    h = re.sub(r"<ac:layout-cell[^>]*>", "", h)
    h = h.replace("</ac:layout-cell>", "")

    # Remove other stray ac:/ri: tags
    h = re.sub(r"</?ac:[a-z-]+[^>]*>", "", h)
    h = re.sub(r"</?ri:[a-z-]+[^>]*/?>", "", h)

    # Add Plane editor classes to headings and paragraphs that don't have one
    h = re.sub(r"<h([1-6])>", r'<h\1 class="' + H + r'">', h)
    h = re.sub(r"<p>", f'<p class="{P}">', h)

    return h


def main():
    if len(sys.argv) < 2:
        print("Usage: reconvert_page_with_callouts.py PAGE_UUID [--apply]")
        sys.exit(2)
    page_id = sys.argv[1]
    dry_run = "--apply" not in sys.argv

    # Build asset_map for images on this page
    from django.db import connection

    cur = connection.cursor()
    cur.execute(
        "SELECT attributes->>'name', id::text FROM file_assets "
        "WHERE entity_identifier = %s AND entity_type = 'PAGE_DESCRIPTION' AND is_uploaded = true",
        [page_id],
    )
    asset_map = {}
    for name, aid in cur.fetchall():
        if name:
            # NFC normalize + html unescape for matching
            import unicodedata

            asset_map[unicodedata.normalize("NFC", name)] = aid

    # Also pull global filename → asset_id for cross-page images
    cur.execute(
        "SELECT attributes->>'name', id::text FROM file_assets WHERE is_uploaded=true"
    )
    import unicodedata

    global_map = {}
    for name, aid in cur.fetchall():
        if name:
            global_map.setdefault(unicodedata.normalize("NFC", name), aid)

    # Merge (same-page wins)
    for k, v in global_map.items():
        asset_map.setdefault(k, v)

    page = Page.objects.get(id=page_id)
    body = load_body(int(page.external_id))
    if body is None:
        print(f"No body for ext={page.external_id}")
        sys.exit(1)

    # Step 1: info/note/tip/warning macros → callout divs (wrapping rich-text-body)
    body_cb = transform_info_macros(body)

    # Step 2: full XHTML → TipTap conversion
    html = convert_xhtml(body_cb, asset_map)

    # Remove the earlier migration footers — they may duplicate with new content
    html = re.sub(
        r"<!--\s*migration:[a-z-]+\s*-->.*?(?=<!--\s*migration:|\Z)",
        "",
        html,
        flags=re.DOTALL,
    )

    print(f"Source body: {len(body)} chars")
    print(f"New HTML:    {len(html)} chars")
    print(f"Asset map:   {len(asset_map)} entries")
    # quick checks
    print("info macros in src :", len(re.findall(r'ac:name="info"', body)))
    print("callouts in new    :", html.count('data-block-type="callout-component"'))

    if dry_run:
        print("\nDry run. Re-run with --apply.")
        return

    Page.objects.filter(id=page_id).update(
        description_html=html, description_binary=b"", updated_at=dj_timezone.now()
    )
    rc = get_redis_connection("default")
    rc.publish(
        "plane:admin",
        json.dumps(
            {
                "command": "force_close",
                "docId": page_id,
                "reason": "corruption_detected",
                "code": 4000,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ),
    )
    print("Applied.")


if __name__ == "__main__":
    main()

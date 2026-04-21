#!/usr/bin/env python3
"""Demo: for a given page, replace the existing
"リクエスト・レスポンスサンプル" footer (or add one) with Plane's
callout-component divs — one per <ac:structured-macro ac:name="info">
in the Confluence source body.

This lets the user preview how info macros render as callouts before
deciding on a wider migration strategy.

Run inside the api container:
    docker exec <api> python /tmp/inject_info_as_callout.py PAGE_UUID [--apply]
"""
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
FOOTER_MARKER = "<!-- migration:info-callouts -->"

INFO_MACRO_RE = re.compile(
    r'<ac:structured-macro[^>]*ac:name="info"[^>]*>(.*?)</ac:structured-macro>',
    re.DOTALL,
)
RICH_BODY_RE = re.compile(r"<ac:rich-text-body>(.*?)</ac:rich-text-body>", re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
PARA_SPLIT_RE = re.compile(r"</?p[^>]*>|<br\s*/?>", re.IGNORECASE)


def extract_paragraphs(info_inner: str) -> list[str]:
    m = RICH_BODY_RE.search(info_inner)
    if not m:
        return []
    body = m.group(1)
    pieces = PARA_SPLIT_RE.split(body)
    paragraphs = []
    for p in pieces:
        text = TAG_RE.sub("", p)
        text = html_mod.unescape(text).replace("\xa0", " ").strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def build_callout(paragraphs: list[str]) -> str:
    """Build Plane callout-component div."""
    # Use emoji: 💡 (lightbulb, 128161) as default
    attrs = (
        'data-block-type="callout-component" '
        'data-logo-in-use="emoji" '
        'data-emoji-unicode="128161" '
        'data-emoji-url="https://cdn.jsdelivr.net/npm/emoji-datasource-apple/img/apple/64/1f4a1.png" '
        f'id="{uuidlib.uuid4()}"'
    )
    body = "".join(
        f'<p class="editor-paragraph-block">{html_mod.escape(p)}</p>' for p in paragraphs
    )
    return f"<div {attrs}>{body}</div>"


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


def main():
    if len(sys.argv) < 2:
        print("Usage: inject_info_as_callout.py PAGE_UUID [--apply]")
        sys.exit(2)
    page_id = sys.argv[1]
    dry_run = "--apply" not in sys.argv

    page = Page.objects.get(id=page_id)
    ext_id = int(page.external_id)
    body = load_body(ext_id)
    if body is None:
        print(f"Body not found for ext_id={ext_id}", file=sys.stderr)
        sys.exit(1)

    matches = list(INFO_MACRO_RE.finditer(body))
    print(f"Found {len(matches)} info macros")

    callouts = []
    for m in matches:
        paras = extract_paragraphs(m.group(1))
        if not paras:
            continue
        callouts.append(build_callout(paras))

    if not callouts:
        print("No callout content extracted")
        return

    # Footer block to append (or replace existing)
    footer = (
        FOOTER_MARKER
        + '<div class="py-4 border-strong-1" data-type="horizontalRule"><div></div></div>'
        + '<h2 class="editor-heading-block"><strong>info ボックス（コールアウト表示プレビュー）</strong></h2>'
        + "".join(callouts)
    )

    html = page.description_html or ""
    # If previously injected, strip old block
    if FOOTER_MARKER in html:
        pattern = re.compile(
            re.escape(FOOTER_MARKER) + r'.*?(?=<!--\s*migration:|\Z)',
            re.DOTALL,
        )
        html = pattern.sub("", html)

    # Also strip the earlier api-samples code-block footer so we can
    # compare just the new callout rendering
    html = re.sub(
        r'<!--\s*migration:api-samples\s*-->.*?(?=<!--\s*migration:|\Z)',
        "",
        html,
        flags=re.DOTALL,
    )

    new_html = html + footer

    print(f"Before: {len(page.description_html or '')} chars")
    print(f"After : {len(new_html)} chars")
    print(f"Callouts: {len(callouts)}")

    if dry_run:
        print("Dry run. Re-run with --apply.")
        return

    Page.objects.filter(id=page_id).update(
        description_html=new_html, description_binary=b"", updated_at=dj_timezone.now()
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
    print("Applied + force_close sent")


if __name__ == "__main__":
    main()

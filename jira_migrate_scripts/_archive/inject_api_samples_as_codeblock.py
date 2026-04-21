#!/usr/bin/env python3
"""For API-spec pages whose Confluence source had info boxes with
URL/header/body sample data, append a code-block section listing each
sample so it's visually distinct from surrounding prose.

Run inside the api container:
    docker exec <api> python /tmp/inject_api_samples_as_codeblock.py \
        [--apply] [PAGE_UUID [PAGE_UUID...]]

If page UUIDs are supplied, only those are processed. Otherwise the
script auto-detects pages whose source body contains info-macros with
the "URL：" / "ボディ：" keywords.
"""
import html as html_module
import json
import os
import re
import sys
from datetime import datetime, timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.production")
sys.path.insert(0, "/code")

import django  # noqa: E402

django.setup()

from django.utils import timezone as dj_timezone  # noqa: E402
from django_redis import get_redis_connection  # noqa: E402

from plane.db.models import Page  # noqa: E402

CONF_JSONL = os.environ.get("CONFLUENCE_JSONL", "/tmp/confluence_pages.jsonl")
FOOTER_MARKER = "<!-- migration:api-samples -->"

INFO_MACRO_RE = re.compile(
    r'<ac:structured-macro[^>]*ac:name="info"[^>]*>(.*?)</ac:structured-macro>',
    re.DOTALL,
)
RICH_BODY_RE = re.compile(r'<ac:rich-text-body>(.*?)</ac:rich-text-body>', re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
PARA_SPLIT_RE = re.compile(r"</?p[^>]*>|<br\s*/?>", re.IGNORECASE)


def extract_sample_text(info_inner: str) -> str:
    m = RICH_BODY_RE.search(info_inner)
    if not m:
        return ""
    body = m.group(1)
    # Split into lines on <p>/<br>, strip remaining tags, unescape HTML
    pieces = PARA_SPLIT_RE.split(body)
    lines = []
    for p in pieces:
        p = TAG_RE.sub("", p)
        p = html_module.unescape(p)
        p = p.replace("\xa0", " ").strip()
        if p:
            lines.append(p)
    return "\n".join(lines)


def load_page_source(page_id_to_ext: dict):
    ext_ids = {int(v): k for k, v in page_id_to_ext.items() if v}
    found = {}
    with open(CONF_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            cid = d.get("id")
            if cid in ext_ids:
                found[ext_ids[cid]] = d.get("body", "")
                if len(found) == len(ext_ids):
                    break
    return found


def build_codeblock_footer(samples: list[str]) -> str:
    if not samples:
        return ""
    parts = [
        FOOTER_MARKER,
        '<div class="py-4 border-strong-1" data-type="horizontalRule"><div></div></div>',
        '<h2 class="editor-heading-block"><strong>リクエスト・レスポンスサンプル</strong></h2>',
    ]
    for i, s in enumerate(samples, 1):
        escaped = html_module.escape(s)
        parts.append(
            f'<p class="editor-paragraph-block"><strong>サンプル {i}</strong></p>'
            f'<pre class="editor-code-block"><code>{escaped}</code></pre>'
        )
    return "".join(parts)


def main():
    args = [a for a in sys.argv[1:] if a != "--apply"]
    dry_run = "--apply" not in sys.argv

    qs = Page.objects.filter(external_source="confluence", deleted_at__isnull=True).exclude(
        external_id__isnull=True
    )
    if args:
        qs = qs.filter(id__in=args)

    page_id_to_ext = {str(p.id): p.external_id for p in qs.only("id", "external_id")}
    if not page_id_to_ext:
        print("No matching pages.")
        return
    print(f"Target pages: {len(page_id_to_ext)}")

    bodies = load_page_source(page_id_to_ext)
    print(f"Loaded {len(bodies)} confluence source bodies")

    updated = []
    for page_id, ext_id in page_id_to_ext.items():
        body = bodies.get(page_id)
        if not body:
            continue
        samples = []
        for m in INFO_MACRO_RE.finditer(body):
            inner = m.group(1)
            text = extract_sample_text(inner)
            if not text:
                continue
            # Heuristic: only info boxes that look like API request/response
            if not any(kw in text for kw in ("URL：", "ボディ：", "ヘッダ：", "email=", "https://")):
                continue
            samples.append(text)
        if not samples:
            continue

        page = Page.objects.get(id=page_id)
        html = page.description_html or ""
        if FOOTER_MARKER in html:
            print(f"{page_id}: already has api-samples footer, skip")
            continue
        footer = build_codeblock_footer(samples)
        new_html = html + footer
        updated.append((page_id, new_html, len(samples)))
        print(f"{page_id}: {len(samples)} sample(s) -> +{len(footer)} chars")

    print(f"\n{'Would update' if dry_run else 'Updated'} {len(updated)} pages")
    if dry_run:
        return

    for page_id, new_html, n in updated:
        Page.objects.filter(id=page_id).update(
            description_html=new_html, description_binary=b"", updated_at=dj_timezone.now()
        )

    rc = get_redis_connection("default")
    ts = datetime.now(timezone.utc).isoformat()
    recv = 0
    for page_id, _, _ in updated:
        recv += rc.publish(
            "plane:admin",
            json.dumps(
                {
                    "command": "force_close",
                    "docId": page_id,
                    "reason": "corruption_detected",
                    "code": 4000,
                    "timestamp": ts,
                }
            ),
        )
    print(f"force_close receivers total: {recv}")


if __name__ == "__main__":
    main()

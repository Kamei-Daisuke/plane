#!/usr/bin/env python3
"""Remove footer attachment <li> entries that point to the same asset
as an existing inline <image-component>. Non-image attachments
(xlsx, pdf, docx, etc.) and gliffy source files stay in the footer.

For each page:
  1. Collect asset UUIDs that appear inside <image-component src="...">.
  2. For each footer <li><a href="/api/assets/v2/workspaces/keis/<UUID>/">
     NAME</a></li>, if UUID is in the inline set, remove that <li>.
  3. If a footer section becomes empty, drop the whole heading + hr + ul.

Run inside the api container:
    docker exec <api> python /tmp/dedupe_footer_vs_inline.py [--apply]
"""
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.production")
sys.path.insert(0, "/code")

import django  # noqa: E402

django.setup()

from django.utils import timezone as dj_timezone  # noqa: E402
from django_redis import get_redis_connection  # noqa: E402

from plane.db.models import Page  # noqa: E402


IMAGE_COMP_SRC_RE = re.compile(
    r'image-component[^>]*src="(?:https?://[^"]+/)?([0-9a-f-]{36})/?"'
)

LI_RE = re.compile(
    r'<li[^>]*>.*?<a[^>]*href="/api/assets/v2/workspaces/keis/([0-9a-f-]{36})/"[^>]*>[^<]*</a>.*?</li>',
    re.DOTALL,
)

FOOTER_BLOCK_RE = re.compile(
    r'(?:<!--\s*migration:[a-z-]+\s*-->)?'
    r'\s*<div[^>]*horizontalRule[^>]*><div></div></div>'
    r'\s*<h2[^>]*>\s*<strong>\s*(?:添付ファイル（移行時に復元）|移行時に復元された画像・添付)\s*</strong>\s*</h2>'
    r'\s*<ul[^>]*>(.*?)</ul>',
    re.DOTALL,
)


def main():
    dry_run = "--apply" not in sys.argv

    qs = Page.objects.filter(deleted_at__isnull=True).only("id", "description_html")

    updates = []
    stats = defaultdict(int)

    for page in qs.iterator(chunk_size=500):
        html = page.description_html or ""
        if "<image-component" not in html:
            continue
        if "migration:" not in html and "添付ファイル" not in html and "移行時に復元" not in html:
            continue

        inline_uuids = set(IMAGE_COMP_SRC_RE.findall(html))
        if not inline_uuids:
            continue

        removed_here = [0]

        def rewrite_block(m):
            full_block = m.group(0)
            ul_inner = m.group(1)

            def filter_li(li_match):
                uuid_ = li_match.group(1)
                if uuid_ in inline_uuids:
                    removed_here[0] += 1
                    return ""
                return li_match.group(0)

            kept_inner = LI_RE.sub(filter_li, ul_inner).strip()
            if not kept_inner:
                return ""
            return full_block.replace(ul_inner, kept_inner)

        new_html = FOOTER_BLOCK_RE.sub(rewrite_block, html)
        if removed_here[0] > 0 and new_html != html:
            updates.append((str(page.id), new_html, removed_here[0]))
            stats["pages"] += 1
            stats["li_removed"] += removed_here[0]

    print("Stats:", file=sys.stderr)
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}", file=sys.stderr)
    print(f"\n{'Would update' if dry_run else 'Updating'} {len(updates)} pages", file=sys.stderr)

    if dry_run:
        for pid, _, n in updates[:5]:
            print(f"  {pid}: -{n}", file=sys.stderr)
        if len(updates) > 5:
            print(f"  ... and {len(updates)-5} more", file=sys.stderr)
        return

    for pid, new_html, _ in updates:
        Page.objects.filter(id=pid).update(
            description_html=new_html, description_binary=b"", updated_at=dj_timezone.now()
        )

    rc = get_redis_connection("default")
    ts = datetime.now(timezone.utc).isoformat()
    recv = 0
    for pid, _, _ in updates:
        recv += rc.publish(
            "plane:admin",
            json.dumps(
                {"command": "force_close", "docId": pid, "reason": "corruption_detected",
                 "code": 4000, "timestamp": ts}
            ),
        )
    print(f"force_close receivers total: {recv}", file=sys.stderr)


if __name__ == "__main__":
    main()

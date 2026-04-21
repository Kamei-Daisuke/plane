#!/usr/bin/env python3
"""Re-encode <pre><code> blocks with data-code-content base64 so that
Plane's sanitizeCodeBlocks()-equivalent recovery path preserves the
content when HTML is converted to Y.js.

Without this attr ProseMirror's DOMParser collapses `\\n\\n` inside
the <pre> into paragraph boundaries and the code content is lost in
the Y.Doc.

Run inside the api container:
    docker exec <api> python /tmp/fix_code_blocks_binary_safe.py [--apply] [PAGE_UUID ...]
"""
import base64
import html as html_mod
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

PRE_RE = re.compile(r"<pre\b([^>]*)>(.*?)</pre>", re.DOTALL)


def fix_pre_tag(match: re.Match) -> str:
    attrs = match.group(1)
    inner = match.group(2)

    # Already has data-code-content: don't touch
    if "data-code-content" in attrs:
        return match.group(0)

    # Extract text from the <code>…</code> if present, otherwise whole inner
    code_match = re.search(r"<code[^>]*>(.*?)</code>", inner, re.DOTALL)
    text_html = code_match.group(1) if code_match else inner
    text = html_mod.unescape(re.sub(r"<[^>]+>", "", text_html))

    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")

    new_attrs = (attrs or "") + f' data-code-content="{encoded}"'
    # Replace inner text with zero-width space placeholder so DOMParser
    # does not split on \n\n. Preserve the <code> wrapper.
    if code_match:
        new_inner = inner.replace(code_match.group(0), f"<code>​</code>")
    else:
        new_inner = "​"
    return f"<pre{new_attrs}>{new_inner}</pre>"


def main():
    dry_run = "--apply" not in sys.argv
    target_ids = [a for a in sys.argv[1:] if a != "--apply"]

    qs = Page.objects.filter(deleted_at__isnull=True).only("id", "description_html")
    if target_ids:
        qs = qs.filter(id__in=target_ids)

    updates = []
    stats = defaultdict(int)

    for page in qs.iterator(chunk_size=500):
        html = page.description_html or ""
        if "<pre" not in html:
            continue
        if "data-code-content=" in html:
            # Already fixed or has mixed; we still want to encode the
            # ones that lack the attr. fix_pre_tag already skips those.
            pass
        new_html, n = PRE_RE.subn(fix_pre_tag, html)
        # subn counts ALL matches; count actual replacements only
        actual = sum(
            1
            for m in PRE_RE.finditer(html)
            if "data-code-content" not in m.group(1)
        )
        if actual == 0 or new_html == html:
            continue
        updates.append((str(page.id), new_html, actual))
        stats["pages"] += 1
        stats["pre_tags_encoded"] += actual

    print("Stats:")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")
    print(f"\n{'Would update' if dry_run else 'Updating'} {len(updates)} pages")

    if dry_run:
        for pid, _, n in updates[:5]:
            print(f"  {pid}: +{n} attrs")
        if len(updates) > 5:
            print(f"  ... and {len(updates)-5} more")
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
    print(f"force_close receivers total: {recv}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Restore description_html for listed page UUIDs from /tmp/restore_<uuid>.html.

Clears description_binary and force-closes live editors.
"""
import json
import os
import sys
from datetime import datetime, timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.production")
sys.path.insert(0, "/code")

import django  # noqa: E402

django.setup()

from django.utils import timezone as dj_timezone  # noqa: E402
from django_redis import get_redis_connection  # noqa: E402

from plane.db.models import Page  # noqa: E402


def main():
    ids = sys.argv[1:]
    if not ids:
        print("Usage: restore_pages_from_files.py UUID1 UUID2 ...", file=sys.stderr)
        sys.exit(2)

    for pid in ids:
        path = f"/tmp/restore_{pid}.html"
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        n = Page.objects.filter(id=pid).update(
            description_html=html, description_binary=b"", updated_at=dj_timezone.now()
        )
        print(f"{pid}: {len(html)} chars -> updated {n} row")

    rc = get_redis_connection("default")
    ts = datetime.now(timezone.utc).isoformat()
    for pid in ids:
        cmd = {
            "command": "force_close",
            "docId": pid,
            "reason": "corruption_detected",
            "code": 4000,
            "timestamp": ts,
        }
        n = rc.publish("plane:admin", json.dumps(cmd))
        print(f"force_close {pid}: receivers={n}")


if __name__ == "__main__":
    main()

"""Force-close Hocuspocus connections so connected browsers drop their
in-memory Y.js state and reload.

Without this, after a bulk reimport the clients merge their stale Y.Doc back
into the server document, re-bloating it.

Run inside the API container's Django shell:

    # All non-deleted pages
    cat jira_migrate_scripts/force_close_all_pages.py | \
      docker exec -i compose-parse-auxiliary-protocol-dxi2hz-api-1 \
      python manage.py shell

    # Specific page IDs (set env var before piping)
    docker exec -e PAGE_IDS=<id1>,<id2> -i compose-parse-auxiliary-protocol-dxi2hz-api-1 \
      python manage.py shell < jira_migrate_scripts/force_close_all_pages.py

The Live service must be running so ForceCloseHandler picks up the Redis
message. Pages not currently loaded in memory on any Live node are ignored.
"""
import json
import os
from datetime import datetime, timezone

from django.db import connection
from django_redis import get_redis_connection


ADMIN_CHANNEL = "hocuspocus:admin"


def main():
    env_ids = os.environ.get("PAGE_IDS", "").strip()
    if env_ids:
        page_ids = [pid.strip() for pid in env_ids.split(",") if pid.strip()]
        print(f"Targeting {len(page_ids)} page(s) from PAGE_IDS env")
    else:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM pages WHERE deleted_at IS NULL")
        page_ids = [str(row[0]) for row in cursor.fetchall()]
        print(f"Targeting all {len(page_ids)} non-deleted pages")

    redis_client = get_redis_connection("default")
    timestamp = datetime.now(timezone.utc).isoformat()

    total_receivers = 0
    for pid in page_ids:
        cmd = {
            "command": "force_close",
            "docId": pid,
            "reason": "corruption_detected",
            "code": 4000,
            "originServer": "migration-script",
            "timestamp": timestamp,
        }
        receivers = redis_client.publish(ADMIN_CHANNEL, json.dumps(cmd))
        total_receivers += receivers

    print(
        f"Published force_close for {len(page_ids)} page(s); "
        f"{total_receivers} total Live subscribers received the messages"
    )


main()

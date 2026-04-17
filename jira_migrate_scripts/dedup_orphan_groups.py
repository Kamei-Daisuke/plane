"""Keep one representative per (name, size) group inside the orphan
pool and delete the rest.

After `delete_duplicate_orphans.py` removed orphans that shadowed a
non-orphan, the remaining orphans still contain many groups where the
exact same file was uploaded multiple times without any non-orphan
partner. This second pass dedupes within the orphan pool.

Safety rules per group:
  - Pick the orphan with the lexicographically smallest asset id as the
    representative (deterministic).
  - HEAD every non-representative and verify its ETag matches the
    representative's. Skip the one if it differs.
  - Delete the S3 object first, then the DB row.

Singleton groups (cnt == 1) are left alone.

Env:
  DRY_RUN=1  Report without touching anything.
"""
import os

import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from django.db import connection, transaction


DRY_RUN = os.environ.get("DRY_RUN", "") in ("1", "true", "yes")


def get_s3():
    return boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )


def bucket_name():
    return (
        os.environ.get("AWS_S3_BUCKET_NAME")
        or getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)
        or getattr(settings, "AWS_S3_BUCKET_NAME", None)
    )


def main():
    print(f"DRY_RUN={DRY_RUN}")

    cursor = connection.cursor()
    s3 = get_s3()
    bucket = bucket_name()
    if not bucket:
        raise RuntimeError("bucket not configured")
    print(f"bucket: {bucket}")

    cursor.execute("""
        WITH orphans AS (
            SELECT id, asset,
                   attributes->>'name' AS name,
                   (attributes->>'size')::bigint AS size
            FROM file_assets
            WHERE deleted_at IS NULL AND (
              (entity_type='PAGE_DESCRIPTION' AND page_id IS NULL) OR
              (entity_type='ISSUE_ATTACHMENT' AND issue_id IS NULL) OR
              (entity_type='COMMENT_DESCRIPTION' AND comment_id IS NULL)
            )
        )
        SELECT name, size, array_agg(id::text ORDER BY id), array_agg(asset ORDER BY id)
        FROM orphans
        GROUP BY name, size
        HAVING COUNT(*) > 1
        ORDER BY SUM(size) DESC
    """)
    groups = cursor.fetchall()
    print(f"Duplicate orphan groups: {len(groups)}")

    deleted = 0
    etag_mismatch = 0
    head_errors = 0
    s3_errors = 0
    saved_bytes = 0
    groups_done = 0

    for name, size, ids, keys in groups:
        groups_done += 1
        rep_key = keys[0]
        try:
            rep_head = s3.head_object(Bucket=bucket, Key=rep_key)
        except ClientError as exc:
            head_errors += 1
            if head_errors <= 5:
                print(f"  head rep FAIL {ids[0]} -> {exc}")
            continue
        rep_etag = rep_head.get("ETag", "").strip('"')

        for idx in range(1, len(ids)):
            dup_id = ids[idx]
            dup_key = keys[idx]
            try:
                dup_head = s3.head_object(Bucket=bucket, Key=dup_key)
            except ClientError as exc:
                head_errors += 1
                if head_errors <= 5:
                    print(f"  head dup FAIL {dup_id} -> {exc}")
                continue
            dup_etag = dup_head.get("ETag", "").strip('"')
            if not dup_etag or dup_etag != rep_etag:
                etag_mismatch += 1
                if etag_mismatch <= 5:
                    print(f"  etag mismatch {dup_id} vs {ids[0]} ({name})")
                continue

            if DRY_RUN:
                deleted += 1
                saved_bytes += int(size or 0)
                continue

            try:
                s3.delete_object(Bucket=bucket, Key=dup_key)
            except ClientError as exc:
                s3_errors += 1
                if s3_errors <= 5:
                    print(f"  s3 delete FAIL {dup_id} -> {exc}")
                continue
            cursor.execute("DELETE FROM file_assets WHERE id = %s", [dup_id])
            deleted += 1
            saved_bytes += int(size or 0)

            if deleted % 500 == 0:
                print(f"  ... deleted {deleted}  groups {groups_done}/{len(groups)}  saved={saved_bytes/1024/1024:.1f} MiB")

    print("\n=== Summary ===")
    print(f"  groups processed: {groups_done}")
    print(f"  deleted: {deleted}")
    print(f"  saved: {saved_bytes/1024/1024:.1f} MiB")
    print(f"  etag mismatches: {etag_mismatch}")
    print(f"  head errors: {head_errors}")
    print(f"  s3 errors: {s3_errors}")


with transaction.atomic():
    main()
    if DRY_RUN:
        transaction.set_rollback(True)

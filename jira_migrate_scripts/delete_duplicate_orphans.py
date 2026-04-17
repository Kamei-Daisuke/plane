"""Delete orphan file_assets that are byte-identical duplicates of a
non-orphan (properly-attached) asset.

Safety criteria applied per orphan:
  - entity_type is PAGE_DESCRIPTION/ISSUE_ATTACHMENT/COMMENT_DESCRIPTION
    AND the respective FK (page_id/issue_id/comment_id) is NULL
  - There is at least one NON-orphan file_asset with identical
    attributes.name + attributes.size
  - The S3/OCI ETag (MD5 for single-part uploads) of the orphan object
    matches the non-orphan's ETag exactly.

If any of those fails, leave the orphan alone. We hard-delete the DB row
only after the S3 object is removed, so a row is never left pointing at
a deleted blob.

Env:
  DRY_RUN=1  Report what would be deleted without touching storage.
  LIMIT=N    Stop after N deletions (useful for a first smoke pass).
"""
import os

import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from django.db import connection, transaction


DRY_RUN = os.environ.get("DRY_RUN", "") in ("1", "true", "yes")
LIMIT = int(os.environ.get("LIMIT", "0") or 0)


def get_s3_client():
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
    print(f"DRY_RUN={DRY_RUN}  LIMIT={LIMIT or 'unlimited'}")

    cursor = connection.cursor()
    s3 = get_s3_client()
    bucket = bucket_name()
    if not bucket:
        raise RuntimeError("No S3 bucket configured")
    print(f"Bucket: {bucket}")

    # For each orphan, join to a non-orphan with same name+size. Prefer
    # the deterministically smallest non-orphan id so we always compare
    # against the same partner for a given (name, size).
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
        ),
        non_orphans AS (
            SELECT DISTINCT ON (name, size)
                id AS nonorphan_id,
                asset AS nonorphan_asset,
                attributes->>'name' AS name,
                (attributes->>'size')::bigint AS size
            FROM file_assets
            WHERE deleted_at IS NULL AND NOT (
              (entity_type='PAGE_DESCRIPTION' AND page_id IS NULL) OR
              (entity_type='ISSUE_ATTACHMENT' AND issue_id IS NULL) OR
              (entity_type='COMMENT_DESCRIPTION' AND comment_id IS NULL)
            )
            ORDER BY name, size, id
        )
        SELECT o.id, o.asset, n.nonorphan_id, n.nonorphan_asset, o.name, o.size
        FROM orphans o
        JOIN non_orphans n ON n.name = o.name AND n.size = o.size
        ORDER BY o.id
    """)
    rows = cursor.fetchall()
    print(f"Candidate duplicate orphans: {len(rows)}")

    deleted = 0
    etag_mismatch = 0
    head_errors = 0
    s3_delete_errors = 0
    processed = 0
    saved_bytes = 0

    for orphan_id, orphan_key, nonorphan_id, nonorphan_key, name, size in rows:
        processed += 1
        if LIMIT and deleted >= LIMIT:
            print(f"Hit LIMIT={LIMIT}, stopping.")
            break

        # Verify both objects still exist and their ETags match.
        try:
            orphan_head = s3.head_object(Bucket=bucket, Key=orphan_key)
        except ClientError as exc:
            head_errors += 1
            if head_errors <= 5:
                print(f"  head orphan FAIL {orphan_id} -> {exc}")
            continue

        try:
            nonorphan_head = s3.head_object(Bucket=bucket, Key=nonorphan_key)
        except ClientError as exc:
            head_errors += 1
            if head_errors <= 5:
                print(f"  head nonorphan FAIL {nonorphan_id} -> {exc}")
            continue

        orphan_etag = orphan_head.get("ETag", "").strip('"')
        nonorphan_etag = nonorphan_head.get("ETag", "").strip('"')
        if not orphan_etag or orphan_etag != nonorphan_etag:
            etag_mismatch += 1
            if etag_mismatch <= 5:
                print(
                    f"  etag mismatch {orphan_id}  orphan={orphan_etag[:12]}"
                    f"  nonorphan={nonorphan_etag[:12]}  name={name}"
                )
            continue

        if DRY_RUN:
            deleted += 1
            saved_bytes += int(size or 0)
            continue

        try:
            s3.delete_object(Bucket=bucket, Key=orphan_key)
        except ClientError as exc:
            s3_delete_errors += 1
            if s3_delete_errors <= 5:
                print(f"  s3 delete FAIL {orphan_id} -> {exc}")
            continue

        cursor.execute("DELETE FROM file_assets WHERE id = %s", [str(orphan_id)])
        deleted += 1
        saved_bytes += int(size or 0)

        if deleted % 500 == 0:
            print(f"  ... deleted {deleted} / {len(rows)}  saved={saved_bytes/1024/1024:.1f} MiB")

    print("\n=== Summary ===")
    print(f"  processed: {processed}")
    print(f"  deleted: {deleted}")
    print(f"  saved: {saved_bytes/1024/1024:.1f} MiB")
    print(f"  etag mismatches (skipped): {etag_mismatch}")
    print(f"  head errors (skipped): {head_errors}")
    print(f"  s3 delete errors: {s3_delete_errors}")


with transaction.atomic():
    main()
    if DRY_RUN:
        transaction.set_rollback(True)

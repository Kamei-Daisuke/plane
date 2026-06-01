#!/usr/bin/env python3
"""Upload orphan Confluence attachments (missed during migration) to Plane as
PAGE_DESCRIPTION file assets, so the page's view-file macros resolve to a real
download link on re-conversion.

Reads /tmp/upload_meta.json: [{"name":..,"page_id":..,"mime":..,"b64":..}, ...]
where name is the exact ri:filename from the Confluence body (so reconvert's
NFC-normalized lookup matches). Idempotent: skips if an asset with the same
name already exists on the page.

Run inside the API container:
  docker cp upload_meta.json <api>:/tmp/ && docker cp upload_orphan_assets.py <api>:/tmp/
  docker exec <api> python /tmp/upload_orphan_assets.py
"""
import base64
import json
import os
import sys
import uuid

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.production")
sys.path.insert(0, "/code")
import django  # noqa: E402

django.setup()

import boto3  # noqa: E402
from django.conf import settings  # noqa: E402

from plane.db.models import FileAsset, Page, Workspace  # noqa: E402


def safe(s):
    return str(s).encode("ascii", "backslashreplace").decode()


meta = json.load(open("/tmp/upload_meta.json", encoding="utf-8"))
ws = Workspace.objects.get(slug=os.environ.get("WORKSPACE_SLUG", "keis"))
s3 = boto3.client(
    "s3",
    endpoint_url=getattr(settings, "AWS_S3_ENDPOINT_URL", None),
    aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
    aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
    region_name=getattr(settings, "AWS_REGION", None) or "us-east-1",
)
bucket = getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)

for item in meta:
    name = item["name"]
    page_id = item["page_id"]
    mime = item["mime"]
    data = base64.b64decode(item["b64"])
    existing = FileAsset.objects.filter(
        entity_identifier=page_id,
        entity_type="PAGE_DESCRIPTION",
        attributes__name=name,
        is_uploaded=True,
    ).first()
    if existing:
        print("SKIP (exists)", safe(name), existing.id)
        continue
    page = Page.objects.get(id=page_id)
    aid = uuid.uuid4()
    key = f"{ws.id}/{aid}-{name}"
    s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=mime)
    FileAsset.objects.create(
        id=aid,
        workspace=ws,
        page=page,
        entity_type="PAGE_DESCRIPTION",
        entity_identifier=page_id,
        attributes={"name": name, "size": len(data), "type": mime},
        asset=key,
        size=float(len(data)),
        is_uploaded=True,
    )
    print("UPLOADED", aid, len(data), "bytes", safe(name))

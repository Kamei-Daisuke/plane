#!/usr/bin/env python3
"""Bulk re-convert: for every page whose Confluence body contains an
info/note/tip/warning macro, re-generate Plane TipTap HTML with those
macros rendered as callout-component divs in their original position.

Strategy mirrors reconvert_page_with_callouts.py but iterates
across all pages loaded from /tmp/conf_bodies_latest.tsv.

Deploy sequence (run from the docker host, not inside the container):
    sudo docker stop compose-parse-auxiliary-protocol-dxi2hz-live-1
    sudo docker exec compose-parse-auxiliary-protocol-dxi2hz-plane-redis-1 valkey-cli FLUSHALL
    sudo docker cp ...py compose-...-api-1:/tmp/
    sudo docker exec compose-...-api-1 python /tmp/reconvert_pages_with_callouts_bulk.py --apply
    sudo docker start compose-parse-auxiliary-protocol-dxi2hz-live-1
"""
import base64
import html as html_mod
import json
import os
import re
import sys
import unicodedata
import uuid as uuidlib
from collections import defaultdict
from datetime import datetime, timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.production")
sys.path.insert(0, "/code")

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402
from django.utils import timezone as dj_timezone  # noqa: E402
from django_redis import get_redis_connection  # noqa: E402

from plane.db.models import Page  # noqa: E402


CONF = os.environ.get("CONFLUENCE_BODIES", "/tmp/conf_bodies_latest.tsv")
PLANE_BASE = os.environ.get("PLANE_BASE", "https://plane.keis-software.com")
WORKSPACE_SLUG = os.environ.get("WORKSPACE_SLUG", "keis")

P_CLASS = "editor-paragraph-block"
H_CLASS = "editor-heading-block"


def norm(s):
    return unicodedata.normalize("NFC", s) if s else s


def make_callout_open(icon_unicode="128161"):
    return (
        f'<div data-block-type="callout-component" data-logo-in-use="emoji" '
        f'data-emoji-unicode="{icon_unicode}" '
        f'data-emoji-url="https://cdn.jsdelivr.net/npm/emoji-datasource-apple/img/apple/64/1f4a1.png" '
        f'id="{uuidlib.uuid4()}">'
    )


def transform_info_macros(body: str) -> str:
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


def convert_xhtml(xhtml: str, asset_map: dict) -> str:
    h = xhtml

    def replace_image(m):
        content = m.group(0)
        att_m = re.search(r'ri:attachment\s+ri:filename="([^"]*)"', content)
        url_m = re.search(r'ri:url\s+ri:value="([^"]*)"', content)
        if att_m:
            aid = asset_map.get(norm(html_mod.unescape(att_m.group(1))))
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

    def replace_code(m):
        body = m.group(1)
        lang_m = re.search(r'<ac:parameter[^>]*ac:name="language">([^<]+)', body)
        lang = lang_m.group(1) if lang_m else ""
        body_m = re.search(
            r"<ac:plain-text-body>\s*<!\[CDATA\[(.*?)\]\]>\s*</ac:plain-text-body>",
            body,
            re.DOTALL,
        )
        code = body_m.group(1) if body_m else ""
        encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
        la = f' class="language-{lang}"' if lang else ""
        return f'<pre data-code-content="{encoded}"><code{la}>​</code></pre>'

    h = re.sub(
        r'<ac:structured-macro[^>]*ac:name="code"[^>]*>(.*?)</ac:structured-macro>',
        replace_code,
        h,
        flags=re.DOTALL,
    )

    # Strip/unwrap remaining structured-macros (including toc)
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

    # ac:layout pass-through
    h = re.sub(r"<ac:layout[^>]*>", "", h)
    h = h.replace("</ac:layout>", "")
    h = re.sub(r"<ac:layout-section[^>]*>", "", h)
    h = h.replace("</ac:layout-section>", "")
    h = re.sub(r"<ac:layout-cell[^>]*>", "", h)
    h = h.replace("</ac:layout-cell>", "")

    # Drop stray ac:/ri:
    h = re.sub(r"</?ac:[a-z-]+[^>]*>", "", h)
    h = re.sub(r"</?ri:[a-z-]+[^>]*/?>", "", h)

    # Add editor classes
    h = re.sub(r"<h([1-6])>", r'<h\1 class="' + H_CLASS + r'">', h)
    h = re.sub(r"<p>", f'<p class="{P_CLASS}">', h)

    return h


def main():
    dry_run = "--apply" not in sys.argv

    # Asset map (global, NFC-normalized filename → first asset_id)
    cur = connection.cursor()
    cur.execute("SELECT id::text, attributes->>'name' FROM file_assets WHERE is_uploaded=true")
    asset_map = {}
    for aid, name in cur.fetchall():
        if not name:
            continue
        asset_map.setdefault(norm(name), aid)
    print(f"Loaded {len(asset_map)} filename → asset_id entries", file=sys.stderr)

    # Plane confluence pages: external_id → page_id
    cur.execute(
        "SELECT id::text, external_id FROM pages "
        "WHERE external_source='confluence' AND deleted_at IS NULL AND external_id IS NOT NULL"
    )
    ext_to_plane = {}
    for pid, ext in cur.fetchall():
        try:
            ext_to_plane[int(ext)] = pid
        except (TypeError, ValueError):
            continue
    print(f"Loaded {len(ext_to_plane)} confluence→plane page ids", file=sys.stderr)

    # Iterate bodies
    updates = []
    stats = defaultdict(int)
    HAS_INFO = re.compile(r'ac:name="(info|note|tip|warning)"')

    with open(CONF, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 2:
                continue
            try:
                ext = int(parts[0])
                body = bytes.fromhex(parts[1]).decode("utf-8", errors="replace")
            except Exception:
                stats["decode_error"] += 1
                continue

            if not HAS_INFO.search(body):
                continue

            page_id = ext_to_plane.get(ext)
            if not page_id:
                stats["no_plane_page"] += 1
                continue

            body_cb = transform_info_macros(body)
            new_html = convert_xhtml(body_cb, asset_map)
            # Drop legacy migration footer markers and their content
            new_html = re.sub(
                r"<!--\s*migration:[a-z-]+\s*-->.*?(?=<!--\s*migration:|\Z)",
                "",
                new_html,
                flags=re.DOTALL,
            )

            callout_count = new_html.count('data-block-type="callout-component"')
            if callout_count == 0:
                stats["no_callouts_produced"] += 1
                continue
            updates.append((page_id, new_html, callout_count))
            stats["pages"] += 1
            stats["callouts"] += callout_count

    print("Stats:", file=sys.stderr)
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}", file=sys.stderr)
    print(f"\n{'Would update' if dry_run else 'Updating'} {len(updates)} pages", file=sys.stderr)

    if dry_run:
        for pid, _, n in updates[:5]:
            print(f"  {pid}: {n} callouts", file=sys.stderr)
        if len(updates) > 5:
            print(f"  ... and {len(updates)-5} more", file=sys.stderr)
        return

    for i, (pid, new_html, _) in enumerate(updates, 1):
        Page.objects.filter(id=pid).update(
            description_html=new_html,
            description_binary=b"",
            updated_at=dj_timezone.now(),
        )
        if i % 200 == 0:
            print(f"  ...updated {i}/{len(updates)}", file=sys.stderr)
    print(f"Applied {len(updates)} page updates", file=sys.stderr)

    rc = get_redis_connection("default")
    ts = datetime.now(timezone.utc).isoformat()
    recv = 0
    for pid, _, _ in updates:
        recv += rc.publish(
            "plane:admin",
            json.dumps(
                {
                    "command": "force_close",
                    "docId": pid,
                    "reason": "corruption_detected",
                    "code": 4000,
                    "timestamp": ts,
                }
            ),
        )
    print(f"force_close receivers total: {recv}", file=sys.stderr)


if __name__ == "__main__":
    main()

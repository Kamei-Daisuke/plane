#!/bin/bash
# Confluence ページ一括再インポート
# Usage: bash jira_migrate_scripts/reimport_pages.sh
#
# 前提:
#   - jira_migrate_scripts/data/confluence_pages.jsonl (Confluence DBダンプ)
#   - jira_migrate_scripts/data/page_map.json (confluence_id -> plane_id)
#   - jira_migrate_scripts/data/page_asset_map.json (filename -> FileAsset ID)
#   - packages/editor/dist/lib.js (ビルド済み)
#   - SSH alias "oci" が使える
#
# やること:
#   1. Python: Confluence XHTML → TipTap HTML 変換 (page_final.jsonl)
#   2. Node.js: HTML → Y.js binary 生成 (page_binaries.jsonl)
#   3. サーバ: live 停止 → Redis フラッシュ → HTML 更新 → binary 更新 → live 起動

set -e
cd "$(dirname "$0")/.."

echo "=== Step 1: Convert Confluence → TipTap HTML ==="
python3 jira_migrate_scripts/convert_final.py

echo ""
echo "=== Step 2: Generate Y.js binaries ==="
node jira_migrate_scripts/gen_binaries_final.js

echo ""
echo "=== Step 3: Transfer to server ==="
scp jira_migrate_scripts/data/page_final.jsonl jira_migrate_scripts/data/page_binaries.jsonl oci:/tmp/

echo ""
echo "=== Step 4: Stop live, flush Redis ==="
ssh oci "sudo docker stop compose-parse-auxiliary-protocol-dxi2hz-live-1 2>/dev/null; sudo docker exec compose-parse-auxiliary-protocol-dxi2hz-plane-redis-1 valkey-cli FLUSHALL"

echo ""
echo "=== Step 5: Update HTML in DB ==="
ssh oci "sudo docker cp /tmp/page_final.jsonl compose-parse-auxiliary-protocol-dxi2hz-api-1:/tmp/page_updates_tiptap_fixed.jsonl"
ssh oci "sudo docker exec compose-parse-auxiliary-protocol-dxi2hz-api-1 python manage.py shell -c \"exec(open('/tmp/update_html_fixed.py').read())\""

echo ""
echo "=== Step 6: Update binaries in DB ==="
ssh oci "sudo docker cp /tmp/page_binaries.jsonl compose-parse-auxiliary-protocol-dxi2hz-api-1:/tmp/"
ssh oci "sudo docker exec compose-parse-auxiliary-protocol-dxi2hz-api-1 python manage.py shell -c \"exec(open('/tmp/import_binaries.py').read())\""

echo ""
echo "=== Step 7: Start live ==="
ssh oci "sudo docker start compose-parse-auxiliary-protocol-dxi2hz-live-1"

echo ""
echo "=== Done ==="
echo "ブラウザのサイトデータ (plane.example.com) を削除してから確認してください"

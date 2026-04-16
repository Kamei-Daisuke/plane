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
echo "=== Step 2.5: Verify binary roundtrip ==="
node jira_migrate_scripts/verify_pages.js
if [ $? -ne 0 ]; then
  echo "ERROR: Content loss detected. Aborting."
  exit 1
fi

echo ""
echo "=== Step 3: Transfer to server ==="
scp jira_migrate_scripts/data/page_final.jsonl jira_migrate_scripts/data/page_binaries.jsonl oci:/tmp/

echo ""
echo "=== Step 4: Stop live, flush Redis ==="
ssh oci "sudo docker stop compose-parse-auxiliary-protocol-dxi2hz-live-1 2>/dev/null; sudo docker exec compose-parse-auxiliary-protocol-dxi2hz-plane-redis-1 valkey-cli FLUSHALL"

echo ""
echo "=== Step 5: Update HTML in DB ==="
scp jira_migrate_scripts/update_html_fixed.py oci:/tmp/
ssh oci "sudo docker cp /tmp/page_final.jsonl compose-parse-auxiliary-protocol-dxi2hz-api-1:/tmp/page_updates_tiptap_fixed.jsonl"
ssh oci "sudo docker cp /tmp/update_html_fixed.py compose-parse-auxiliary-protocol-dxi2hz-api-1:/tmp/"
ssh oci "sudo docker exec compose-parse-auxiliary-protocol-dxi2hz-api-1 python manage.py shell -c \"exec(open('/tmp/update_html_fixed.py').read())\""

echo ""
echo "=== Step 5.5: Resolve page links (data-page-id → real URL) ==="
scp jira_migrate_scripts/fix_page_links.py oci:/tmp/
ssh oci "sudo docker cp /tmp/fix_page_links.py compose-parse-auxiliary-protocol-dxi2hz-api-1:/tmp/"
ssh oci "sudo docker exec compose-parse-auxiliary-protocol-dxi2hz-api-1 python manage.py shell -c \"exec(open('/tmp/fix_page_links.py').read())\""

echo ""
echo "=== Step 6: Update binaries in DB ==="
scp jira_migrate_scripts/import_binaries.py oci:/tmp/
ssh oci "sudo docker cp /tmp/page_binaries.jsonl compose-parse-auxiliary-protocol-dxi2hz-api-1:/tmp/"
ssh oci "sudo docker cp /tmp/import_binaries.py compose-parse-auxiliary-protocol-dxi2hz-api-1:/tmp/"
ssh oci "sudo docker exec compose-parse-auxiliary-protocol-dxi2hz-api-1 python manage.py shell -c \"exec(open('/tmp/import_binaries.py').read())\""

echo ""
echo "=== Step 6.5: Health check (before live restart) ==="
scp jira_migrate_scripts/health_check_pages.py oci:/tmp/
ssh oci "sudo docker cp /tmp/health_check_pages.py compose-parse-auxiliary-protocol-dxi2hz-api-1:/tmp/"
ssh oci "sudo docker exec compose-parse-auxiliary-protocol-dxi2hz-api-1 python manage.py shell -c \"exec(open('/tmp/health_check_pages.py').read())\""

echo ""
echo "=== Step 7: ユーザ対応（手動） ==="
echo "live は停止したままです。以下を実施してから Step 8 を実行してください:"
echo ""
echo "  1. 全ユーザに通知: plane.example.com のサイトデータ（IndexedDB）を削除"
echo "     Chrome: 設定 > プライバシーとセキュリティ > サイトの設定 > plane.example.com > データを削除"
echo "  2. 全ユーザが削除完了したことを確認"
echo "  3. 以下を実行:"
echo ""
echo "     ssh oci 'sudo docker exec compose-parse-auxiliary-protocol-dxi2hz-plane-redis-1 valkey-cli FLUSHALL && sudo docker start compose-parse-auxiliary-protocol-dxi2hz-live-1'"
echo ""
echo "=== Done (live は手動で起動してください) ==="

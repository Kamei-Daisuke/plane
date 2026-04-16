# Jira/Confluence → Plane 移行スクリプト

## ディレクトリ構成

```
jira_migrate_scripts/
├── data/                          # データファイル（git管理外）
│   ├── confluence_pages.jsonl     # Confluence DBダンプ（MySQL → JSONL）
│   ├── page_map.json              # Confluence page ID → Plane page ID
│   ├── page_asset_map.json        # ファイル名 → FileAsset ID
│   ├── page_final.jsonl           # 変換済み TipTap HTML
│   ├── page_binaries.jsonl        # Y.js binary (base64)
│   └── ...
├── convert_final.py               # Confluence XHTML → TipTap HTML 変換
├── gen_binaries_final.js          # HTML → Y.js binary 生成
├── update_html_fixed.py           # DB に HTML を投入（サーバ側実行）
├── import_binaries.py             # DB に binary を投入（サーバ側実行）
├── fix_jira_urls.py               # Jira URL → Plane URL 変換（サーバ側実行）
├── fix_page_asset_projects.py     # FileAsset の project_id 修正（サーバ側実行）
├── reimport_pages.sh              # 一括再インポート
└── _archive/                      # 過去の試行錯誤スクリプト（git管理外）
```

## ページ再インポート手順

変換ロジックを修正した後の再インポート:

```bash
bash jira_migrate_scripts/reimport_pages.sh
```

実行後、ブラウザの plane.example.com のサイトデータを削除してからページを確認。

### 個別ステップ

```bash
# 1. Confluence → TipTap HTML 変換
python3 jira_migrate_scripts/convert_final.py

# 2. Y.js binary 生成（Plane の editor パッケージを使用）
node jira_migrate_scripts/gen_binaries_final.js

# 3. サーバに転送 → DB 更新
# reimport_pages.sh のStep 3〜7を参照
```

## Confluence DBダンプの取得

```bash
# prd-step 経由で Confluence MySQL にアクセス
eval $(ssh-agent -s) && ssh-add ~/Dropbox/work/00AWS/keis-kamei.pem
ssh -A -i ~/Dropbox/work/00AWS/keis-kamei.pem kamei@54.92.11.25 \
  "ssh kamei@10.7.1.60 'mysql -u confluenceuser -peiquo3EJ confluence \
    -e \"SELECT JSON_OBJECT(\\\"id\\\", c.CONTENTID, \\\"title\\\", c.TITLE, \\\"body\\\", b.BODY, \\\"space\\\", s.SPACEKEY) \
    FROM CONTENT c JOIN BODYCONTENT b ON c.CONTENTID = b.CONTENTID \
    JOIN SPACES s ON c.SPACEID = s.SPACEID \
    WHERE c.CONTENTTYPE = \\\"PAGE\\\" AND c.PREVVER IS NULL AND c.CONTENT_STATUS = \\\"current\\\"\" \
    --batch --raw --skip-column-names'" > jira_migrate_scripts/data/confluence_pages.jsonl
```

## page_map.json の再取得

```bash
ssh oci "sudo docker exec compose-parse-auxiliary-protocol-dxi2hz-plane-db-1 \
  psql -U plane plane -t -A -c \
  \"SELECT external_id, id FROM pages WHERE deleted_at IS NULL AND external_id IS NOT NULL\"" \
  | python3 -c "
import json, sys
pm = {}
for line in sys.stdin:
    line = line.strip()
    if '|' in line:
        ext, pid = line.split('|', 1)
        pm[ext] = pid
with open('jira_migrate_scripts/data/page_map.json', 'w') as f:
    json.dump(pm, f)
print(f'Page map: {len(pm)}')"
```

## page_asset_map.json の再取得

```bash
ssh oci "sudo docker exec compose-parse-auxiliary-protocol-dxi2hz-api-1 \
  python manage.py shell -c \"
import json
from plane.db.models import FileAsset
am = {}
for fa in FileAsset.objects.filter(entity_type='PAGE_DESCRIPTION', deleted_at__isnull=True).only('id','attributes'):
    name = (fa.attributes or {}).get('name','')
    if name: am[name] = str(fa.id)
print(json.dumps(am))
\"" > jira_migrate_scripts/data/page_asset_map.json
```

## 変換ロジック（convert_final.py）の概要

1. `ac:image` → `image-component`（FileAsset UUID 参照）
2. `ac:structured-macro name="code"` → `<pre><code>`
3. ネストしたマクロ（expand, info, panel 等）→ 内側から順に展開（`ac:rich-text-body` の中身を抽出）
4. `ac:link` → `<a>` または `[Page: title]`
5. 残りの `ac:` / `ri:` タグを除去
6. `<hr>` → TipTap の `<div data-type="horizontalRule">`
7. `<span style="color:...">` → `<span data-text-color="..." style="color:...">`
8. `<p>`, `<h1>`〜`<h6>` に TipTap のクラスを付与
9. ブロック要素のネスト修正（`<p>` 内の `<h2>` 等を `</p>` で分割）
10. 空の `<p>` を除去

## 既知の制限

- TipTap のパーサーが理解できない HTML 構造は binary 生成時に消える
- 10段以上のマクロネストは処理されない（ループ上限10回）
- Confluence のページ間リンクは `[Page: title]` テキストになる（Plane のページ URL への変換は未実装）
- 4ページの JSONL パースエラー（HTML 内のエスケープ問題）

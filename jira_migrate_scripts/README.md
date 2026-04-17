# Jira/Confluence → Plane 移行スクリプト

## ディレクトリ構成

```
jira_migrate_scripts/
├── data/                          # データファイル（git管理外）
│   ├── confluence_pages.jsonl     # Confluence DBダンプ（MySQL → JSONL）
│   ├── confluence_parents.tsv     # Confluence ページ親子関係（MySQL → TSV）
│   ├── page_map.json              # Confluence page ID → Plane page ID
│   ├── page_asset_map.json        # ファイル名 → FileAsset ID
│   ├── page_titles.json           # Plane page ID → タイトル
│   ├── page_to_project.json       # Plane page ID → project ID
│   ├── page_parents.json          # Plane page ID → parent page ID
│   ├── title_to_plane_id.json     # ページタイトル → Plane page ID
│   ├── title_stripped_to_plane_id.json
│   ├── jira_key_to_plane_url.json # Jira キー → Plane URL
│   ├── page_final.jsonl           # 変換済み TipTap HTML
│   ├── page_binaries.jsonl        # Y.js binary (base64、タイトル含む)
│   └── ...
├── convert_final_v2.py            # Confluence XHTML → TipTap HTML 変換（lxml）
├── gen_binaries_final.js          # HTML → Y.js binary 生成（タイトル付き）
├── verify_pages.js                # binary → HTML roundtrip 検証
├── health_check_pages.py          # reimport 後の整合性チェック（サーバ側実行）
├── update_html_fixed.py           # DB に HTML を投入（サーバ側実行）
├── import_binaries.py             # DB に binary を投入（サーバ側実行）
├── fix_jira_urls.py               # 旧 Jira/Confluence URL → Plane URL（サーバ側実行）
├── fix_page_links.py              # data-page-id → Plane URL 解決（サーバ側実行）
├── fix_page_asset_projects.py     # FileAsset の project_id 修正（サーバ側実行）
├── reimport_pages.sh              # 一括再インポート
├── EDITOR_FORMAT.md               # Plane エディタ HTML フォーマット仕様
├── convert_final.py               # v1 変換（正規表現ベース、廃止）
└── _archive/                      # 過去のスクリプト
```

## ページ再インポート手順

### 前提

- live サービスを停止してから実行する
- 他のユーザがページを開いていない状態で行う
- 再インポート後に live を起動すると、ブラウザの再接続で Y.js ドキュメントが
  マージされ増殖する可能性がある（IndexedDB 無効化済みなら低リスク）

### 実行

```bash
bash jira_migrate_scripts/reimport_pages.sh
```

### 手順の詳細

1. `convert_final_v2.py` — Confluence XHTML → TipTap HTML（lxml パーサー）
2. `gen_binaries_final.js` — HTML + タイトル → Y.js binary
3. `verify_pages.js` — binary roundtrip 検証
4. サーバに転送
5. live 停止 + Redis フラッシュ
6. HTML 更新 (`update_html_fixed.py`)
7. binary 更新 (`import_binaries.py`)
8. ヘルスチェック (`health_check_pages.py`)
9. live 起動

### ヘルスチェックの内容

`health_check_pages.py` が以下を検証:

- **HTML mismatch**: DB の HTML が page_final.jsonl と異なる
- **Heading count increase**: DB のヘディング数が expected より多い = live が壊した
- **Link loss**: Plane ページリンクが消えた

判定基準:

- Heading count increase > 0 → live が Y.js マージで増殖させた。該当ページを個別修正
- HTML mismatch はあっても heading increase がなければ、live の storeDocument が
  binary → HTML を再生成しただけ（内容は同じ、フォーマットが微妙に変わる）

## 既知の問題

### live サービスによるドキュメント増殖

- **原因**: ブラウザの Y.js ドキュメントがサーバのドキュメントとマージされ重複
- **対策**: IndexedDB 無効化済み（`use-yjs-setup.ts`）、storeDocument に 1.5x ガード
- **検出**: `health_check_pages.py` の heading count increase
- **修復**: page_final.jsonl から該当ページを個別 UPDATE

### live の storeDocument が HTML を上書き

- live がページを保存する時、binary → HTML 変換して description_html を上書き
- TipTap の server-side パーサー (zeed-dom) が一部の HTML を消す:
  - `style` 属性付きの span → カラーが消える（`data-text-color` なら保持）
  - `<pre>` 内のリンク → プレーンテキストになる
- 対策: `convert_final_v2.py` が EDITOR_FORMAT.md の仕様に準拠した HTML を出力

### Confluence 由来の重複

- 273 ページで同じ見出しが 2-4 回出現（`ac:layout` で複数カラムに同じ内容）
- これは Confluence の元データ由来で、live の破損ではない
- 検出: Confluence の heading count と同じなら正常

## Confluence DBダンプの取得

```bash
# SSH キー
KEY=jira_migrate_scripts/data/confluence_export/AT/attachments/02-02_AWS/AruhiAtlassian.pem

# Confluence EC2 を t2.large で起動（t2.small だと起動に失敗する）
aws ec2 modify-instance-attribute --instance-id i-040d1f4a7dd19a638 --instance-type t2.large --profile ip --region ap-northeast-1
aws ec2 start-instances --instance-ids i-040d1f4a7dd19a638 --profile ip --region ap-northeast-1

# ページデータ
ssh -i $KEY ec2-user@<IP> "mysql -u <USER> -p<PASS> confluence \
  -e \"SELECT JSON_OBJECT('id', c.CONTENTID, 'title', c.TITLE, 'body', b.BODY, 'space', s.SPACEKEY) \
  FROM CONTENT c JOIN BODYCONTENT b ON c.CONTENTID = b.CONTENTID \
  JOIN SPACES s ON c.SPACEID = s.SPACEID \
  WHERE c.CONTENTTYPE = 'PAGE' AND c.PREVVER IS NULL AND c.CONTENT_STATUS = 'current'\" \
  --batch --raw --skip-column-names" > jira_migrate_scripts/data/confluence_pages.jsonl

# 親子関係
ssh -i $KEY ec2-user@<IP> "mysql -u <USER> -p<PASS> confluence \
  -e \"SELECT c.CONTENTID, c.PARENTID, c.TITLE, s.SPACEKEY \
  FROM CONTENT c LEFT JOIN SPACES s ON c.SPACEID = s.SPACEID \
  WHERE c.CONTENTTYPE = 'PAGE' AND c.PREVVER IS NULL AND c.CONTENT_STATUS = 'current'\" \
  --batch" > jira_migrate_scripts/data/confluence_parents.tsv

# 終わったら t2.small に戻して停止
aws ec2 stop-instances --instance-ids i-040d1f4a7dd19a638 --profile ip --region ap-northeast-1
aws ec2 wait instance-stopped --instance-ids i-040d1f4a7dd19a638 --profile ip --region ap-northeast-1
aws ec2 modify-instance-attribute --instance-id i-040d1f4a7dd19a638 --instance-type t2.small --profile ip --region ap-northeast-1
```

## 変換ロジック（convert_final_v2.py）

lxml XML パーサーベース。仕様は `EDITOR_FORMAT.md` 参照。

主な変換:

1. `ac:structured-macro name="code"` → `<pre><code class="language-xxx">`
2. その他のマクロ（expand, panel, info, note 等）→ rich-text-body の中身を展開
3. `ac:link` + `ri:page` → Plane ページ URL（完全 URL 必須）
4. `ac:link` + `ri:url` → `<a href="URL">`
5. `ac:image` → `<image-component>` または `<img>`
6. `ac:layout` → 中身を展開（レイアウト構造は削除）
7. `<span style="color:...">` → `<span data-text-color="...">` （style 属性なし）
8. `<table style="width:N%">` → `<table>` + 各セルに `colwidth`
9. Confluence/Jira URL → Plane URL
10. HTML エンティティ → 数値参照（XML パーサー用）
11. リッチコンテンツ入り `<pre>` → `<p>`（コードブロック内のリンクを守る）

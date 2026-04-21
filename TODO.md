# TODO — keis 本番デプロイ後の移行積み残し（2026-04-21 更新）

## 現状サマリ（v7 bulk reconvert 後）

- `reconvert_pages_with_callouts_bulk.py` が唯一のマスタースクリプト
- **4588 ページ**を Confluence source から完全再変換済み
- 対応マクロ: info/note/tip/warning/toc/jira/expand/include/panel/status/code/view-file/excel/spreadsheets/viewppt/viewxls/viewdoc/viewpdf/children/pagetree/pagetreesearch/anchor + ac:link + task-list
- Confluence URL → Plane URL 解決をスクリプト内に統合済（再実行してもデグレしない）
- 意図的に drop: change-history/recently-updated/contributors/gadget/roadmap/attachments 等の動的 widget

## 未対応

### HIGH

- [x] **画像 "Error loading image"** → **2 段階で対応済 2026-04-20**
  - 最初の対応: 3 ページ × 39 参照を placeholder に置換 → 誤判断（画像は削除されていない）
  - ユーザ指摘で方針変更: dedupe で消えた Plane UUID を `page_asset_map.json` 経由で filename に逆引きし、残存する同名+同サイズの file_asset UUID に書き換え
  - `jira_migrate_scripts/fix_missing_image_uuids.py` で **79 ページ × 768 refs を復元**（710 は filename+size 一致、49 は name-only fallback）
  - 復元前に `extract_backup_html.py` + `restore_pages_from_files.py` で 3 ページの description_html を backup から restore

- [x] **Excel/PDF/DOCX 添付が HTML に差し込まれていない** — file_assets には存在するが description_html にリンクが無い → **対応済 2026-04-20**
  - 340 ページ × 2440 添付 を `jira_migrate_scripts/inject_orphan_attachments.py` で footer に一括追加
  - description_binary クリア + force_close ブロードキャスト済み

- [x] **コードブロックが引き継がれていない** → **対応済 2026-04-20**（2 ページ × 10 samples）
  - `jira_migrate_scripts/inject_api_samples_as_codeblock.py` で Confluence の info macro 内に URL:/ボディ: を含むサンプルを抽出し、ページ末尾に `<pre><code>` の「リクエスト・レスポンスサンプル」節として追加
  - 対応: ef8af409 (Profiles POST / 5 samples), 1245c9ce (Profiles PUT / 5 samples)
  - 要検討: 他の API 仕様ページでも同パターン info box があれば一括適用（全ページ走査で検出し `--apply` 引数なしで実行）

- [x] **Confluence への外部リンクが残っている** — リンク先が Plane 内ページではなく元 Confluence URL のまま → **対応済 2026-04-20**
  - 12 ページ × 47 リンクを `jira_migrate_scripts/rewrite_confluence_links.py` で Plane URL に書き換え
  - 未解決: 61 件の `/display/<SPACE>/<Title>` が jsonl に無い（未移行ページ等）、150 件の unrecognized URL (draft/resume action 等、リンクは残置)

### MEDIUM

- [x] **ページ並び順が降順** → **対応済 2026-04-20**
  - `apps/web/core/store/pages/project-page.store.ts` の初期 filter を `sortKey: "name", sortBy: "asc"` に変更

### LOW

- [x] **Gliffy フロー図が移行されていない** → **部分対応済 2026-04-20**
  - Gliffy の JSON / PNG プレビューは file_assets にアップロード済だった（141 asset / 37 ページ）
  - inject_orphan_attachments で全ページ footer にリンク追加済。ユーザは PNG 版で図を閲覧可能
  - 本文中の元位置には埋め込まれていない（Gliffy macro 解析が必要。対応費用高いので見送り）
  - 再作図したい場合: Gliffy JSON をダウンロードして draw.io 等にインポート可能

## 調査タスク

- [x] 全ページ走査: `image-component src="UUID"` の UUID が file_assets に存在するか → 3 ページ × 39 refs 欠損（上記で対応済）
- [x] 全ページ走査: entity_identifier = page.id で file_assets が紐付いているが description_html に参照が無いケース → 340 ページ × 2440 assets（上記で対応済）
- [x] Gliffy 図の原データは file_assets に PNG 含めて存在 → footer 経由で参照可能に

## 残課題（fix 後に発覚した場合用）

- [ ] コードブロック（info box）の見た目改善（上記 MEDIUM 扱い、本質的には migration ではなく rendering 差異）
- [ ] Gliffy を本文の元位置に画像として埋め込み直す（Confluence body の macro 位置解析が必要）
- [ ] Confluence リンクの未解決 61 件 + 150 unrecognized（draft/resume/browse 等、Plane 内に対応ページが無い）
- [ ] 元 Confluence `<ac:image>` と Plane UUID の位置対応付けによる画像 UUID 復元（今回欠損の 39 refs が対象）

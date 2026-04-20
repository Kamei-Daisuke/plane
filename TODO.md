# TODO — keis 本番デプロイ後の移行積み残し

## 未対応

### HIGH

- [x] **画像 "Error loading image"** → **対応済 2026-04-20**（3 ページ × 39 参照を placeholder に置換）
  - 対応ページ: 9927b198, 55cc494c, 9c7402d3
  - 置換テキスト: `[画像欠損: 元 Confluence から復元できませんでした]`
  - 元画像の復元は不可（Plane UUID が file_assets に無く、Confluence content ID への逆引きマップが無い）
  - 改善余地: 元 Confluence の `<ac:image>` 順序と Plane UUID の順序を位置対応させれば復元可能かも（今回は見送り）

- [x] **Excel/PDF/DOCX 添付が HTML に差し込まれていない** — file_assets には存在するが description_html にリンクが無い → **対応済 2026-04-20**
  - 340 ページ × 2440 添付 を `jira_migrate_scripts/inject_orphan_attachments.py` で footer に一括追加
  - description_binary クリア + force_close ブロードキャスト済み

- [ ] ~~**コードブロックが引き継がれていない**~~ — 調査の結果、元の Confluence に code macro が無かった。2 ページとも info box（URL/header/body を列挙）が Plane では plain `<p>` に変換されて見た目が code ブロックに見えない状態。本質的には migration バグではなく content rendering の違い
  - 既知: [ef8af409 (Profiles POST)](https://plane.keis-software.com/keis/projects/cc5b6449-177b-412b-b9de-08707161428a/pages/ef8af409-eb2c-4d29-8918-e6c9590b1716/)
  - 既知: [1245c9ce (Profiles PUT)](https://plane.keis-software.com/keis/projects/cc5b6449-177b-412b-b9de-08707161428a/pages/1245c9ce-c23e-42d9-8ddf-7315bcf98e91/)
  - 対応: info box 内容を blockquote or 同等の視覚的強調に変換するか、ユーザに個別調整してもらう

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

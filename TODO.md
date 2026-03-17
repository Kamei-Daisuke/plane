# TODO — fix/local-compose-and-settings-routes レビュー修正

全 20 件対応済み（5 ラウンドのレビュー・修正ループ）。

## HIGH (完了)
- [x] `ProjectPropertyValuesBulkEndpoint` の `issue_ids` に UUID バリデーション追加
- [x] `IssuePropertyValueEndpoint.post` を `transaction.atomic()` で囲む
- [x] `IssueWorklogViewSet.destroy` をソフトデリート (`deleted_at`) に修正
- [x] `allow_permission` の `request.data` からの `project_id` 取得を削除（セキュリティリスク）
- [x] `property-item.tsx`: `!is_active` 時に「Active」と表示されるバグを修正
- [x] `page.tsx`: ハードコード日本語「カスタムプロパティ」を `t()` で i18n 化

## MEDIUM (完了)
- [x] `_is_project_admin` の DB クエリをリクエストにキャッシュして効率化
- [x] `additional-properties.tsx` の `fetchedRef` が `issue.id` 変更時にリセットされない問題（fix ブランチで解消済み）
- [x] 設定画面コンポーネント（root/issue-type-section/property-form/option-form/property-item）のハードコード日本語を i18n 化
- [x] `ProjectIssueTypeListView` の `permission_classes` を `ProjectBasePermission` に変更
- [x] `IssueTypeSelect` (モーダル版) の自動選択 useEffect に `autoSelectedRef` ガードを追加
- [x] `property-item.tsx` の `title="編集"` / `title="削除"` を i18n 化
- [x] `property-item.tsx` の "options" ハードコード英語を i18n 化
- [x] `property-field.tsx` の "Select member(s)" ハードコード英語を i18n 化

## LOW (完了)
- [x] `PROGRESS.md` / `README_KEIS.md` を `.gitignore` に追加
- [x] `header.tsx` のカスタムプロパティ表示を i18n 化
- [x] `PropertyField` の未使用 `workspaceSlug` props を削除
- [x] サイドバー/Peek の "Type" ラベルを `t("common.type")` で i18n 化
- [x] `property-field.tsx` の "No options defined" ハードコードを修正
- [x] `property-item.tsx` の "Inactive" ハードコード英語を i18n 化

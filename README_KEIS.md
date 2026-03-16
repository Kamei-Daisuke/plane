# Keis Software カスタマイズ — 実装メモ

このファイルは、Plane の `keis` ブランチで行ったカスタマイズ内容をまとめたものです。

---

## 実装済み機能

### カスタムプロパティ（Custom Properties）

ワークアイテム（Issue）に対して、プロジェクトごとに自由なフィールドを追加できる仕組みです。

#### 概要

EAV（Entity–Attribute–Value）方式でプロパティ定義と値を分離して管理します。
Plane の CE/EE スタブアーキテクチャ（`apps/web/ce/` に CE 実装を置く方式）に従って実装しています。

#### 対応プロパティ型

| 型             | 説明             |
| -------------- | ---------------- |
| `text`         | テキスト入力     |
| `number`       | 数値入力         |
| `date`         | 日付入力         |
| `boolean`      | トグル（ON/OFF） |
| `url`          | URL 入力         |
| `select`       | 単一選択         |
| `multi_select` | 複数選択         |
| `member`       | メンバー単一選択 |
| `multi_member` | メンバー複数選択 |

#### バックエンド（Django）

**バルクフェッチエンドポイント** (追加):

```
GET /workspaces/{slug}/projects/{project_id}/property-values/?issue_ids=id1,id2,...
```

レスポンス: `{issue_id: {property_id: value, ...}, ...}` — 一覧ビュー向けの一括取得用。

**新規モデル** (`apps/api/plane/db/models/issue_property.py`):

- `IssueTypeProperty` — プロパティ定義（名前、型、必須フラグ、有効フラグ）
- `IssueTypePropertyOption` — select/multi_select の選択肢
- `IssuePropertyValue` — ワークアイテムごとの値（JSONField）

**APIエンドポイント** (`apps/api/plane/app/urls/issue.py`):

```
GET/POST   /workspaces/{slug}/issue-types/{type_id}/properties/
PATCH/DEL  /workspaces/{slug}/issue-types/{type_id}/properties/{id}/
GET/POST   /workspaces/{slug}/issue-types/{type_id}/properties/{prop_id}/options/
PATCH/DEL  /workspaces/{slug}/issue-types/{type_id}/properties/{prop_id}/options/{id}/
GET/POST   /workspaces/{slug}/projects/{project_id}/issues/{issue_id}/property-values/
```

**マイグレーション**: `apps/api/plane/db/migrations/0121_add_custom_properties.py`

#### フロントエンド（Next.js / MobX）

**型定義** (`packages/types/src/issues/issue_property.ts`):

- `TIssuePropertyType`, `TIssueTypeProperty`, `TIssueTypePropertyOption`
- `TIssuePropertyValues`, `TIssuePropertyValueErrors`

**サービス** (`apps/web/core/services/issue/issue_property.service.ts`):

- プロパティ CRUD および値の取得・一括 upsert

**MobX ストア** (`apps/web/ce/store/issue-property.store.ts`):

- `propertiesByIssueType` — issue type ID ごとのプロパティ一覧
- `valuesByIssue` — `"${projectId}:${issueId}"` をキーとした値マップ

**フック** (`apps/web/core/hooks/store/use-issue-property.ts`):

- `useIssueProperty()` — ストアへのアクセスフック

**コンポーネント（CE スタブ実装）**:

| ファイル                                                                    | 役割                                           |
| --------------------------------------------------------------------------- | ---------------------------------------------- |
| `apps/web/ce/components/issues/issue-properties/property-field.tsx`         | 型に応じた入力 UI                              |
| `apps/web/ce/components/issues/issue-modal/modal-additional-properties.tsx` | 作成/編集モーダル内のプロパティ入力欄          |
| `apps/web/ce/components/issues/issue-details/additional-properties.tsx`     | 詳細サイドバーのプロパティ編集                 |
| `apps/web/ce/components/issues/issue-layouts/additional-properties.tsx`     | 一覧ビューでの値表示（読み取り専用）           |
| `apps/web/ce/components/issues/issue-modal/provider.tsx`                    | モーダル用 Context（バリデーション・保存処理） |

#### プロパティ管理設定画面

プロジェクト設定にカスタムプロパティ管理ページを追加しました。ADMIN ユーザーが UI からプロパティを定義できます。

**URL**: `/{workspaceSlug}/settings/projects/{projectId}/custom-properties/`

**追加エンドポイント**:

```
GET  /workspaces/{slug}/projects/{project_id}/issue-types/
```

プロジェクトに紐づく IssueType 一覧を返します（`ProjectIssueType` 経由）。

**設定画面コンポーネント**:

| ファイル                                                                            | 役割                                   |
| ----------------------------------------------------------------------------------- | -------------------------------------- |
| `apps/web/app/.../custom-properties/page.tsx`                                       | ルートページ（権限チェック含む）       |
| `apps/web/app/.../custom-properties/header.tsx`                                     | ページヘッダー（パンくずリスト）       |
| `apps/web/ce/components/projects/settings/custom-properties/root.tsx`               | IssueType ごとにセクション表示         |
| `apps/web/ce/components/projects/settings/custom-properties/issue-type-section.tsx` | 1タイプのプロパティ一覧＋追加ボタン    |
| `apps/web/ce/components/projects/settings/custom-properties/property-item.tsx`      | プロパティ行（編集・削除・選択肢管理） |
| `apps/web/ce/components/projects/settings/custom-properties/property-form.tsx`      | プロパティ作成/編集フォーム            |
| `apps/web/ce/components/projects/settings/custom-properties/option-form.tsx`        | 選択肢作成/編集フォーム（色設定付き）  |

**ストア追加アクション** (`apps/web/ce/store/issue-property.store.ts`):

- `issueTypesByProject` — projectId ごとの IssueType キャッシュ
- `fetchProjectIssueTypes`, `createProperty`, `updateProperty`, `deleteProperty`
- `createOption`, `updateOption`, `deleteOption`

---

### IssueType の自動生成

プロジェクト作成時に、ワークスペース共通のデフォルト IssueType「Task」を自動生成し、プロジェクトに紐づけます。
これにより、カスタムプロパティ設定画面が空にならずにすぐ使えます。

**変更ファイル**:

- `apps/api/plane/app/views/project/base.py` — プロジェクト作成時の IssueType + ProjectIssueType 自動生成
- `apps/api/plane/api/views/project.py` — API 経由の作成でも同様
- `apps/api/plane/db/migrations/0122_backfill_default_issue_type.py` — 既存プロジェクトへのバックフィル

---

### Worklog（作業時間記録）

ワークアイテムに対して、ユーザーが作業時間を記録する機能です。

#### バックエンド

**新規モデル** (`apps/api/plane/db/models/worklog.py`):

- `IssueWorklog` — duration（分）、logged_date、description、logged_by

**API エンドポイント**:

```
GET/POST   /workspaces/{slug}/projects/{project_id}/issues/{issue_id}/worklogs/
PATCH/DEL  /workspaces/{slug}/projects/{project_id}/issues/{issue_id}/worklogs/{id}/
```

- GET: ワークログ一覧 + 合計時間を返す
- POST: 作業時間を記録
- PATCH: 自分のログのみ編集可（Admin は全件）
- DELETE: 自分のログのみ削除可（Admin は全件）

**マイグレーション**: `apps/api/plane/db/migrations/0123_add_issue_worklog.py`

#### フロントエンド

**型定義** (`packages/types/src/issues/worklog.ts`):

- `TIssueWorklog`, `TIssueWorklogListResponse`

**サービス** (`apps/web/core/services/issue/worklog.service.ts`):

- CRUD + 合計時間取得

**MobX ストア** (`apps/web/ce/store/worklog.store.ts`):

- `worklogsByIssue` — `"${projectId}:${issueId}"` をキーとしたログ一覧
- `totalByIssue` — 合計時間（分）キャッシュ

**時間入力フォーマット** (`utils.ts`):

- `1h 30m`、`90m`、`90`（分数）の各形式を受け付ける

**コンポーネント**:

| ファイル                                                                   | 役割                                               |
| -------------------------------------------------------------------------- | -------------------------------------------------- |
| `apps/web/ce/components/issues/worklog/worklog-form.tsx`                   | 時間・日付・メモ入力フォーム（i18n 対応済み）      |
| `apps/web/ce/components/issues/worklog/activity/worklog-create-button.tsx` | アクティビティ欄の「作業時間を記録」ボタン         |
| `apps/web/ce/components/issues/worklog/activity/root.tsx`                  | アクティビティ内のワークログ表示（編集・削除付き） |
| `apps/web/ce/components/issues/worklog/activity/filter-root.tsx`           | アクティビティフィルタ拡張（CE スタブ）            |
| `apps/web/ce/components/issues/worklog/property/root.tsx`                  | サイドバーの合計時間表示（記録ありのみ表示）       |

**差し込み箇所**:

- アクティビティヘッダー: `apps/web/core/components/issues/issue-detail/issue-activity/root.tsx`
- アクティビティ一覧: `apps/web/core/components/issues/issue-detail/issue-activity/activity-comment-root.tsx`（`activity_type === "WORKLOG"` で分岐）
- Issue サイドバー: `apps/web/core/components/issues/issue-detail/sidebar.tsx`
- Peek OverView: `apps/web/core/components/issues/peek-overview/properties.tsx`

**i18n**:

翻訳キー `worklog.*` を EN/JA に追加済み（`packages/i18n/src/locales/`）。

**アクティビティフィルタ**:

`packages/constants/src/issue/filter.ts` の `EActivityFilterType` に `WORKLOG` を追加し、`ACTIVITY_FILTER_TYPE_OPTIONS` と `defaultActivityFilters` にも反映。これにより、アクティビティフィルタ UI に「作業時間」が表示され、フィルタリングが機能する。

**バグ修正・改善（セルフレビュー後）**:

- タイムゾーンバグ修正: `new Date().toISOString()` → `new Date().toLocaleDateString("en-CA")`
- 削除確認ダイアログ + エラーハンドリング追加
- race condition 対策: IssueType `get_or_create` を `transaction.atomic()` + `select_for_update()` でラップ
- `use-worklog.ts` の不要な `as unknown as` キャスト削除
- フィルタバグ修正: `WORKLOG` が `EActivityFilterType` に未定義でワークログが常に非表示になっていた問題を修正
- アクティビティフィード表示バグ修正: `activity.store.ts` の `buildActivityAndCommentItems` がワークログを含めていなかった問題を修正。CE store で `WorklogStore.worklogsByIssue` を参照し WORKLOG エントリを注入するよう改修
- UI 権限チェック追加: 編集・削除ボタンを作成者または Admin のみに表示（`useUser` + `useUserPermissions` で判定）
- DB インデックス追加: `0124_worklog_indices.py` で `(issue, -logged_date, -created_at)` 複合インデックスと `logged_by` インデックスを追加

---

## ブランチ構成

- ベースブランチ: `origin/preview`（makeplane/plane の最新 CE リリース）
- カスタマイズブランチ: `keis`

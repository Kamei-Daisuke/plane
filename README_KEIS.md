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

## ブランチ構成

- ベースブランチ: `origin/preview`（makeplane/plane の最新 CE リリース）
- カスタマイズブランチ: `keis`

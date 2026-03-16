# PROGRESS — keis branch 作業記録

---

## 2026-03-16

### カスタムプロパティ設定 UI の実装

**やったこと**

- プロジェクト設定サイドバーに「カスタムプロパティ」タブを追加
- `TProjectSettingsTabs` 型・`PROJECT_SETTINGS` 定数・サイドバーアイコン・i18n キーを追加
- 設定ページルート (`/settings/projects/{id}/custom-properties/`) を実装
- CE コンポーネント: `root.tsx` / `issue-type-section.tsx` / `property-item.tsx` / `property-form.tsx` / `option-form.tsx`

**苦労したところ**

- `ProjectIssueType` が CE では自動生成されないため設定画面が空になる問題 → プロジェクト作成時に `get_or_create` でデフォルト IssueType「Task」を自動生成する処理を追加（`base.py` / `api/views/project.py`）
- 既存プロジェクト向けにバックフィルマイグレーション (`0122_backfill_default_issue_type.py`) を作成
- `oxlint` の `label-has-associated-control` / `no-autofocus` / `no-map-spread` エラーを複数箇所で修正

---

### Worklog（作業時間記録）の実装

**やったこと**

- Django モデル `IssueWorklog`（duration 分単位、logged_date、description、logged_by）
- API ViewSet + URL (`/worklogs/`)
- マイグレーション `0123_add_issue_worklog.py`
- TypeScript 型 `TIssueWorklog` / `TIssueWorklogListResponse`
- `WorklogService`（CRUD）
- MobX `WorklogStore`（`worklogsByIssue` / `totalByIssue`）
- `useWorklog()` フック
- UI: `WorklogForm`, `IssueActivityWorklogCreateButton`, `IssueActivityWorklog`, `IssueWorklogProperty`

**苦労したところ**

- `oxfmt` が `.claude/` ディレクトリを処理しようとして SIGKILL → `.claude/` をステージングから外してコミット
- `use-worklog.ts` で `StoreContext` 型が `CoreRootStore` に見えたため `as unknown as` キャストを使ったが、実際は CE の `RootStore` 型なので不要だった

---

### セルフレビューの修正

**やったこと**

- **HIGH**: `worklog-form.tsx` のタイムゾーンバグ修正 — `toISOString()` → `toLocaleDateString("en-CA")`
- **MEDIUM**: `use-worklog.ts` の不要な `as unknown as` キャスト削除
- **MEDIUM**: `activity/root.tsx` の削除ボタンに確認ダイアログ + エラーハンドリング追加
- **MEDIUM**: `base.py` / `api/views/project.py` の `get_or_create` を `transaction.atomic()` + `select_for_update()` でラップ
- **MEDIUM**: EN/JA 翻訳ファイルに `worklog.*` キー追加、全コンポーネントのハードコード日本語を `t()` に置き換え

**苦労したところ**

- `select_for_update()` は `get_or_create` と組み合わせると Django ORM 上は `filter().select_for_update()` 相当になるため、`transaction.atomic()` との併用が必須

---

### 統合状況の確認・ドキュメント整備

**やったこと**

- アクティビティタブへの統合確認 → `issue-activity/root.tsx` と `activity-comment-root.tsx` で `IssueActivityWorklogCreateButton` / `IssueActivityWorklog` がすでに使われていることを確認
- サイドバー合計時間の確認 → `sidebar.tsx` と `peek-overview/properties.tsx` で `IssueWorklogProperty` がすでに差し込まれていることを確認
- `filter-root.tsx` の存在確認 → 正しく実装済み、`ACTIVITY_FILTER_TYPE_OPTIONS` を動的に展開する設計
- カスタムプロパティ一覧ビューの確認 → `WorkItemLayoutAdditionalProperties` はキャッシュから読むだけで fetch しない設計
- カスタムプロパティのバリデーション確認 → `provider.tsx` の `handlePropertyValuesValidation` で必須チェック実装済み
- `CLAUDE.md` に設計原則・ドキュメント更新ルール・ワークフロールールを追加
- `PROGRESS.md` 新規作成

**苦労したところ**

- 一覧ビューで `valuesByIssue` がプリフェッチされない → バルク API がないため N+1 になる。意図的にオンデマンド（サイドバー開放時にキャッシュ）のままとした

---

## 既知の制限

- **一覧ビューのカスタムプロパティ値**: Issue 詳細サイドバーを開いた後でないとキャッシュがなく表示されない。バルクフェッチ API を追加すれば解消可能
- **ワークログのフィルタ**: `filter-root.tsx` は `ACTIVITY_FILTER_TYPE_OPTIONS` に `WORKLOG` が含まれている前提。未定義の場合はフィルタに表示されない（動作は問題なし）

---

## 次にやること

### Worklog フィルタバグ修正

**やったこと**

- `EActivityFilterType` に `WORKLOG = "WORKLOG"` を追加（`packages/constants/src/issue/filter.ts`）
- `ACTIVITY_FILTER_TYPE_OPTIONS` に `WORKLOG` エントリ追加（翻訳キー `worklog.label` 使用）
- `defaultActivityFilters` に `WORKLOG` を追加

**苦労したところ**

- `filterActivityOnSelectedFilters` は `activity_type` が選択フィルタに含まれているかを確認するが、`WORKLOG` が enum に存在しなかったためワークログが常にフィルタアウトされる致命的バグだった
- `TIssueActivityComment` 型には `activity_type: "WORKLOG"` が定義されていたが、フィルタ定数が未整備だった

---

### セルフレビュー（第2回）修正

**やったこと**

- **致命的バグ修正**: `activity.store.ts` の `buildActivityAndCommentItems` がワークログを含めていなかったため、アクティビティフィードに WORKLOG エントリが一切表示されなかった
  - CE `activity.store.ts` の `buildActivityAndCommentItems` で `WorklogStore.worklogsByIssue` を参照し、`issueId` に一致するエントリを `EActivityFilterType.WORKLOG` として注入するよう修正
- **エラーハンドリング**: `activity/root.tsx` の削除処理に `catch` ブロックと `deleteError` state を追加

**苦労したところ**

- `activity.store.ts` は CE にしか存在しない（core には activity store なし）が、`this.store` 型は `CoreRootStore` であるため `worklogStore` にアクセスするには `as unknown as RootStore` キャストが必要
- `computedFn` 内で `worklogsByIssue` (MobX observable) を参照しているため、ワークログ追加・削除時に自動的にリアクティブ更新される

---

### カスタムプロパティ値のバルクフェッチ実装

**やったこと**

- **バックエンド**: `GET /workspaces/{slug}/projects/{project_id}/property-values/?issue_ids=id1,id2,...` を追加
  - `ProjectPropertyValuesBulkEndpoint` として `apps/api/plane/app/views/issue/property.py` に実装
  - レスポンス形式: `{issue_id: {property_id: value, ...}, ...}`
- **フロントエンド**:
  - `TProjectPropertyValuesBulkResponse` 型を `issue_property.ts` に追加
  - `IssuePropertyService.getBulkPropertyValues()` を追加
  - `IssuePropertyStore.fetchBulkPropertyValues()` を追加（MobX action）
  - `WorkItemLayoutAdditionalProperties` に `useEffect` を追加し、キャッシュ未取得の issue のみ lazy-fetch

**設計の判断**

- バルクエンドポイントは追加したが、一覧ビューの各 issue コンポーネントから per-issue で lazy fetch する方式を選んだ
  - 理由: 一覧ビューに issue 一覧へのアクセス手段がなく、バルク呼び出し箇所の特定が難しいため
  - `useRef` で fetch 済みフラグを管理し、既にロード済みの issue は再フェッチしない

**苦労したところ**

- `useEffect` の `exhaustive-deps` lint ルールに対応するため、`valuesByIssue` オブジェクト全体ではなく `isCached` フラグに依存させた

---

### セルフレビュー（第3回）修正

**やったこと**

- `additional-properties.tsx`: `isCached` を deps に入れると effect が再実行される問題を `useRef` で解決
- `activity.store.ts`: `as unknown as RootStore` キャストをオプショナルチェーン `?.worklogStore?.worklogsByIssue` で null 安全に改善

---

### 監査レビューによる追加修正

**やったこと**

- **DB インデックス追加** (`0124_worklog_indices.py`): `issue + logged_date + created_at` 複合インデックスと `logged_by` インデックスを追加
- **UI 権限チェック** (`activity/root.tsx`): 編集・削除ボタンを `isAdmin || worklog.logged_by === currentUser.id` の場合のみ表示
- **PROGRESS.md 誤記修正**: `isCached` → `useRef`

**苦労したところ**

- `activity/root.tsx` は `workspaceSlug` と `projectId` を既に受け取っているため、`useUserPermissions()` の `getProjectRoleByWorkspaceSlugAndProjectId` をそのまま使えた

---

## 次にやること

- [ ] E2E 手動動作確認（設定画面 → プロパティ追加 → Issue 作成 → 値入力 → 一覧表示 → ワークログ記録）

# TODO — fix/local-compose-and-settings-routes レビュー修正

## 未対応

### HIGH
- [ ] `TEST_USERS.md` にパスワードが平文で記載されている — リポジトリにクレデンシャルをコミットすべきでない

### MEDIUM
- [ ] `grouper.py` に `type_id` を追加しているが、`ProjectPropertyValuesBulkEndpoint` への追加の `issue_ids` 呼び出しが `base-issues.store.ts` で全 issue を一度に送信 — 大量 issue 時に URL 長超過のリスク（GET クエリパラメータ制限）

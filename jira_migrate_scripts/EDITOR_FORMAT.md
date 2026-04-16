# Plane Pages エディタ HTML フォーマット仕様

Plane の Pages エディタは TipTap (ProseMirror) ベース。
以下は Plane CE (keis ブランチ) のソースコードから読み取った、サポートされる HTML フォーマット。

## 注意事項

- **`style` 属性は使わない** — TipTap の server-side パーサー (zeed-dom) が `style` を正しく処理できない ([tiptap#5352](https://github.com/ueberdosis/tiptap/issues/5352))
- **リンクは完全 URL** — 相対パス (`/keis/...`) は `isValidHttpUrl` で無効と判定される
- **binary (Y.js) との roundtrip で消えるものがある** — HTML → binary → HTML の変換で一部が消失する。以下の仕様に従えば最大限保持される

## Nodes（ブロック要素）

| 要素           | HTML                                                                             | 属性                  | 備考                                  |
| -------------- | -------------------------------------------------------------------------------- | --------------------- | ------------------------------------- |
| 段落           | `<p class="editor-paragraph-block">`                                             | class 必須            |                                       |
| 見出し         | `<h1-h6 class="editor-heading-block">`                                           | class 必須、level 1-6 |                                       |
| 箇条書き       | `<ul><li>...</li></ul>`                                                          |                       |                                       |
| 番号付き       | `<ol><li>...</li></ol>`                                                          |                       |                                       |
| タスクリスト   | `<ul class="not-prose pl-2 space-y-2"><li class="flex" data-checked="false">`    |                       |                                       |
| コードブロック | `<pre><code class="language-xxx">...</code></pre>`                               | language は任意       | 中身はプレーンテキスト                |
| 引用           | `<blockquote>...</blockquote>`                                                   |                       |                                       |
| 水平線         | `<div class="py-4 border-strong-1" data-type="horizontalRule"><div></div></div>` |                       | `<hr>` はパースされるが出力はこの形式 |
| テーブル       | `<table><tbody><tr><th>/<td>...</td></tr></tbody></table>`                       |                       |                                       |
| テーブルヘッダ | `<th colspan="1" rowspan="1" colwidth="N" background="none">`                    | colwidth は px 単位   |                                       |
| テーブルセル   | `<td colspan="1" rowspan="1" colwidth="N">`                                      | colwidth は px 単位   |                                       |
| 画像           | `<image-component id="UUID" src="UUID" data-id="UUID" status="uploaded">`        | Plane カスタム        | FileAsset ID を指定                   |
| メンション     | `<mention-component ...>`                                                        | Plane カスタム        |                                       |

## Marks（インライン要素）

| 要素             | HTML                                   | parseHTML が受け付けるタグ                                  | 備考                                                                  |
| ---------------- | -------------------------------------- | ----------------------------------------------------------- | --------------------------------------------------------------------- |
| 太字             | `<strong>`                             | `<strong>`, `<b>`, `font-weight: bold/bolder/500-900`       |                                                                       |
| イタリック       | `<em>`                                 | `<em>`, `<i>`, `font-style: italic/normal`                  |                                                                       |
| 下線             | `<u>`                                  | `<u>`                                                       |                                                                       |
| 取消線           | `<s>`                                  | `<s>`, `<del>`, `<strike>`, `text-decoration: line-through` |                                                                       |
| インラインコード | `<code>`                               | `<code>`                                                    |                                                                       |
| リンク           | `<a href="URL">`                       | `<a href="...">`                                            | href は完全 URL (https://...) 必須。`isValidHttpUrl` でバリデーション |
| テキスト色       | `<span data-text-color="COLOR">`       | `<span data-text-color="...">`                              | `style` 属性を付けてはいけない（server-side で壊れる）                |
| 背景色           | `<span data-background-color="COLOR">` | `<span data-background-color="...">`                        | 同上                                                                  |

## カラー値

`data-text-color` / `data-background-color` に使える値:

- Plane 定義色（キー名）: `grey`, `orange`, `yellow`, `green`, `blue`, `purple`, `pink`, `red` 等
- 任意の CSS カラー値: `rgb(255,0,0)`, `#ff0000` 等

Plane 定義色の場合は CSS クラスで色が適用される。それ以外は `renderHTML` が `style="color: VALUE"` を出力する。

## Extensions 一覧（`CoreEditorExtensionsWithoutProps`）

ソース: `packages/editor/src/core/extensions/core-without-props.ts`

1. CustomStarterKit (Paragraph, Heading, BulletList, OrderedList, ListItem, Text, HardBreak, Bold, Italic, Strike, Code, Blockquote, CodeBlock, HorizontalRule, History)
2. Emoji
3. CustomQuote (blockquote)
4. CustomHorizontalRule
5. CustomLink (a[href])
6. Image
7. CustomImage (image-component)
8. Underline (u)
9. TextStyle (span)
10. TaskList / TaskItem
11. CustomCodeInline (code)
12. CustomCodeBlock (pre > code)
13. Table / TableHeader / TableCell / TableRow
14. CustomMention
15. CustomTextAlign
16. CustomCallout
17. CustomColor (data-text-color, data-background-color)

## Confluence → Plane 変換時の対応表

| Confluence                                                       | Plane                                                                       |
| ---------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `<ac:structured-macro ac:name="code">`                           | `<pre><code class="language-xxx">`                                          |
| `<ac:structured-macro ac:name="expand/panel/info/note/warning">` | rich-text-body の中身を展開                                                 |
| `<ac:link><ri:page ri:content-title="T">`                        | `<a href="https://plane.example.com/keis/projects/PROJ/pages/PAGE/">` |
| `<ac:link><ri:url ri:value="URL">`                               | `<a href="URL">`                                                            |
| `<ac:image><ri:attachment ri:filename="F">`                      | `<image-component id="ASSET_ID">`                                           |
| `<ac:image><ri:url ri:value="URL">`                              | `<img src="URL">`                                                           |
| `<ac:layout>` / `<ac:layout-section>` / `<ac:layout-cell>`       | 中身を展開（レイアウト構造は削除）                                          |
| `<span style="color: rgb(...)">`                                 | `<span data-text-color="rgb(...)">`                                         |
| `<span style="background-color: rgb(...)">`                      | `<span data-background-color="rgb(...)">`                                   |
| `<table style="width: N%">`                                      | `<table>` + 各セルに `colwidth="px"`                                        |

# research-x

X（Twitter）のツイート・ブックマーク取得を、複数の取得方式で比較しながら運用できる
実験基盤です。

単発のスクレイピングスクリプトではなく、次の目的で作っています。

- 複数アダプタを同じ契約で実行して比較する
- 成功した方式だけを本線候補にできるようにする
- 失敗時も evidence を残して原因を追えるようにする
- ブックマーク、プロフィール、検索、URL 指定取得を同じ SQLite DB に統合する
- 引用ツイート、画像、AI ラベルをあとから UI や継続運用に使える形で保存する

このプロジェクトは X 公式 API を前提にしていません。ログイン済みブラウザセッションや
各種取得ライブラリを使い、取得結果を正規化して保存します。

## 注意

このリポジトリは、自分が管理しているアカウント、または明示的に許可された対象の調査・
バックアップ・検証用途を想定しています。

- パスワードや Cookie は Git に入れないでください。
- `.secrets/` と `runs/` は `.gitignore` 済みです。
- X 側のレート制限、ログイン確認、CAPTCHA、凍結、非公開化、削除済み投稿などにより、
  取得できる件数は変わります。
- セキュリティチャレンジの回避機能は持ちません。検出した場合は失敗として記録します。

## 主な機能

- **アダプタ比較**
  - `twscrape_raw`
  - `Scweet`
  - `twikit`
  - `masa-finance/masa-twitter-scraper`
  - `Playwright`
  - `Scrapling`
  - `Crawl4AI`
  - `Camoufox`
  - `Patchright`
  - `rebrowser-playwright`
  - `rebrowser-patches`
  - `Scrapy`

- **ブックマーク大量取得**
  - Web GraphQL のカーソル継続
  - 生レスポンス保存
  - 中断後の再開
  - 引用元ツイートをブックマーク本体として誤カウントしない保存構造

- **統合 DB**
  - `tweets`: ツイート本体を `tweet_id` で一意管理
  - `account_bookmarks`: アカウントごとのブックマーク関係
  - `collection_items`: プロフィール、検索、URL、ブックマーク取得の所属関係
  - `tweet_edges`: 引用ツイートなどの親子関係
  - `media`: 画像などのメディア情報
  - `ai_labels`: AI によるジャンル分類

- **AI ラベル付け**
  - OpenAI
  - Gemini
  - OpenAI 互換 API
  - Qwen / Kimi / GLM などの互換プロバイダ

- **ローカルアプリ**
  - ブラウザ画面からアカウント情報を入力
  - 自動ログイン、取得、DB 保存、本文確認まで実行

## セットアップ

Python 3.11 以上と `uv` を使います。

```powershell
uv sync
```

ブラウザ系プロバイダを使う場合は、必要に応じてブラウザを入れます。

```powershell
uv run patchright install chromium
uv run rebrowser_playwright install chromium
```

## まず動かす

認証なしで動く synthetic アダプタの smoke test です。

```powershell
uv run python -m research_x run --config examples/smoke.toml --out runs/smoke
```

テスト:

```powershell
uv run pytest
uv run ruff check src tests
```

## ローカルアプリを使う

コマンドを毎回打ちたくない場合は、ローカルアプリを起動します。

```powershell
uv run python -m research_x app
```

既定では次の URL を開きます。

```text
http://127.0.0.1:8765
```

画面から以下を入力できます。

- アカウント ID
- screen name
- user id
- display name
- パスワード
- 出力先
- DB パス
- 全件取得モード
- 画像保存
- AI 分類設定

パスワードはアカウント profile には保存しません。

## アカウントを登録する

アカウントごとに session / Cookie / DB 関係を分離します。

```powershell
uv run python -m research_x accounts add `
  --account my_account `
  --screen-name my_screen_name `
  --user-id 1234567890 `
  --display-name "My Account" `
  --url https://x.com/my_screen_name
```

PC標準の Edge に既に X ログイン済みの場合は、別 `user-data-dir` を作らずに
標準プロファイルから storage_state を書き出せます。Edge をすべて閉じてから実行すると
CDP ポートが確実に有効になります。

```powershell
uv run python -m research_x auth system-profile `
  --account my_account `
  --browser msedge `
  --profile-directory Default `
  --close-existing-browser
```

複数プロファイルを使っている場合は `--profile-directory "Profile 1"` のように指定します。
手動で Edge を CDP 起動済みなら、既存の CDP ルートも使えます。

```powershell
uv run python -m research_x auth cdp `
  --account my_account `
  --endpoint-url http://127.0.0.1:9222
```

パスワード自動ログインを使う場合、認証情報は環境変数から渡します。

```powershell
$env:RESEARCH_X_X_USERNAME="my_screen_name"
$env:RESEARCH_X_X_PASSWORD="<password>"
$env:RESEARCH_X_X_EMAIL_OR_PHONE="<email-or-phone-if-needed>"

uv run python -m research_x auth auto `
  --account my_account `
  --try-system-browser-profile `
  --system-browser-profile-directory Default `
  --system-browser-profile-close-existing `
  --system-browser msedge
```

保存先:

```text
.secrets/accounts/<account>/playwright_x_state.json
```

## ブックマークを取得する

全件取得:

```powershell
uv run python -m research_x bookmarks `
  --account my_account `
  --out runs/bookmarks_my_account `
  --all `
  --no-classify `
  --db runs/x_data.sqlite3 `
  --download-media
```

同じ `--out` で再実行すると、保存済みページとカーソル状態を使って再開します。

主な出力:

```text
runs/bookmarks_my_account/
  bookmarks_items.jsonl
  bookmarks.jsonl
  account_bookmarks.jsonl
  collection_items.jsonl
  tweets.jsonl
  tweet_edges.jsonl
  media.jsonl
  media/
  bookmark_trees.jsonl
  raw_payloads.jsonl
  bookmark_pages/
  pipeline_report.json
```

本文を確認する:

```powershell
uv run python -m research_x db-show `
  --db runs/x_data.sqlite3 `
  --account my_account `
  --kind bookmarks `
  --limit 20
```

JSON で見る:

```powershell
uv run python -m research_x db-show `
  --db runs/x_data.sqlite3 `
  --account my_account `
  --kind bookmarks `
  --limit 20 `
  --json
```

## AI でジャンル分けする

Gemini を使う例:

```powershell
$env:GEMINI_API_KEY="..."

uv run python -m research_x bookmarks `
  --account my_account `
  --out runs/bookmarks_my_account_labeled `
  --all `
  --classify `
  --classifier-provider gemini `
  --categories examples/bookmark_categories.toml `
  --db runs/x_data.sqlite3
```

分類カテゴリは `examples/bookmark_categories.toml` で追加・編集できます。

## 通常ツイートを取得する

プロフィール:

```powershell
uv run python -m research_x tweets `
  --account my_account `
  --kind profile `
  --value @target_user `
  --limit 100 `
  --out runs/tweets_target_user `
  --db runs/x_data.sqlite3
```

検索:

```powershell
uv run python -m research_x tweets `
  --account my_account `
  --kind search `
  --value "検索キーワード" `
  --limit 100 `
  --out runs/search_keyword `
  --db runs/x_data.sqlite3
```

段階的な件数テスト:

```powershell
uv run python -m research_x tweet-stages `
  --account my_account `
  --kind profile `
  --value @target_user `
  --stage-limits 100,200,300,400 `
  --out runs/tweet_stages
```

## 複数アダプタを比較する

利用可能なアダプタを見る:

```powershell
uv run python -m research_x adapters --details
```

パイプライン実行:

```powershell
uv run python -m research_x pipeline `
  --account my_account `
  --config examples/x_pipeline.toml `
  --out runs/x_pipeline_my_account `
  --min-successful-providers 2
```

各 provider の結果は `evidence/` と `pipeline_report.json` に残ります。

## ディレクトリ構成

```text
src/research_x/
  adapters/              取得方式ごとの実装
  accounts.py            アカウント別 session パス管理
  bookmarks.py           ブックマーク取得ジョブ
  tweets.py              通常ツイート取得ジョブ
  x_store.py             SQLite / JSONL 保存
  bookmark_classifier.py AI ラベル付け
  local_app.py           ローカル操作画面
  cli.py                 CLI エントリポイント

examples/                設定例
docs/                    調査メモ・設計メモ
tests/                   テスト
```

## 開発

```powershell
uv run pytest
uv run ruff check src tests
```

公開前に確認すること:

- `.secrets/` が Git に入っていないこと
- `runs/` が Git に入っていないこと
- 実アカウント名、Cookie、パスワード、メールアドレスを README や docs に残していないこと

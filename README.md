# gmail_retriever

Gmail APIを使い、特定の送信元からの就活関連メール(スカウト・企業からの選考案内)を読み取り専用で取得し、
Obsidian の Vault(デイリーノート・企業ノート)に要約を自動追記するツールです。

Gmail APIの `gmail.readonly` スコープのみを使用します。メールの削除・既読化・変更・送信などは一切行いません。

このリポジトリは以下2種類のルールのみを扱います:

- **就活(job)**: スカウトサービス等からのメールに含まれる企業の選考情報・イベント・記事をデイリーノートに記録
- **企業(company)**: 企業の採用担当から届くメールから、選考情報(あれば)をデイリーノートに、企業情報・働き方をCompaniesノートに記録

## 仕組み

1. `mails.xlsx` の「欲しい処理」列を見て、`【就活】`または`【企業】`で始まる行のメールアドレスを対象として抽出する
2. `fetch_target_mail.py` / `backfill_digest.py` が Gmail API(読み取り専用)で該当メールを取得し、`mail_data/` 配下に日付ごとのJSONとして保存する
3. ローカルの Claude Code(`claude -p`)がJSONを読み、要約ルールに従って Obsidian Vault のデイリーノート・企業ノートに追記する

要約・Obsidianへの書き込みは、ローカルにインストールした Claude Code CLI (`claude -p`、非対話モード)を使って行います。
API課金ではなく、ログイン済みの Claude アカウントの権限で実行されます。

## セットアップ

### 1. Gmail APIの認証情報

1. Google Cloud Console でプロジェクトを作成し、Gmail APIを有効化する
2. OAuth同意画面を設定する(User Type: 外部、テストユーザーに自分のGmailアドレスを追加)
3. OAuthクライアントID(デスクトップアプリ)を作成し、ダウンロードしたJSONを `credentials.json` としてこのディレクトリに配置する

### 2. Python環境

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. 環境変数

```bash
cp .env.example .env
```

`.env` を編集し、`OBSIDIAN_VAULT_DIR` に自分の Obsidian Vault の絶対パスを設定する。

### 4. 対象アドレス一覧(xlsx)の作成

`mails.sample.xlsx` を参考に、自分の `mails.xlsx` を作成してください。

必須列:

| 列名 | 内容 |
|---|---|
| メールアドレス | 対象の送信元アドレス |
| 表示名 | 送信者の表示名(企業ノートのファイル名の元にもなる) |
| 欲しい処理 | `【就活】企業、選考、イベント、記事があればデイリーノートに記録。` または `【企業】選考開始時期・企業情報・働き方などまとめ` で始まる文字列。この2種類以外の行は無視されます |
| Base Tag | (任意)デイリーノートに付与する基本タグ。例: `#Career` |

### 5. Obsidian Vault側の準備

Vault内に以下のファイル・構成が必要です(`templates/` 配下にサンプルを同梱しています):

- `Daily/Daily_Template.md`: デイリーノートのテンプレート。`### Mails` セクションを含むこと(無ければ自動追加されます)
- `Companies/Companies_Template.md`: 企業ノートのテンプレート(基本情報/事業概要/業績/働く環境/新卒採用)
- `Diary/{YYYY}/{MM}/{YYYY-MM-DD}.md`: 日付ごとのデイリーノート(無ければテンプレートから自動作成されます)

## 使い方

### 手動実行(当日分)

```bash
./daily_digest.sh
```

### バックフィル実行(指定期間分)

```bash
./backfill_digest.sh 2026-08-01 2026-08-08
```

`END_DATE` を省略すると実行時点(JST)の今日までを対象とします。

### 定期実行

`daily_digest.sh` を cron や launchd などで毎日決まった時刻に実行することを想定しています。
(このリポジトリには定期実行の設定ファイルは含まれていません。各自の環境に合わせて設定してください)

## 安全性について

- 要求スコープは `gmail.readonly` のみで、メールの変更・削除・送信は一切行いません
- `credentials.json` / `token.json` / `.env` / `mails.xlsx` / `mail_data/` / `logs/` は `.gitignore` 対象です。これらにはGoogleアカウントへのアクセス権や個人の受信メール内容が含まれるため、コミット・共有しないでください

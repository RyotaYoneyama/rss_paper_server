# RSS要約システム

RSS記事を自動取得し、ChatGPTのAPIを使って落合フォーマットで要約してメール送信するDockerベースのシステムです。

## 機能

1. **RSS自動取得**: 登録したRSSフィードから指定時間に記事を自動取得
2. **重複記事検出**: データベース上の既存記事との重複を防止
3. **キーワードフィルタリング**: 記事を複数のキーワードで自動分類・フィルタリング
4. **ウェブアプリ**: 記事の一覧表示、検索、管理機能
5. **AI要約**: ChatGPT APIを使用した落合フォーマットでの記事要約
6. **メール送信**: 毎朝未読記事の要約を指定メールアドレスに自動送信

## 落合フォーマットとは

以下の6つの観点で研究論文や技術記事を要約する形式：

1. **どんなもの？** - 研究の概要
2. **先行研究と比べてどこがすごい？** - 新規性・優位性
3. **技術や手法のキモはどこ？** - 核心技術
4. **どうやって有効だと検証した？** - 評価方法
5. **議論はある？** - 課題・制限
6. **次読むべき論文は？** - 関連研究

## システム構成

- **Backend**: FastAPI (Python)
- **Database**: PostgreSQL
- **AI**: OpenAI GPT-3.5 Turbo
- **Frontend**: Bootstrap + Jinja2 Templates
- **Container**: Docker + Docker Compose
- **Scheduler**: Python schedule library

## セットアップ

### 1. 環境設定

```bash
# リポジトリをクローン
git clone <repository-url>
cd rss_summarizer

# 環境変数ファイルを作成
cp .env.example .env
```

### 2. 環境変数の設定

`.env`ファイルを編集して以下の値を設定：

```bash
# OpenAI API Key (必須)
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_TEMPERATURE=1.0  # 生成テキストの多様性（0.0-2.0）

# メール設定 (必須)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_FROM=your_email@gmail.com
EMAIL_TO=recipient@example.com
EMAIL_LOG_CONTENT_LENGTH=1000  # ログに保存するメール内容の長さ

# スケジュール設定
SCHEDULER_CHECK_INTERVAL=60  # スケジューラのチェック間隔（秒）
SUMMARY_EMAIL_HOUR=5  # 要約メール送信時間（時、JST）
SUMMARY_EMAIL_MINUTE=0  # 要約メール送信時間（分、JST）

# クリーンアップ設定
CLEANUP_READ_ARTICLES_DAYS=7  # 既読記事を削除する日数
CLEANUP_UNREAD_ARTICLES_LIMIT=1000  # 未読記事の保持上限
CLEANUP_READ_ARTICLES_HOUR=3  # 既読記事クリーンアップ時間（時、JST）
CLEANUP_READ_ARTICLES_MINUTE=0  # 既読記事クリーンアップ時間（分、JST）
CLEANUP_UNREAD_ARTICLES_HOUR=3  # 未読記事クリーンアップ時間（時、JST）
CLEANUP_UNREAD_ARTICLES_MINUTE=10  # 未読記事クリーンアップ時間（分、JST）

# 要約設定
MAX_ARTICLES_TO_SUMMARIZE=10  # 一度に要約する最大記事数
ARTICLE_DESCRIPTION_LIMIT=3000  # 要約時の記事説明文字数制限

# ウェブアプリ設定
ARTICLES_PER_PAGE=20  # 記事一覧の1ページあたりの表示数
HOME_ARTICLES_LIMIT=20  # ホームページの記事表示数
INITIAL_FEED_ARTICLES=5  # 新規フィード追加時の初期取得記事数
STATS_DAYS_PERIOD=7  # 統計情報の期間（日）
ADMIN_EMAIL_LOGS_LIMIT=10  # 管理画面のメールログ表示数

# リクエスト設定
REQUEST_TIMEOUT=30  # HTTP/APIリクエストのタイムアウト（秒）
```

これらの環境変数を調整することで、システムの動作をカスタマイズできます。特に重要なのは：

- `CLEANUP_UNREAD_ARTICLES_LIMIT`: 未読記事の保持上限（デフォルト1000件）
- `CLEANUP_READ_ARTICLES_DAYS`: 既読記事を保持する期間（デフォルト7日）
- `ARTICLE_DESCRIPTION_LIMIT`: 要約時の記事説明文字数制限（デフォルト3000文字）

### 3. Docker Composeで起動

```bash
# コンテナをビルド・起動
docker-compose up -d

# ログを確認
docker-compose logs -f app
```

### 4. ウェブアプリにアクセス

ブラウザで `http://localhost:8000` にアクセス

## 使用方法

### RSSフィードの追加

1. ウェブアプリの「RSS管理」ページにアクセス
2. RSS URLとタイトルを入力して追加
3. 自動的に記事の取得が開始されます

### 記事の閲覧

1. 「記事一覧」ページで記事を検索・フィルタリング
2. 記事タイトルをクリックして詳細表示
3. AI要約（落合フォーマット）を確認

### 管理機能

1. 「管理」ページで手動実行やシステム状態を確認
2. RSS取得、要約メール送信を手動実行可能
3. メール送信履歴やスケジュール情報を確認

## API エンドポイント

### ウェブページ
- `GET /` - ホームページ
- `GET /articles` - 記事一覧
- `GET /article/{id}` - 記事詳細
- `GET /feeds` - RSS管理
- `GET /admin` - 管理画面

### API
- `GET /api/stats` - システム統計情報

### 管理操作
- `POST /admin/fetch-rss` - RSS手動取得
- `POST /admin/send-summary` - 要約メール手動送信
- `POST /admin/test-email` - メールテスト

## スケジュール

- **RSS取得**: 6時間ごと（デフォルト）
- **要約メール送信**: 毎日5:00 JST（デフォルト）
- **既読記事クリーンアップ**: 毎日3:00 JST（デフォルト）
- **未読記事クリーンアップ**: 毎日3:10 JST（デフォルト）

すべてのスケジュールは環境変数で変更可能です。例えば：
- `SUMMARY_EMAIL_HOUR=7` と `SUMMARY_EMAIL_MINUTE=30` で要約メールを7:30 JSTに送信
- `CLEANUP_UNREAD_ARTICLES_LIMIT=2000` で未読記事の上限を2000件に変更

## トラブルシューティング

### メール送信エラー

1. Gmail使用時はアプリパスワードを生成
2. 2段階認証を有効にしてアプリパスワードを設定
3. 管理画面でメールテストを実行

### OpenAI APIエラー

1. APIキーが正しく設定されているか確認
2. OpenAIアカウントに十分なクレジットがあるか確認
3. API利用制限に達していないか確認

### データベース接続エラー

```bash
# データベースコンテナの状態確認
docker-compose ps

# データベースログ確認
docker-compose logs db

# コンテナ再起動
docker-compose restart
```

## 開発

### ローカル開発環境

```bash
# 依存関係インストール
pip install -r requirements.txt

# データベース起動（Docker）
docker-compose up -d db

# アプリケーション起動
python main.py
```

### データベーススキーマ

```bash
# テーブル作成
python database.py
```

## ライセンス

MIT License

## 貢献

プルリクエストやイシューの報告を歓迎します。

## サポート

問題が発生した場合は、以下を確認してください：

1. Docker Composeログ: `docker-compose logs`
2. アプリケーションログ: `docker-compose logs app`
3. データベースログ: `docker-compose logs db`

## 更新履歴

### v1.1.0
- 環境変数による設定の柔軟化
- ハードコードされた数値を環境変数から設定可能に変更
- 未読記事の保持上限を設定可能に
- 既読記事の保持期間を設定可能に
- 各種タイムアウト値やページ表示数を設定可能に

### v1.0.0
- 初回リリース
- RSS自動取得機能
- 落合フォーマット要約機能
- ウェブアプリUI
- メール送信機能
- Docker対応

### TODO
- [ ] ディレクトリきれいにする。
- [ ] コードきれいにする。
- [ ] TTSの実装、お金かかるが。

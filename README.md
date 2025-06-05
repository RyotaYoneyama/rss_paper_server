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

# メール設定 (必須)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_FROM=your_email@gmail.com
EMAIL_TO=recipient@example.com

# その他の設定 (オプション)
MAX_ARTICLES_TO_SUMMARIZE=10
RSS_FETCH_SCHEDULE=0 */6 * * *
SUMMARY_EMAIL_SCHEDULE=0 7 * * *
```

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
- **要約メール送信**: 毎日7:00（デフォルト）

スケジュールは環境変数で変更可能です。

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
- [ ] 時間をcronからやれるようにする。
- [ ] 未読、既読を一括で変更する。
- [ ] ログインパスワードの設定
- [ ] TTSの実装、お金かかるが。
- [ ] setup.shの修正
- [ ] キーワード一覧のページ削除
- [ ] RSSフィード管理のページをきれいにする。
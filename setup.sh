#!/bin/bash

# RSS要約システム セットアップスクリプト

echo "🚀 RSS要約システムのセットアップを開始します..."

# 環境変数ファイルの確認
if [ ! -f .env ]; then
    echo "📝 .envファイルを作成しています..."
    cp .env.example .env
    echo "✅ .envファイルが作成されました"
    echo "⚠️  .envファイルを編集して、OpenAI APIキーとメール設定を入力してください"
    echo ""
    echo "必須設定項目:"
    echo "- OPENAI_API_KEY: OpenAI APIキー"
    echo "- EMAIL_USER: 送信元メールアドレス"
    echo "- EMAIL_PASSWORD: メールパスワード（Gmailの場合はアプリパスワード）"
    echo "- EMAIL_TO: 送信先メールアドレス"
    echo ""
    read -p "設定が完了したらEnterキーを押してください..."
else
    echo "✅ .envファイルが既に存在します"
fi

# Dockerの確認
if ! command -v docker &> /dev/null; then
    echo "❌ Dockerがインストールされていません"
    echo "https://docs.docker.com/get-docker/ からDockerをインストールしてください"
    exit 1
fi

if ! command -v docker compose &> /dev/null; then
    echo "❌ Docker Composeがインストールされていません"
    echo "https://docs.docker.com/compose/install/ からDocker Composeをインストールしてください"
    exit 1
fi

echo "✅ Docker環境が確認できました"

# コンテナのビルドと起動
echo "🔨 Dockerコンテナをビルドしています..."
docker compose build

if [ $? -ne 0 ]; then
    echo "❌ Dockerビルドに失敗しました"
    exit 1
fi

echo "🚀 コンテナを起動しています..."
docker compose up -d

if [ $? -ne 0 ]; then
    echo "❌ コンテナの起動に失敗しました"
    exit 1
fi

# 起動確認
echo "⏳ サービスの起動を待機しています..."
sleep 10

# ヘルスチェック
echo "🔍 サービスの状態を確認しています..."
docker compose ps

# データベースの初期化確認
echo "📊 データベースの初期化を確認しています..."
docker compose exec -T app python -c "from database import create_tables; create_tables(); print('Database tables created successfully!')"

if [ $? -eq 0 ]; then
    echo "✅ データベースの初期化が完了しました"
else
    echo "⚠️  データベースの初期化で問題が発生した可能性があります"
fi

echo ""
echo "🎉 セットアップが完了しました！"
echo ""
echo "📱 ウェブアプリにアクセス: http://localhost:8000"
echo "📊 管理画面: http://localhost:8000/admin"
echo ""
echo "📋 次のステップ:"
echo "1. ウェブブラウザで http://localhost:8000 にアクセス"
echo "2. 「RSS管理」ページでRSSフィードを追加"
echo "3. 「管理」ページでRSS取得とメール送信をテスト"
echo ""
echo "🔧 便利なコマンド:"
echo "- ログ確認: docker compose logs -f app"
echo "- コンテナ停止: docker compose down"
echo "- コンテナ再起動: docker compose restart"
echo ""
echo "❓ 問題が発生した場合は README.md のトラブルシューティングセクションを確認してください"

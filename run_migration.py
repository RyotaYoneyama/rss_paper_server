import os
import subprocess
import logging
from datetime import datetime
from config import settings

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("migration.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def create_backup():
    """データベースのバックアップを作成する関数"""
    logger.info("データベースのバックアップを作成します...")
    
    # データベースURLからデータベース名を取得
    db_url = settings.database_url
    db_name = db_url.split("/")[-1]
    
    # バックアップファイル名（タイムスタンプ付き）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"backup_{db_name}_{timestamp}.sql"
    
    try:
        # SQLiteの場合
        if db_url.startswith("sqlite:"):
            db_path = db_url.replace("sqlite:///", "")
            # ファイルをコピー
            os.system(f"cp {db_path} {db_path}.bak")
            logger.info(f"SQLiteデータベースのバックアップを作成しました: {db_path}.bak")
            return True
        
        # PostgreSQLの場合
        elif db_url.startswith("postgresql:"):
            # 接続情報を解析
            parts = db_url.replace("postgresql://", "").split("/")
            db_name = parts[1]
            auth = parts[0].split("@")
            host_port = auth[1].split(":")
            host = host_port[0]
            port = host_port[1] if len(host_port) > 1 else "5432"
            user_pass = auth[0].split(":")
            user = user_pass[0]
            password = user_pass[1] if len(user_pass) > 1 else ""
            
            # pg_dumpコマンドを実行
            env = os.environ.copy()
            if password:
                env["PGPASSWORD"] = password
            
            cmd = f"pg_dump -h {host} -p {port} -U {user} -F c -b -v -f {backup_file} {db_name}"
            subprocess.run(cmd, shell=True, env=env, check=True)
            
            logger.info(f"PostgreSQLデータベースのバックアップを作成しました: {backup_file}")
            return True
        
        # MySQLの場合
        elif db_url.startswith("mysql:"):
            # 接続情報を解析
            parts = db_url.replace("mysql://", "").split("/")
            db_name = parts[1]
            auth = parts[0].split("@")
            host_port = auth[1].split(":")
            host = host_port[0]
            port = host_port[1] if len(host_port) > 1 else "3306"
            user_pass = auth[0].split(":")
            user = user_pass[0]
            password = user_pass[1] if len(user_pass) > 1 else ""
            
            # mysqldumpコマンドを実行
            cmd = f"mysqldump -h {host} -P {port} -u {user}"
            if password:
                cmd += f" -p{password}"
            cmd += f" {db_name} > {backup_file}"
            
            subprocess.run(cmd, shell=True, check=True)
            
            logger.info(f"MySQLデータベースのバックアップを作成しました: {backup_file}")
            return True
        
        else:
            logger.error(f"サポートされていないデータベースタイプです: {db_url}")
            return False
            
    except Exception as e:
        logger.error(f"バックアップ作成中にエラーが発生しました: {e}")
        return False

def run_migration():
    """マイグレーションを実行する関数"""
    try:
        # 1. データベースのバックアップを作成
        if not create_backup():
            logger.error("バックアップの作成に失敗しました。マイグレーションを中止します。")
            return False
        
        # 2. キーワードデータを移行
        logger.info("キーワードデータの移行を開始します...")
        from migrate_keywords import migrate_keywords
        migrate_keywords()
        
        # 3. データベーススキーマを更新
        logger.info("データベーススキーマの更新を開始します...")
        from update_schema import update_schema
        update_schema()
        
        logger.info("マイグレーションが正常に完了しました。")
        return True
        
    except Exception as e:
        logger.error(f"マイグレーション中にエラーが発生しました: {e}")
        return False

if __name__ == "__main__":
    print("キーワードマイグレーションを開始します...")
    success = run_migration()
    
    if success:
        print("マイグレーションが正常に完了しました。")
    else:
        print("マイグレーション中にエラーが発生しました。ログを確認してください。")

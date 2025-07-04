from sqlalchemy import create_engine, text
from config import settings
import logging

# ロギングの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# データベース接続の設定
engine = create_engine(settings.database_url)

def update_schema():
    """データベーススキーマを更新する関数"""
    logger.info("データベーススキーマの更新を開始します...")
    
    # データベース接続
    conn = engine.connect()
    
    try:
        # トランザクション開始
        trans = conn.begin()
        
        # 1. article_keywords中間テーブルを削除
        logger.info("article_keywordsテーブルを削除します...")
        conn.execute(text("DROP TABLE IF EXISTS article_keywords"))
        
        # 2. keywordsテーブルを削除
        logger.info("keywordsテーブルを削除します...")
        conn.execute(text("DROP TABLE IF EXISTS keywords"))
        
        # トランザクションをコミット
        trans.commit()
        logger.info("データベーススキーマの更新が完了しました")
        
    except Exception as e:
        # エラーが発生した場合はロールバック
        trans.rollback()
        logger.error(f"スキーマ更新中にエラーが発生しました: {e}")
    finally:
        # 接続を閉じる
        conn.close()

if __name__ == "__main__":
    update_schema()
    print("データベーススキーマの更新が完了しました。")

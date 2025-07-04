from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from config import settings
import logging

# ロギングの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# データベース接続の設定
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 古いモデルの定義（マイグレーション用）
article_keywords = Table(
    'article_keywords',
    Base.metadata,
    Column('article_id', Integer, ForeignKey('articles.id'), primary_key=True),
    Column('keyword_id', Integer, ForeignKey('keywords.id'), primary_key=True)
)

class OldKeyword(Base):
    __tablename__ = "keywords"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime)
    
    # Relationship
    articles = relationship("OldArticle", secondary=article_keywords, back_populates="keywords")

class OldArticle(Base):
    __tablename__ = "articles"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    link = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text)
    author = Column(String)
    published_date = Column(DateTime)
    guid = Column(String, unique=True, index=True)
    is_read = Column(Boolean, default=False)
    is_summarized = Column(Boolean, default=False)
    summary = Column(Text)
    keywords_text = Column(Text, name="keywords")  # 新しいフィールド
    
    # 落合フォーマットの各セクション
    top_summary = Column(Text)
    comparison = Column(Text)
    technique = Column(Text)
    validation = Column(Text)
    discussion = Column(Text)
    next_papers = Column(Text)
    
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    
    # Foreign key
    feed_id = Column(Integer, ForeignKey("rss_feeds.id"))
    
    # Relationships
    keywords = relationship("OldKeyword", secondary=article_keywords, back_populates="articles")

def migrate_keywords():
    """キーワードデータを移行する関数"""
    logger.info("キーワードデータの移行を開始します...")
    
    # セッションの作成
    db = SessionLocal()
    
    try:
        # 全ての記事を取得
        articles = db.query(OldArticle).all()
        logger.info(f"移行対象の記事数: {len(articles)}")
        
        # 各記事のキーワードをカンマ区切りの文字列に変換
        for article in articles:
            if article.keywords:
                # キーワード名のリストを作成
                keyword_names = [keyword.name for keyword in article.keywords]
                # カンマ区切りの文字列に変換
                keywords_str = ','.join(keyword_names)
                
                # SQLインジェクション対策
                keywords_str = keywords_str.replace("'", "''")
                
                # SQLAlchemyのORM経由ではなく、直接SQLを実行して更新
                # これにより、新しいモデル定義との競合を避ける
                db.execute(
                    f"UPDATE articles SET keywords = '{keywords_str}' WHERE id = {article.id}"
                )
                
                logger.info(f"記事ID {article.id} のキーワードを移行: {keywords_str}")
        
        # 変更をコミット
        db.commit()
        logger.info("キーワードデータの移行が完了しました")
        
    except Exception as e:
        db.rollback()
        logger.error(f"移行中にエラーが発生しました: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    migrate_keywords()
    print("キーワードの移行が完了しました。")

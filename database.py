from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func
from datetime import datetime
import pytz
from config import settings
from passlib.context import CryptContext

# JSTタイムゾーンを設定
jst = pytz.timezone('Asia/Tokyo')

# 現在のJST時間を取得する関数
def get_jst_now():
    return datetime.now(jst)

# Database setup
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Association table for many-to-many relationship between articles and keywords
article_keywords = Table(
    'article_keywords',
    Base.metadata,
    Column('article_id', Integer, ForeignKey('articles.id'), primary_key=True),
    Column('keyword_id', Integer, ForeignKey('keywords.id'), primary_key=True)
)


class RSSFeed(Base):
    __tablename__ = "rss_feeds"
    
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    filter_keywords = Column(Text, nullable=True)  # フィードごとのフィルタリングキーワード
    created_at = Column(DateTime, default=get_jst_now)
    updated_at = Column(DateTime, default=get_jst_now, onupdate=get_jst_now)
    
    # Relationship
    articles = relationship("Article", back_populates="feed")


class Article(Base):
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
    
    # 落合フォーマットの各セクション
    top_summary = Column(Text)  # 1. どんなもの？
    comparison = Column(Text)   # 2. 先行研究と比べてどこがすごい？
    technique = Column(Text)    # 3. 技術や手法のキモはどこ？
    validation = Column(Text)   # 4. どうやって有効だと検証した？
    discussion = Column(Text)   # 5. 議論はある？
    next_papers = Column(Text)  # 6. 次読むべき論文は？
    
    created_at = Column(DateTime, default=get_jst_now)
    updated_at = Column(DateTime, default=get_jst_now, onupdate=get_jst_now)
    
    # Foreign key
    feed_id = Column(Integer, ForeignKey("rss_feeds.id"))
    
    # Relationships
    feed = relationship("RSSFeed", back_populates="articles")
    keywords = relationship("Keyword", secondary=article_keywords, back_populates="articles")


class Keyword(Base):
    __tablename__ = "keywords"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=get_jst_now)
    
    # Relationship
    articles = relationship("Article", secondary=article_keywords, back_populates="keywords")


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=get_jst_now)
    updated_at = Column(DateTime, default=get_jst_now, onupdate=get_jst_now)


class EmailLog(Base):
    __tablename__ = "email_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    recipient = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    articles_count = Column(Integer, default=0)
    sent_at = Column(DateTime, default=get_jst_now)
    status = Column(String, default="sent")  # sent, failed


# パスワードハッシュ化のためのユーティリティ
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    create_tables()
    print("Database tables created successfully!")

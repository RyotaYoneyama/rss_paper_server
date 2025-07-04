import feedparser
import requests
from datetime import datetime, timezone, timedelta
import pytz
from sqlalchemy.orm import Session
from database import get_db, Article, RSSFeed
from typing import List, Optional, Tuple
import logging
from bs4 import BeautifulSoup
import re
from filter_parser import FilterParser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RSSFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'RSS Summarizer Bot 1.0'
        })
        # Import summarizer here to avoid circular imports
        from summarizer import ArticleSummarizer
        self.summarizer = ArticleSummarizer()
        # フィルターパーサーを初期化
        self.filter_parser = FilterParser()

    def fetch_feed(self, feed_url: str) -> Optional[dict]:
        """Fetch RSS feed from URL"""
        try:
            response = self.session.get(feed_url, timeout=30)
            response.raise_for_status()
            
            feed = feedparser.parse(response.content)
            if feed.bozo:
                logger.warning(f"Feed parsing warning for {feed_url}: {feed.bozo_exception}")
            
            return feed
        except Exception as e:
            logger.error(f"Error fetching feed {feed_url}: {e}")
            return None

    def clean_html(self, html_content: str) -> str:
        """Clean HTML content and extract text"""
        if not html_content:
            return ""
        
        soup = BeautifulSoup(html_content, 'html.parser')
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Get text and clean it
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        return text

    def parse_date(self, date_string: str) -> Optional[datetime]:
        """Parse date string to datetime object and convert to JST"""
        if not date_string:
            return None
        
        try:
            if date_string:
                # Create UTC datetime
                utc_dt = datetime(*date_string[:6], tzinfo=timezone.utc)
                
                # Convert to JST (UTC+9)
                jst = pytz.timezone('Asia/Tokyo')
                jst_dt = utc_dt.astimezone(jst)
                
                return jst_dt
        except Exception as e:
            logger.error(f"Error parsing date: {e}")
            pass
        
        return None

    def article_exists(self, db: Session, link: str, guid: str = None) -> bool:
        """Check if article already exists in database"""
        query = db.query(Article).filter(Article.link == link)
        if guid:
            query = query.filter(Article.guid == guid)
        return query.first() is not None

    def check_keywords_match(self, db: Session, title: str, description: str, feed: RSSFeed = None) -> Tuple[str, List[str]]:
        """
        Check if title or description matches the filter expression
        Returns a tuple of (result, matching_keywords)
        
        フィルター式の構文:
        - 単純なキーワード: "keyword"
        - カンマ区切りのキーワード: "keyword1, keyword2" (いずれかがマッチすればOK)
        - OR演算: "keyword1 OR keyword2" (いずれかがマッチすればOK)
        - AND演算: "keyword1 AND keyword2" (両方がマッチする必要あり)
        - グループ化: "(keyword1 OR keyword2) AND keyword3"
        """
        # タイトルと説明文を結合したテキスト
        text = f"{title} {description}"
        logger.info(f"Article : {feed.filter_keywords}")
        
        # フィルターキーワードがない場合
        if feed.filter_keywords is None or feed.filter_keywords.strip() == '':
            return "None", []
        
        try:
            # フィルター式を解析して評価
            matches, matching_keywords = self.filter_parser.parse_and_evaluate(feed.filter_keywords, text)
            
            # マッチするかどうかの結果を返す
            result = "Match" if matches else "None"
            return result, matching_keywords
            
        except Exception as e:
            logger.error(f"フィルター式の評価中にエラーが発生しました: {e}")
            # エラーが発生した場合は、従来の方法でフィルタリング
            feed_keywords = [kw.strip() for kw in feed.filter_keywords.split(',') if kw.strip()]
            matching_keywords = []
            for keyword in feed_keywords:
                if keyword.lower() in text.lower():
                    matching_keywords.append(keyword)
            
            result = "None" if len(matching_keywords) == 0 else "Match"
            return result, matching_keywords

    def save_article(self, db: Session, feed: RSSFeed, entry: dict) -> Optional[Article]:
        """Save article to database"""
        try:
            # Extract article data
            title = entry.get('title', 'No Title')
            link = entry.get('link', '')
            description = self.clean_html(entry.get('description', ''))
            author = entry.get('author', '')
            published_date = self.parse_date(entry.get('published_parsed', ''))
            guid = entry.get('guid', link)

            # Check if article already exists
            if self.article_exists(db, link, guid):
                logger.info(f"Article already exists: {title}")
                return None

            # Check if article matches any keywords
            result, matching_keywords = self.check_keywords_match(db, title, description, feed)
            if result == "None":
                logger.info(f"Article does not match any keywords: {title}")
                return None

            # Create new article
            article = Article(
                title=title,
                link=link,
                description=description,
                author=author,
                published_date=published_date,
                guid=guid,
                feed_id=feed.id
            )

            db.add(article)
            db.flush()  # Get the article ID

            # キーワードをカンマ区切りの文字列として保存
            article.keywords = ','.join(matching_keywords)

            # Create summary immediately after saving
            logger.info(f"Creating summary for new article: {title}")
            summary = self.summarizer.create_ochiai_summary(article)
            article.summary = summary
            article.is_summarized = True
            
            db.commit()
            logger.info(f"Saved new article with summary: {title}")
            return article

        except Exception as e:
            db.rollback()
            logger.error(f"Error saving article: {e}")
            return None

    def fetch_all_feeds(self):
        """Fetch all active RSS feeds and save new articles"""
        db = next(get_db())
        try:
            feeds = db.query(RSSFeed).filter(RSSFeed.is_active == True).all()
            
            total_new_articles = 0
            for feed in feeds:
                logger.info(f"Fetching feed: {feed.title} ({feed.url})")
                
                feed_data = self.fetch_feed(feed.url)
                if not feed_data:
                    continue

                # Update feed info if available
                if hasattr(feed_data.feed, 'title') and feed_data.feed.title:
                    feed.title = feed_data.feed.title
                if hasattr(feed_data.feed, 'description') and feed_data.feed.description:
                    feed.description = feed_data.feed.description

                # Process entries
                new_articles_count = 0
                for entry in feed_data.entries:
                    article = self.save_article(db, feed, entry)
                    if article:
                        new_articles_count += 1

                total_new_articles += new_articles_count
                logger.info(f"Added {new_articles_count} new articles from {feed.title}")

            db.commit()
            logger.info(f"Total new articles added: {total_new_articles}")
            return total_new_articles

        except Exception as e:
            db.rollback()
            logger.error(f"Error in fetch_all_feeds: {e}")
            return 0
        finally:
            db.close()


if __name__ == "__main__":
    fetcher = RSSFetcher()
    fetcher.fetch_all_feeds()

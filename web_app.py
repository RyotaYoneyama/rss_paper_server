from fastapi import FastAPI, Depends, HTTPException, Request, Form, Body
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, or_
from database import get_db, Article, RSSFeed, Keyword, EmailLog
from rss_fetcher import RSSFetcher
from summarizer import ArticleSummarizer
from email_sender import EmailSender
from scheduler import TaskScheduler
from typing import List, Optional
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="RSS Summarizer", description="RSS記事要約システム")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Initialize components
rss_fetcher = RSSFetcher()
summarizer = ArticleSummarizer()
email_sender = EmailSender()
scheduler = TaskScheduler()


@app.on_event("startup")
async def startup_event():
    """Initialize database and start scheduler"""
    from database import create_tables
    create_tables()
    
    # Start scheduler
    scheduler.start()
    logger.info("Application started with scheduler")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop scheduler on shutdown"""
    scheduler.stop()
    logger.info("Application shutdown")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    """Home page with article list"""
    # Get recent articles
    articles = db.query(Article).order_by(desc(Article.created_at)).limit(20).all()
    
    # Get statistics
    total_articles = db.query(Article).count()
    unread_articles = db.query(Article).filter(Article.is_read == False).count()
    total_feeds = db.query(RSSFeed).filter(RSSFeed.is_active == True).count()
    
    stats = {
        'total_articles': total_articles,
        'unread_articles': unread_articles,
        'total_feeds': total_feeds
    }
    
    return templates.TemplateResponse("home.html", {
        "request": request,
        "articles": articles,
        "stats": stats
    })


@app.get("/articles", response_class=HTMLResponse)
async def articles_list(
    request: Request,
    page: int = 1,
    keyword: Optional[str] = None,
    feed_id: Optional[str] = None,
    unread_only: bool = False,
    db: Session = Depends(get_db)
):
    """Articles list with filtering"""
    per_page = 20
    offset = (page - 1) * per_page
    
    # Build query
    query = db.query(Article)
    
    if unread_only:
        query = query.filter(Article.is_read == False)
    
    if feed_id:
        if feed_id != "すべて":
            try:
                feed_id = int(feed_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid feed ID")
        query = query.filter(Article.feed_id == feed_id)
    
    if keyword:
        query = query.join(Article.keywords).filter(Keyword.name.ilike(f"%{keyword}%"))
    
    # Get total count
    total = query.count()
    
    # Get articles for current page
    articles = query.order_by(desc(Article.created_at)).offset(offset).limit(per_page).all()
    
    # Get feeds for filter dropdown
    feeds = db.query(RSSFeed).filter(RSSFeed.is_active == True).all()
    
    # Get keywords for filter
    keywords = db.query(Keyword).limit(50).all()
    
    # Calculate pagination
    total_pages = (total + per_page - 1) // per_page
    
    return templates.TemplateResponse("articles.html", {
        "request": request,
        "articles": articles,
        "feeds": feeds,
        "keywords": keywords,
        "current_page": page,
        "total_pages": total_pages,
        "total_articles": total,
        "selected_keyword": keyword,
        "selected_feed_id": feed_id,
        "unread_only": unread_only
    })


@app.get("/article/{article_id}", response_class=HTMLResponse)
async def article_detail(request: Request, article_id: int, db: Session = Depends(get_db)):
    """Article detail page"""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    # Mark as read
    if not article.is_read:
        article.is_read = True
        db.commit()
    
    return templates.TemplateResponse("article_detail.html", {
        "request": request,
        "article": article
    })


@app.get("/feeds", response_class=HTMLResponse)
async def feeds_list(request: Request, db: Session = Depends(get_db)):
    """RSS feeds management page"""
    feeds = db.query(RSSFeed).order_by(desc(RSSFeed.created_at)).all()
    
    return templates.TemplateResponse("feeds.html", {
        "request": request,
        "feeds": feeds
    })


@app.get("/keywords", response_class=HTMLResponse)
async def keywords_list(request: Request, db: Session = Depends(get_db)):
    """Keywords management page"""
    keywords = db.query(Keyword).order_by(desc(Keyword.created_at)).all()
    
    return templates.TemplateResponse("keywords.html", {
        "request": request,
        "keywords": keywords
    })


@app.post("/keywords/add")
async def add_keyword(name: str = Form(...), db: Session = Depends(get_db)):
    """Add new keyword"""
    try:
        # Check if keyword already exists
        existing_keyword = db.query(Keyword).filter(Keyword.name == name).first()
        if existing_keyword:
            raise HTTPException(status_code=400, detail="Keyword already exists")
        
        # Create new keyword
        keyword = Keyword(name=name)
        db.add(keyword)
        db.commit()
        
        return RedirectResponse(url="/keywords", status_code=303)
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/keywords/{keyword_id}/toggle")
async def toggle_keyword(keyword_id: int, db: Session = Depends(get_db)):
    """Toggle keyword active status"""
    keyword = db.query(Keyword).filter(Keyword.id == keyword_id).first()
    if not keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")
    
    keyword.is_active = not keyword.is_active
    db.commit()
    
    return RedirectResponse(url="/keywords", status_code=303)


@app.post("/keywords/{keyword_id}/delete")
async def delete_keyword(keyword_id: int, db: Session = Depends(get_db)):
    """Delete keyword"""
    keyword = db.query(Keyword).filter(Keyword.id == keyword_id).first()
    if not keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")
    
    db.delete(keyword)
    db.commit()
    
    return RedirectResponse(url="/keywords", status_code=303)


@app.post("/feeds/add")
async def add_feed(url: str = Form(...), title: str = Form(...), filter_keywords: str = Form(None), db: Session = Depends(get_db)):
    """Add new RSS feed"""
    try:
        # Check if feed already exists
        existing_feed = db.query(RSSFeed).filter(RSSFeed.url == url).first()
        if existing_feed:
            raise HTTPException(status_code=400, detail="Feed already exists")
        
        # Create new feed
        feed = RSSFeed(url=url, title=title, filter_keywords=filter_keywords)
        db.add(feed)
        db.commit()
        
        # Try to fetch articles immediately
        try:
            feed_data = rss_fetcher.fetch_feed(url)
            if feed_data:
                for entry in feed_data.entries[:5]:  # Limit to 5 articles for initial fetch
                    rss_fetcher.save_article(db, feed, entry)
        except Exception as e:
            logger.warning(f"Could not fetch articles for new feed: {e}")
        
        return RedirectResponse(url="/feeds", status_code=303)
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/feeds/{feed_id}/update-filter")
async def update_feed_filter(feed_id: int, filter_keywords: str = Form(None), db: Session = Depends(get_db)):
    """Update feed filter keywords"""
    feed = db.query(RSSFeed).filter(RSSFeed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    
    feed.filter_keywords = filter_keywords
    db.commit()
    logger.info(f"Updated filter keywords for feed {feed_id}: {filter_keywords}")
    
    return RedirectResponse(url="/feeds", status_code=303)


@app.post("/feeds/{feed_id}/toggle")
async def toggle_feed(feed_id: int, db: Session = Depends(get_db)):
    """Toggle feed active status"""
    feed = db.query(RSSFeed).filter(RSSFeed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    
    feed.is_active = not feed.is_active
    db.commit()
    
    return RedirectResponse(url="/feeds", status_code=303)


@app.post("/feeds/{feed_id}/delete")
async def delete_feed(feed_id: int, db: Session = Depends(get_db)):
    """Delete RSS feed"""
    feed = db.query(RSSFeed).filter(RSSFeed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    
    db.delete(feed)
    db.commit()
    
    return RedirectResponse(url="/feeds", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, db: Session = Depends(get_db)):
    """Admin panel"""
    # Get recent email logs
    email_logs = db.query(EmailLog).order_by(desc(EmailLog.sent_at)).limit(10).all()
    
    # Get schedule info
    schedule_info = scheduler.get_schedule_info()
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "email_logs": email_logs,
        "schedule_info": schedule_info
    })


@app.post("/admin/fetch-rss")
async def manual_fetch_rss():
    """Manually trigger RSS fetch"""
    scheduler.run_manual_fetch()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/send-summary")
async def manual_send_summary():
    """Manually trigger summary email"""
    scheduler.run_manual_summary()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/test-email")
async def test_email():
    """Test email configuration"""
    success = email_sender.test_email_connection()
    if success:
        test_content = "# テストメール\n\nRSS要約システムのメール設定テストです。"
        email_sender.send_email(
            email_sender.from_email,
            "RSS要約システム - テストメール",
            test_content
        )
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/summarize-all")
async def summarize_all_articles():
    """Summarize all unsummarized articles"""
    count = summarizer.summarize_unsummarized_articles()
    logger.info(f"Summarized {count} articles")
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/article/{article_id}/delete")
async def delete_article(article_id: int, db: Session = Depends(get_db)):
    """Delete an article"""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="記事が見つかりません")
    
    # Delete the article
    db.delete(article)
    db.commit()
    logger.info(f"Article {article_id} deleted")
    
    # Redirect to articles list
    return RedirectResponse(url="/articles", status_code=303)


@app.post("/articles/delete-multiple")
async def delete_multiple_articles(article_ids: List[int] = Body(...), db: Session = Depends(get_db)):
    """選択した複数の記事を削除"""
    try:
        # article_idsがリストでない場合（単一のIDが送信された場合）、リストに変換
        if not isinstance(article_ids, list):
            article_ids = [article_ids]
        
        # 空のリストの場合は何もしない
        if not article_ids:
            return {"deleted": 0}
        
        # 関連するarticle_keywordsテーブルのレコードを先に削除
        # SQLAlchemyのORM削除を使用して、各記事を個別に削除する
        deleted_count = 0
        for article_id in article_ids:
            article = db.query(Article).filter(Article.id == article_id).first()
            if article:
                # 記事を削除すると、SQLAlchemyが自動的に関連するarticle_keywordsのレコードも削除する
                db.delete(article)
                deleted_count += 1
        
        db.commit()
        logger.info(f"Deleted {deleted_count} articles (IDs: {article_ids})")
        return {"deleted": deleted_count}
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting multiple articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def get_stats(db: Session = Depends(get_db)):
    """API endpoint for statistics"""
    total_articles = db.query(Article).count()
    unread_articles = db.query(Article).filter(Article.is_read == False).count()
    total_feeds = db.query(RSSFeed).filter(RSSFeed.is_active == True).count()
    
    # Articles by day (last 7 days)
    seven_days_ago = datetime.now() - timedelta(days=7)
    recent_articles = db.query(Article).filter(Article.created_at >= seven_days_ago).all()
    
    articles_by_day = {}
    for article in recent_articles:
        day = article.created_at.strftime('%Y-%m-%d')
        articles_by_day[day] = articles_by_day.get(day, 0) + 1
    
    return {
        "total_articles": total_articles,
        "unread_articles": unread_articles,
        "total_feeds": total_feeds,
        "articles_by_day": articles_by_day
    }


if __name__ == "__main__":
    import uvicorn
    from config import settings
    
    uvicorn.run(
        "web_app:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug
    )

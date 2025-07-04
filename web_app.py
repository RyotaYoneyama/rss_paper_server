from fastapi import FastAPI, Depends, HTTPException, Request, Form, Body, Cookie, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, or_
from database import get_db, Article, RSSFeed, EmailLog, User, get_password_hash
from auth import authenticate_user, create_access_token, get_current_user, get_current_active_user, get_current_admin_user, Token
from rss_fetcher import RSSFetcher
from summarizer import ArticleSummarizer
from email_sender import EmailSender
from scheduler import TaskScheduler
from typing import List, Optional
from datetime import datetime, timedelta
import logging
from config import settings

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

# Get current user from cookie for templates
async def get_user_from_cookie(request: Request, db: Session = Depends(get_db)):
    try:
        from auth import get_optional_user
        user = await get_optional_user(request=request, db=db)
        return user
    except:
        return None

# Add middleware to make current_user available in all templates and redirect to login if not authenticated
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # パスがログインページ、静的ファイル、またはAPIエンドポイントの場合は認証をスキップ
    path = request.url.path
    if path == "/login" or path.startswith("/static") or path.startswith("/api"):
        return await call_next(request)
    
    # クッキーからトークンを取得
    token = request.cookies.get("access_token")
    if not token or not token.startswith("Bearer "):
        # ログインしていない場合はログインページにリダイレクト
        return RedirectResponse(url="/login", status_code=303)
    
    # トークンがある場合は通常の処理を続行
    response = await call_next(request)
    return response


@app.on_event("startup")
async def startup_event():
    """Initialize database and start scheduler"""
    from database import create_tables, get_password_hash, User, SessionLocal
    create_tables()
    
    # Create default admin user if no users exist
    db = SessionLocal()
    try:
        user_count = db.query(User).count()
        if user_count == 0:
            # Create default admin user
            admin_user = User(
                username="admin",
                email="admin@example.com",
                hashed_password=get_password_hash("admin"),
                is_active=True,
                is_admin=True
            )
            db.add(admin_user)
            db.commit()
            logger.info("Created default admin user (username: admin, password: admin)")
    except Exception as e:
        logger.error(f"Error creating default admin user: {e}")
    finally:
        db.close()
    
    # Start scheduler
    scheduler.start()
    logger.info("Application started with scheduler")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop scheduler on shutdown"""
    scheduler.stop()
    logger.info("Application shutdown")


# Authentication endpoints
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": None
    })


@app.post("/login")
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Login and get access token"""
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "ユーザー名またはパスワードが正しくありません"
        }, status_code=400)
    
    if not user.is_active:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "このアカウントは無効化されています"
        }, status_code=400)
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    # Set cookie
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=settings.access_token_expire_minutes * 60,
        expires=settings.access_token_expire_minutes * 60,
    )
    
    return response


@app.post("/logout")
async def logout(response: Response):
    """Logout and clear cookie"""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="access_token")
    return response


# User management endpoints
@app.get("/users", response_class=HTMLResponse)
async def users_list(
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Users management page (admin only)"""
    users = db.query(User).order_by(desc(User.created_at)).all()
    
    return templates.TemplateResponse("users.html", {
        "request": request,
        "users": users,
        "current_user": current_user
    })


@app.post("/users/add")
async def add_user(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    is_admin: bool = Form(False),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Add new user (admin only)"""
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()
        
        if existing_user:
            if existing_user.username == username:
                raise HTTPException(status_code=400, detail="このユーザー名は既に使用されています")
            else:
                raise HTTPException(status_code=400, detail="このメールアドレスは既に使用されています")
        
        # Create new user
        hashed_password = get_password_hash(password)
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            is_admin=is_admin
        )
        db.add(user)
        db.commit()
        
        return RedirectResponse(url="/users", status_code=303)
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/users/{user_id}/update")
async def update_user(
    user_id: int,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(None),
    is_admin: bool = Form(False),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Update user (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
    
    # Check if username or email is already taken by another user
    existing_user = db.query(User).filter(
        (User.username == username) | (User.email == email),
        User.id != user_id
    ).first()
    
    if existing_user:
        if existing_user.username == username:
            raise HTTPException(status_code=400, detail="このユーザー名は既に使用されています")
        else:
            raise HTTPException(status_code=400, detail="このメールアドレスは既に使用されています")
    
    # Update user
    user.username = username
    user.email = email
    if password:
        user.hashed_password = get_password_hash(password)
    user.is_admin = is_admin
    
    db.commit()
    
    return RedirectResponse(url="/users", status_code=303)


@app.post("/users/{user_id}/toggle")
async def toggle_user(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Toggle user active status (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
    
    # Prevent deactivating yourself
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="自分自身を無効化することはできません")
    
    user.is_active = not user.is_active
    db.commit()
    
    return RedirectResponse(url="/users", status_code=303)


@app.post("/users/{user_id}/delete")
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Delete user (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
    
    # Prevent deleting yourself
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="自分自身を削除することはできません")
    
    db.delete(user)
    db.commit()
    
    return RedirectResponse(url="/users", status_code=303)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    """Home page with article list"""
    # Get current user from cookie
    current_user = await get_user_from_cookie(request, db)
    
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
        "stats": stats,
        "current_user": current_user
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
    # Get current user from cookie
    current_user = await get_user_from_cookie(request, db)
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
        query = query.filter(Article.keywords.ilike(f"%{keyword}%"))
    
    # Get total count
    total = query.count()
    
    # Get articles for current page
    articles = query.order_by(desc(Article.created_at)).offset(offset).limit(per_page).all()
    
    # Get feeds for filter dropdown
    feeds = db.query(RSSFeed).filter(RSSFeed.is_active == True).all()
    
    # Get unique keywords from articles for filter
    keywords_query = db.query(Article.keywords).filter(Article.keywords != None).distinct()
    keywords = []
    for k in keywords_query:
        if k[0]:  # Check if keywords is not None
            for keyword in k[0].split(','):
                if keyword.strip() and keyword.strip() not in [k.strip() for k in keywords]:
                    keywords.append({"name": keyword.strip()})
    
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
        "unread_only": unread_only,
        "current_user": current_user
    })


@app.get("/article/{article_id}", response_class=HTMLResponse)
async def article_detail(request: Request, article_id: int, db: Session = Depends(get_db)):
    """Article detail page"""
    # Get current user from cookie
    current_user = await get_user_from_cookie(request, db)
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    # Mark as read
    if not article.is_read:
        article.is_read = True
        db.commit()
    
    return templates.TemplateResponse("article_detail.html", {
        "request": request,
        "article": article,
        "current_user": current_user
    })


@app.get("/feeds", response_class=HTMLResponse)
async def feeds_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """RSS feeds management page"""
    feeds = db.query(RSSFeed).order_by(desc(RSSFeed.created_at)).all()
    
    return templates.TemplateResponse("feeds.html", {
        "request": request,
        "feeds": feeds,
        "current_user": current_user
    })




@app.post("/feeds/add")
async def add_feed(
    url: str = Form(...),
    title: str = Form(...),
    filter_keywords: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
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
async def update_feed_filter(
    feed_id: int,
    filter_keywords: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update feed filter keywords"""
    feed = db.query(RSSFeed).filter(RSSFeed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    
    feed.filter_keywords = filter_keywords
    db.commit()
    logger.info(f"Updated filter keywords for feed {feed_id}: {filter_keywords}")
    
    return RedirectResponse(url="/feeds", status_code=303)


@app.post("/feeds/{feed_id}/toggle")
async def toggle_feed(
    feed_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Toggle feed active status"""
    feed = db.query(RSSFeed).filter(RSSFeed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    
    feed.is_active = not feed.is_active
    db.commit()
    
    return RedirectResponse(url="/feeds", status_code=303)


@app.post("/feeds/{feed_id}/delete")
async def delete_feed(
    feed_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete RSS feed"""
    feed = db.query(RSSFeed).filter(RSSFeed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    
    db.delete(feed)
    db.commit()
    
    return RedirectResponse(url="/feeds", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Admin panel"""
    # Get recent email logs
    email_logs = db.query(EmailLog).order_by(desc(EmailLog.sent_at)).limit(10).all()
    
    # Get schedule info
    schedule_info = scheduler.get_schedule_info()
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "email_logs": email_logs,
        "schedule_info": schedule_info,
        "current_user": current_user
    })


@app.post("/admin/fetch-rss")
async def manual_fetch_rss(current_user: User = Depends(get_current_admin_user)):
    """Manually trigger RSS fetch"""
    scheduler.run_manual_fetch()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/send-summary")
async def manual_send_summary(current_user: User = Depends(get_current_admin_user)):
    """Manually trigger summary email"""
    scheduler.run_manual_summary()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/test-email")
async def test_email(current_user: User = Depends(get_current_admin_user)):
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
async def summarize_all_articles(current_user: User = Depends(get_current_admin_user)):
    """Summarize all unsummarized articles"""
    count = summarizer.summarize_unsummarized_articles()
    logger.info(f"Summarized {count} articles")
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/article/{article_id}/delete")
async def delete_article(
    article_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
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
async def delete_multiple_articles(
    article_ids: List[int] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
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

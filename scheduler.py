import schedule
import time
import threading
from datetime import datetime, timedelta
import logging
from rss_fetcher import RSSFetcher
from summarizer import ArticleSummarizer
from email_sender import EmailSender
from config import settings
from database import get_db, Article
from sqlalchemy.orm import Session
from sqlalchemy import and_

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TaskScheduler:
    def __init__(self):
        self.rss_fetcher = RSSFetcher()
        self.summarizer = ArticleSummarizer()
        self.email_sender = EmailSender()
        self.running = False

    def fetch_rss_job(self):
        """Job to fetch RSS feeds"""
        logger.info("Starting RSS fetch job")
        try:
            new_articles = self.rss_fetcher.fetch_all_feeds()
            logger.info(f"RSS fetch job completed. New articles: {new_articles}")
        except Exception as e:
            logger.error(f"Error in RSS fetch job: {e}")

    def send_summary_email_job(self):
        """Job to send daily summary email"""
        logger.info("Starting summary email job")
        try:
            # Get summary content
            content = self.summarizer.summarize_unread_articles()
            
            # Count articles in content (rough estimate)
            articles_count = content.count('## ') if '## ' in content else 0
            
            # Send email
            success = self.email_sender.send_daily_summary(content, articles_count)
            
            if success:
                logger.info(f"Summary email sent successfully. Articles: {articles_count}")
            else:
                logger.error("Failed to send summary email")
                
        except Exception as e:
            logger.error(f"Error in summary email job: {e}")

    def cleanup_read_articles_job(self):
        """既読かつ1週間以上前の記事を削除"""
        logger.info("Starting cleanup of read articles older than 1 week")
        try:
            db: Session = next(get_db())
            one_week_ago = datetime.utcnow() - timedelta(days=7)
            deleted = db.query(Article).filter(
                and_(
                    Article.is_read == True,
                    Article.read_at != None,
                    Article.read_at < one_week_ago
                )
            ).delete(synchronize_session=False)
            db.commit()
            logger.info(f"Deleted {deleted} read articles older than 1 week")
        except Exception as e:
            logger.error(f"Error in cleanup_read_articles_job: {e}")

    def cleanup_unread_articles_job(self):
        """未読記事が1000件を超えた場合、古い順に削除"""
        logger.info("Starting cleanup of unread articles if over limit")
        try:
            db: Session = next(get_db())
            unread_count = db.query(Article).filter(Article.is_read == False).count()
            limit = 1000
            if unread_count > limit:
                to_delete = unread_count - limit
                old_unread = db.query(Article).filter(Article.is_read == False).order_by(Article.published_at.asc()).limit(to_delete).all()
                ids = [a.id for a in old_unread]
                deleted = db.query(Article).filter(Article.id.in_(ids)).delete(synchronize_session=False)
                db.commit()
                logger.info(f"Deleted {deleted} old unread articles to keep under {limit}")
        except Exception as e:
            logger.error(f"Error in cleanup_unread_articles_job: {e}")

    def setup_schedules(self):
        """Setup scheduled jobs"""
        # Parse cron-like schedule for RSS fetching (simplified)
        # For now, we'll use simple schedule library syntax
        # RSS fetch every 6 hours
        schedule.every(6).hours.do(self.fetch_rss_job)
        
        # Summary email every day at 5 AM JST
        import pytz

        def run_summary_email_jst():
            jst = pytz.timezone('Asia/Tokyo')
            now_jst = datetime.now(jst)
            if now_jst.hour == 5 and now_jst.minute == 0:
                self.send_summary_email_job()
        schedule.every().minute.do(run_summary_email_jst)

        def run_cleanup_read_articles_jst():
            jst = pytz.timezone('Asia/Tokyo')
            now_jst = datetime.now(jst)
            if now_jst.hour == 3 and now_jst.minute == 0:
                self.cleanup_read_articles_job()
        schedule.every().minute.do(run_cleanup_read_articles_jst)

        def run_cleanup_unread_articles_jst():
            jst = pytz.timezone('Asia/Tokyo')
            now_jst = datetime.now(jst)
            if now_jst.hour == 3 and now_jst.minute == 10:
                self.cleanup_unread_articles_job()
        schedule.every().minute.do(run_cleanup_unread_articles_jst)

        logger.info("Scheduled jobs configured:")
        logger.info("- RSS fetch: Every 6 hours")
        logger.info("- Summary email: Daily at 5:00 AM JST")
        logger.info("- Cleanup read articles: Daily at 03:00 JST")
        logger.info("- Cleanup unread articles: Daily at 03:10 JST")

    def run_scheduler(self):
        """Run the scheduler in a separate thread"""
        self.running = True
        logger.info("Scheduler started")
        
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in scheduler: {e}")
                time.sleep(60)

    def start(self):
        """Start the scheduler"""
        self.setup_schedules()
        
        # Run initial RSS fetch
        logger.info("Running initial RSS fetch...")
        self.fetch_rss_job()
        
        # Start scheduler in background thread
        scheduler_thread = threading.Thread(target=self.run_scheduler, daemon=True)
        scheduler_thread.start()
        
        return scheduler_thread

    def stop(self):
        """Stop the scheduler"""
        self.running = False
        logger.info("Scheduler stopped")

    def run_manual_fetch(self):
        """Manually trigger RSS fetch"""
        logger.info("Manual RSS fetch triggered")
        self.fetch_rss_job()

    def run_manual_summary(self):
        """Manually trigger summary email"""
        logger.info("Manual summary email triggered")
        self.send_summary_email_job()

    def get_schedule_info(self):
        """Get information about scheduled jobs"""
        jobs = []
        for job in schedule.jobs:
            jobs.append({
                'job': str(job.job_func.__name__),
                'next_run': job.next_run.strftime('%Y-%m-%d %H:%M:%S') if job.next_run else 'Not scheduled',
                'interval': str(job.interval),
                'unit': job.unit
            })
        return jobs


if __name__ == "__main__":
    scheduler = TaskScheduler()
    
    try:
        # Start scheduler
        thread = scheduler.start()
        
        print("Scheduler is running. Press Ctrl+C to stop.")
        
        # Keep main thread alive
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("Stopping scheduler...")
        scheduler.stop()
        print("Scheduler stopped.")

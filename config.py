from pydantic_settings import BaseSettings
from typing import List, Optional
import os
from datetime import timedelta
import secrets


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://rss_user:rss_password@db:5432/rss_db"
    
    # OpenAI
    openai_api_key: str
    openai_temperature: float = 1.0
    
    # Email
    email_enabled: bool = True
    email_host: str = "smtp.gmail.com"
    email_port: int = 587
    email_user: str
    email_password: str
    email_from: str
    email_to: str
    email_log_content_length: int = 1000
    
    # Scheduling
    scheduler_check_interval: int = 60  # seconds
    cleanup_read_articles_days: int = 7  # days
    cleanup_unread_articles_limit: int = 1000  # articles
    cleanup_read_articles_hour: int = 3  # hour (JST)
    cleanup_read_articles_minute: int = 0  # minute
    cleanup_unread_articles_hour: int = 3  # hour (JST)
    cleanup_unread_articles_minute: int = 10  # minute
    summary_email_hour: int = 5  # hour (JST)
    summary_email_minute: int = 0  # minute
    
    # Summary settings
    max_articles_to_summarize: int = 10
    article_description_limit: int = 3000  # characters
    
    # App settings
    app_host: str = "0.0.0.0"
    app_port: int = 3045
    debug: bool = False
    
    # Web app settings
    articles_per_page: int = 20
    home_articles_limit: int = 20
    initial_feed_articles: int = 5
    stats_days_period: int = 7
    admin_email_logs_limit: int = 10
    
    # Request settings
    request_timeout: int = 30  # seconds
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

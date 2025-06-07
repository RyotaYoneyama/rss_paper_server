from pydantic_settings import BaseSettings
from typing import List, Optional
import os
from datetime import timedelta
import secrets


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://rss_user:rss_password@db:5432/rss_db"
    
    # Authentication
    secret_key: str = secrets.token_hex(32)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours
    
    # OpenAI
    openai_api_key: str
    
    # Email
    email_host: str = "smtp.gmail.com"
    email_port: int = 587
    email_user: str
    email_password: str
    email_from: str
    email_to: str
    
    # Scheduling
    rss_fetch_schedule: str = "0 */6 * * *"  # Every 6 hours
    summary_email_schedule: str = "0 7 * * *"  # Every day at 7 AM
    
    # Summary settings
    max_articles_to_summarize: int = 10
    
    # App settings
    app_host: str = "0.0.0.0"
    app_port: int = 3045
    debug: bool = False
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

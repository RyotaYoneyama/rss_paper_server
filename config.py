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
    
    # Email
    email_enabled: bool = True
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

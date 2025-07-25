import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, List
from config import settings
from database import get_db, EmailLog, Article
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EmailSender:
    def __init__(self):
        self.smtp_server = settings.email_host
        self.smtp_port = settings.email_port
        self.username = settings.email_user
        self.password = settings.email_password
        self.from_email = settings.email_from

    def send_email(
        self, to_email: str, subject: str, content: str, content_type: str = "html"
    ) -> bool:
        """Send email with the given content"""
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["From"] = self.from_email
            msg["To"] = to_email
            msg["Subject"] = subject

            # Convert markdown-like content to HTML
            html_content = self.markdown_to_html(content)

            # Add both plain text and HTML versions
            text_part = MIMEText(content, "plain", "utf-8")
            html_part = MIMEText(html_content, "html", "utf-8")

            msg.attach(text_part)
            msg.attach(html_part)

            # Connect to server and send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)

            logger.info(f"Email sent successfully to {to_email}")

            # Log email to database
            self.log_email(to_email, subject, content, "sent")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            self.log_email(to_email, subject, content, "failed")
            return False

    def markdown_to_html(self, markdown_content: str) -> str:
        """Convert simple markdown to HTML"""
        html = markdown_content

        # Convert headers
        html = html.replace("# ", "<h1>").replace("\n# ", "</h1>\n<h1>")
        html = html.replace("## ", "<h2>").replace("\n## ", "</h2>\n<h2>")
        html = html.replace("### ", "<h3>").replace("\n### ", "</h3>\n<h3>")

        # Convert bold text
        import re

        html = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", html)

        # Convert line breaks
        html = html.replace("\n\n", "</p><p>")
        html = html.replace("\n", "<br>")

        # Wrap in paragraphs
        html = f"<p>{html}</p>"

        # Fix headers (close them properly)
        html = re.sub(r"<h1>(.*?)<br>", r"<h1>\1</h1>", html)
        html = re.sub(r"<h2>(.*?)<br>", r"<h2>\1</h2>", html)
        html = re.sub(r"<h3>(.*?)<br>", r"<h3>\1</h3>", html)

        # Convert horizontal rules
        html = html.replace("---", "<hr>")

        # Add basic HTML structure
        html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RSS要約レポート</title>
    <style>
        body {{
            font-family: 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
            border-left: 4px solid #3498db;
            padding-left: 15px;
        }}
        h3 {{
            color: #7f8c8d;
            margin-top: 20px;
        }}
        hr {{
            border: none;
            height: 2px;
            background-color: #ecf0f1;
            margin: 30px 0;
        }}
        strong {{
            color: #2c3e50;
        }}
        a {{
            color: #3498db;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ecf0f1;
            color: #7f8c8d;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        {html}
        <div class="footer">
            <p>このメールは RSS要約システム により自動生成されました。</p>
        </div>
    </div>
</body>
</html>
"""
        return html_template

    def log_email(
        self,
        recipient: str,
        subject: str,
        content: str,
        status: str,
        articles_count: int = 0,
    ):
        """Log email to database"""
        db = next(get_db())
        try:
            email_log = EmailLog(
                recipient=recipient,
                subject=subject,
                content=content[
                    : settings.email_log_content_length
                ],  # Limit content length
                articles_count=articles_count,
                status=status,
            )
            db.add(email_log)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error logging email: {e}")
        finally:
            db.close()

    def send_daily_summary(self) -> bool:
        """Send daily summary email"""

        subject = f"今日の論文要約レポート"
        to_email = settings.email_to
        content = self.create_daily_summary_content()
        success = self.send_email(to_email, subject, content)

        if success:
            # Update log with articles count
            db = next(get_db())
            try:
                latest_log = (
                    db.query(EmailLog)
                    .filter(EmailLog.recipient == to_email, EmailLog.subject == subject)
                    .order_by(EmailLog.sent_at.desc())
                    .first()
                )

                if latest_log:
                    db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating email log: {e}")
            finally:
                db.close()

        return success

    def get_unread_articles(self, limit: int = None) -> List[Article]:
        """Get unread articles for summary email"""
        db = next(get_db())
        try:
            # keywordsはリレーションシップではなくテキストカラムなのでjoinedloadは不要
            query = db.query(Article).filter(Article.is_read == False)

            # Apply order_by before limit
            query = query.order_by(Article.published_date.desc())

            if limit:
                query = query.limit(limit)

            articles = query.all()
            return articles
        finally:
            db.close()

    def create_daily_summary_content(self) -> str:
        """Create daily summary email content"""

        articles = self.get_unread_articles(limit=settings.max_articles_to_summarize)
        if not articles:
            return "新しい記事がありません。"

        logger.info(f"Creating summary for {len(articles)} articles")

        email_content = f"""
# 日次記事要約レポート
生成日時: {datetime.now().strftime("%Y年%m月%d日 %H:%M")}
記事数: {len(articles)}件

---

"""

        for i, article in enumerate(articles, 1):
            # Use existing summary
            summary = article.summary

            email_content += f"""
## {i}. {article.title}

**著者**: {article.author or "不明"}
**URL**: {article.link}
### 要約（落合フォーマット）
{summary}

---

"""

        email_content += f"""
このレポートは自動生成されました。
記事の詳細は各URLをご確認ください。
"""

        return email_content

    def test_email_connection(self) -> bool:
        """Test email connection and configuration"""
        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
            logger.info("Email connection test successful")
            return True
        except Exception as e:
            logger.error(f"Email connection test failed: {e}")
            return False


if __name__ == "__main__":
    sender = EmailSender()

    # Test connection
    if sender.test_email_connection():
        print("Email configuration is working!")

        # Send test email
        test_content = """
# テストメール

これはRSS要約システムのテストメールです。

## 機能確認
- **メール送信**: ✅ 正常
- **HTML変換**: ✅ 正常
- **日本語対応**: ✅ 正常

---

システムが正常に動作しています。
"""
        sender.send_email(
            settings.email_to, "RSS要約システム - テストメール", test_content
        )
    else:
        print("Email configuration needs to be checked.")

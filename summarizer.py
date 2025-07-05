import openai
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session, joinedload
from database import get_db, Article, EmailLog
from config import settings
import logging
from datetime import datetime
import requests
import tempfile
import os
import json
import base64
from io import BytesIO
from PIL import Image
import fitz  # PyMuPDF

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ArticleSummarizer:
    def __init__(self):
        openai.api_key = settings.openai_api_key
        self.client = openai.OpenAI(api_key=settings.openai_api_key)

    def create_ochiai_summary(self, article: Article) -> str:
        """
        Create summary using Ochiai format (落合フォーマット) and parse into sections
        """
        prompt = f"""
以下の記事を落合フォーマットで要約してください。落合フォーマットは以下の6つの観点で構成されます：

1. どんなもの？
2. 先行研究と比べてどこがすごい？
3. 技術や手法のキモはどこ？
4. どうやって有効だと検証した？
5. 議論はある？
6. 次読むべき論文は？

記事情報：
タイトル: {article.title}
URL: {article.link}

内容:
{article.description[:3000]}  # Limit content to avoid token limits

要約は日本語で、各観点について簡潔にまとめてください。技術的な内容の場合は専門用語も適切に使用して。
必ず各セクションを「1. どんなもの？」のように番号付きで明確に区切って。あと書き言葉で書いて。
"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4.1-nano",
                messages=[
                    {"role": "system", "content": "あなたは研究論文や技術記事の要約を専門とするAIアシスタントです。落合フォーマットに従って、正確で簡潔な要約を作成してください。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=1.0
            )
            
            summary = response.choices[0].message.content.strip()
            
            # 各セクションを分割して保存
            self._parse_and_save_sections(article, summary)
            
            return summary
            
        except Exception as e:
            logger.error(f"Error creating summary for article {article.id}: {e}")
            return f"要約の生成に失敗しました: {str(e)}"
            
    def _parse_and_save_sections(self, article: Article, summary: str) -> None:
        """
        Parse the Ochiai format summary into separate sections and save to article
        """
        try:
            # 正規表現パターンを定義
            import re
            
            # 各セクションのパターン
            patterns = {
                'top_summary': r'1\.\s*どんなもの？\s*(.*?)(?=2\.\s*先行研究|$)',
                'comparison': r'2\.\s*先行研究と比べてどこがすごい？\s*(.*?)(?=3\.\s*技術や手法|$)',
                'technique': r'3\.\s*技術や手法のキモはどこ？\s*(.*?)(?=4\.\s*どうやって有効|$)',
                'validation': r'4\.\s*どうやって有効だと検証した？\s*(.*?)(?=5\.\s*議論|$)',
                'discussion': r'5\.\s*議論はある？\s*(.*?)(?=6\.\s*次読むべき|$)',
                'next_papers': r'6\.\s*次読むべき論文は？\s*(.*?)(?=$)'
            }
            
            # 各セクションを抽出して保存
            for field, pattern in patterns.items():
                match = re.search(pattern, summary, re.DOTALL)
                if match:
                    content = match.group(1).strip()
                    setattr(article, field, content)
                else:
                    # マッチしない場合は空文字列を設定
                    setattr(article, field, "")
                    
        except Exception as e:
            logger.error(f"Error parsing summary sections for article {article.id}: {e}")

    def summarize_article(self, article_id: int) -> bool:
        """Summarize a single article and save to database"""
        db = next(get_db())
        try:
            article = db.query(Article).filter(Article.id == article_id).first()
            if not article:
                logger.error(f"Article {article_id} not found")
                return False

            if article.is_summarized:
                logger.info(f"Article {article_id} already summarized")
                return True

            summary = self.create_ochiai_summary(article)
            
            article.summary = summary
            article.is_summarized = True
            db.commit()
            
            logger.info(f"Successfully summarized article {article_id}: {article.title}")
            return True

        except Exception as e:
            db.rollback()
            logger.error(f"Error summarizing article {article_id}: {e}")
            return False
        finally:
            db.close()

    def get_unread_articles(self, limit: int = None) -> List[Article]:
        """Get unread articles for summary email"""
        db = next(get_db())
        try:
            # Use joinedload to eager load the keywords relationship
            query = db.query(Article).options(joinedload(Article.keywords)).filter(Article.is_read == False)
            
            # Apply order_by before limit
            query = query.order_by(Article.published_date.desc())
            
            if limit:
                query = query.limit(limit)
            
            articles = query.all()
            return articles
        finally:
            db.close()

    def create_daily_summary_email(self, articles: List[Article]) -> str:
        """Create daily summary email content"""
        if not articles:
            return "今日は新しい記事がありません。"

        email_content = f"""
# 日次記事要約レポート
生成日時: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}
記事数: {len(articles)}件

---

"""

        for i, article in enumerate(articles, 1):
            # Use existing summary
            summary = article.summary

            email_content += f"""
## {i}. {article.title}

**著者**: {article.author or '不明'}
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

    def summarize_unsummarized_articles(self) -> int:
        """Summarize all articles that don't have summaries yet"""
        db = next(get_db())
        try:
            # Get all unsummarized articles
            articles = db.query(Article).filter(Article.is_summarized == False).all()
            
            if not articles:
                logger.info("No unsummarized articles found")
                return 0

            summarized_count = 0
            for article in articles:
                try:
                    summary = self.create_ochiai_summary(article)
                    article.summary = summary
                    article.is_summarized = True
                    summarized_count += 1
                    logger.info(f"Created summary for article {article.id}: {article.title}")
                except Exception as e:
                    logger.error(f"Error summarizing article {article.id}: {e}")
                    continue

            db.commit()
            logger.info(f"Successfully summarized {summarized_count} articles")
            return summarized_count

        except Exception as e:
            db.rollback()
            logger.error(f"Error in summarize_unsummarized_articles: {e}")
            return 0
        finally:
            db.close()

    def extract_images_from_pdf(self, pdf_url: str, max_images: int = 2) -> List[Dict[str, Any]]:
        """
        PDFから画像を抽出する
        
        Args:
            pdf_url: PDFのURL
            max_images: 抽出する最大画像数（デフォルト: 2）
            
        Returns:
            抽出した画像のリスト（Base64エンコードされた画像データを含む）
        """
        try:
            logger.info(f"PDFから画像を抽出しています: {pdf_url}")
            
            # PDFをダウンロード
            response = requests.get(pdf_url, stream=True)
            response.raise_for_status()
            
            # 一時ファイルにPDFを保存
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                temp_file_path = temp_file.name
                for chunk in response.iter_content(chunk_size=8192):
                    temp_file.write(chunk)
            
            # 抽出した画像を保存するリスト
            extracted_images = []
            
            try:
                # PyMuPDFを使用してPDFから画像を抽出
                pdf_document = fitz.open(temp_file_path)
                
                image_count = 0
                for page_num in range(len(pdf_document)):
                    if image_count >= max_images:
                        break
                        
                    page = pdf_document.load_page(page_num)
                    image_list = page.get_images(full=True)
                    
                    for img_index, img in enumerate(image_list):
                        if image_count >= max_images:
                            break
                            
                        try:
                            xref = img[0]
                            base_image = pdf_document.extract_image(xref)
                            image_bytes = base_image["image"]
                            
                            # 画像のメタデータを取得
                            image_ext = base_image["ext"]
                            width = base_image.get("width", 0)
                            height = base_image.get("height", 0)
                            
                            # 小さすぎる画像はスキップ（アイコンなど）
                            if width < 100 or height < 100:
                                continue
                                
                            # 画像をPILで開いてサイズを確認
                            image = Image.open(BytesIO(image_bytes))
                            
                            # Base64エンコード
                            buffered = BytesIO()
                            image.save(buffered, format="PNG")
                            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                            
                            # 画像情報を保存
                            extracted_images.append({
                                "data": img_base64,
                                "mime_type": f"image/{image_ext}",
                                "width": width,
                                "height": height,
                                "page": page_num + 1,
                                "index": img_index
                            })
                            
                            image_count += 1
                            logger.info(f"画像を抽出しました: ページ {page_num+1}, インデックス {img_index}")
                            
                        except Exception as e:
                            logger.error(f"画像の抽出中にエラーが発生しました: {e}")
                            continue
                
                pdf_document.close()
                
            except Exception as e:
                logger.error(f"PDFの処理中にエラーが発生しました: {e}")
            
            finally:
                # 一時ファイルを削除
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.error(f"一時ファイルの削除中にエラーが発生しました: {e}")
            
            logger.info(f"{len(extracted_images)}個の画像を抽出しました")
            return extracted_images
            
        except Exception as e:
            logger.error(f"PDFからの画像抽出中にエラーが発生しました: {e}")
            return []
    
    def process_article_images(self, article_id: int) -> bool:
        """
        記事のPDFから画像を抽出して保存する
        
        Args:
            article_id: 記事ID
            
        Returns:
            処理が成功したかどうか
        """
        db = next(get_db())
        try:
            article = db.query(Article).filter(Article.id == article_id).first()
            if not article:
                logger.error(f"記事が見つかりません: {article_id}")
                return False
                
            # PDFリンクがない場合は処理をスキップ
            if not article.pdf_link:
                logger.info(f"PDFリンクがありません: {article_id}")
                return False
                
            # 既に画像が抽出されている場合はスキップ
            if article.image_urls:
                logger.info(f"既に画像が抽出されています: {article_id}")
                return True
                
            # PDFから画像を抽出
            images = self.extract_images_from_pdf(article.pdf_link)
            if not images:
                logger.info(f"画像が見つかりませんでした: {article_id}")
                return False
                
            # 画像URLをJSON形式で保存
            article.image_urls = json.dumps(images)
            db.commit()
            
            logger.info(f"記事 {article_id} の画像を保存しました: {len(images)}個")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"記事の画像処理中にエラーが発生しました: {article_id}, {e}")
            return False
        finally:
            db.close()
    
    def summarize_unread_articles(self, max_articles: int = None) -> str:
        """Summarize unread articles and return email content"""
        max_articles = max_articles or settings.max_articles_to_summarize
        
        articles = self.get_unread_articles(limit=max_articles)
        if not articles:
            logger.info("No unread articles to summarize")
            return "新しい記事がありません。"

        logger.info(f"Creating summary for {len(articles)} articles")
        email_content = self.create_daily_summary_email(articles)
        
        # Mark articles as read
        db = next(get_db())
        try:
            for article in articles:
                db_article = db.query(Article).filter(Article.id == article.id).first()
                if db_article:
                    db_article.is_read = True

            db.commit()
            logger.info(f"Marked {len(articles)} articles as read")
        except Exception as e:
            db.rollback()
            logger.error(f"Error marking articles as read: {e}")
        finally:
            db.close()

        return email_content


if __name__ == "__main__":
    summarizer = ArticleSummarizer()
    content = summarizer.summarize_unread_articles()
    print(content)

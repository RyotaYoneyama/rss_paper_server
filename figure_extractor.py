#!/usr/bin/env python3

import sys, os, json, tempfile, shutil, math, logging
import base64
from io import BytesIO
from pathlib import Path
from typing import List, Dict, Any
import requests
from pdf2image import convert_from_path
import layoutparser as lp
from PIL import Image
import pytesseract
from database import get_db, Article, EmailLog

# ロガーの設定
logger = logging.getLogger(__name__)



class FigureExtractor:
    # ---------- 設定 ----------
    MODEL_NAME = "lp://efficientdet/PubLayNet"    # EfficientDet‑Lite backbone
    DPI = 200                                      # 画質と速度のバランス
    PADDING_X = 20                                   # 図の切り出し余白
    PADDING_Y = 30                                   # 図の切り出し余白
    # ---------------------------
    def __init__(self):
        self.model = self.load_model()
        pass

    def load_model(self):
        print("[INFO] Loading layout model ...")
        return lp.AutoLayoutModel(
            self.MODEL_NAME,
        )

    def detect_layout(self, model, pil_img):
        layout = model.detect(pil_img)
        # figure と text系だけ抽出
        figures = [b for b in layout if b.type == "Figure"]
        texts   = [b for b in layout if b.type in ("Text", "Title")]
        return figures, texts

    def find_caption_for(self, fig, text_blocks):
        """fig の下側にあり、センターが近い最短距離テキストをキャプションとみなす"""
        cx_fig = (fig.block.x_1 + fig.block.x_2) / 2
        candidates = [
            t for t in text_blocks
            if t.block.y_1 >= fig.block.y_2 and                      # 下側
               abs(((t.block.x_1 + t.block.x_2)/2) - cx_fig) < 0.3*fig.block.width
        ]
        if not candidates:
            return None
        caption = min(candidates, key=lambda t: t.block.y_1 - fig.block.y_2)
        return caption

    def expand_box(self, coords, pad_x, pad_y, img_w, img_h):
        x1, y1, x2, y2 = coords
        return (
            max(0, x1 - pad_x),
            max(0, y1 - pad_y),
            min(img_w, x2 + pad_x),
            min(img_h, y2 + pad_y),
        )

    def vconcat(self, fig_crop: Image.Image,
                cap_crop: Image.Image,
                pad_px: int = 8,
                bg_color: str = "white") -> Image.Image:
        """
        2 枚の画像を縦方向に連結して 1 枚の Image を返す。
          - pad_px   : 図とキャプションの間の余白（px）
          - bg_color : 余白を塗る色（"white" なら JPEG/PNG どちらでも可）
        """

        # 幅が違う場合は図に合わせてキャプションを resize（可逆にしたいならコメントアウト可）
        if cap_crop.width != fig_crop.width:
            ratio = fig_crop.width / cap_crop.width
            new_h = int(cap_crop.height * ratio)
            cap_crop = cap_crop.resize((fig_crop.width, new_h), Image.LANCZOS)

        # 新しいキャンバスを作る
        total_w = fig_crop.width
        total_h = fig_crop.height + pad_px + cap_crop.height
        canvas = Image.new("RGB", (total_w, total_h), bg_color)

        # 貼り付け
        canvas.paste(fig_crop, (0, 0))
        canvas.paste(cap_crop, (0, fig_crop.height + pad_px))

        return canvas


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
            

    def extract_images_from_pdf(self, pdf_url: str, max_images: int = 2) -> List[Dict[str, Any]]:
        """
        PDFから画像を抽出する
        
        Args:
            pdf_url: PDFのURL
            max_images: 抽出する最大画像数（デフォルト: 2）
            
        Returns:
            抽出した画像のリスト（Base64エンコードされた画像データを含む）
        """

        # 一時ファイルパスの初期化
        temp_file_path = None
        
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

            with tempfile.TemporaryDirectory() as tmp:
                logger.info("[INFO] Converting PDF pages to images ...")
                imgs = convert_from_path(temp_file_path, dpi=self.DPI, output_folder=tmp, fmt="png")

                for page_idx, img in enumerate(imgs, 1):
                    figures, texts = self.detect_layout(self.model, img)
                    page_prefix = f"{page_idx:03d}"
                    for i, fig in enumerate(figures, 1):
                        # 図を切り出し保存
                        img_w, img_h = img.size
                        left, upper, right, lower = self.expand_box(fig.block.coordinates, self.PADDING_X, self.PADDING_Y, img_w, img_h )
                        fig_crop = img.crop((left, upper, right, lower))

                        # キャプション
                        cap_block = self.find_caption_for(fig, texts)
                        
                        # 画像を処理
                        if cap_block:
                            # キャプションがある場合は図とキャプションを連結
                            left, upper, right, lower = self.expand_box(cap_block.block.coordinates, self.PADDING_X, self.PADDING_Y, img_w, img_h )
                            cap_crop = img.crop((left, upper, right, lower))
                            processed_img = self.vconcat(fig_crop, cap_crop, pad_px=8, bg_color="white")
                        else:
                            # キャプションがない場合は図だけを使用
                            processed_img = fig_crop
                        
                        # 画像をBase64エンコード
                        buffered = BytesIO()
                        processed_img.save(buffered, format="PNG")
                        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                        
                        # 画像情報を保存
                        extracted_images.append({
                            "data": img_base64,
                            "mime_type": "image/png",
                            "width": processed_img.width,
                            "height": processed_img.height,
                            "page": page_idx,
                            "index": i
                        })

                        if len(extracted_images) >= max_images:
                            break

                    if len(extracted_images) >= max_images:
                        logger.info(f"最大画像数に達しました: {max_images}")
                        break

        except Exception as e:
            logger.error(f"PDFの処理中にエラーが発生しました: {e}")
        
        finally:
            # 一時ファイルを削除
            if temp_file_path:
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.error(f"一時ファイルの削除中にエラーが発生しました: {e}")
        
        logger.info(f"{len(extracted_images)}個の画像を抽出しました")
        return extracted_images

import re
from typing import List, Dict, Any, Optional, Tuple, Union
import logging

logger = logging.getLogger(__name__)

class FilterParser:
    """
    論理演算（OR、AND）とグループ化（カッコ）をサポートするフィルター構文パーサー
    
    サポートする構文:
    - 単純なキーワード: "keyword"
    - OR演算: "keyword1 OR keyword2"
    - AND演算: "keyword1 AND keyword2"
    - グループ化: "(keyword1 OR keyword2) AND keyword3"
    
    大文字小文字は区別しません。
    """
    
    def __init__(self):
        self.tokens = []
        self.current_token_index = 0
        self.current_token = None
    
    def tokenize(self, filter_expression: str) -> List[str]:
        """
        フィルター式をトークンに分割する
        
        Args:
            filter_expression: フィルター式
            
        Returns:
            トークンのリスト
        """
        # 空白を正規化
        expression = filter_expression.strip()
        
        # カッコの前後にスペースを追加
        expression = re.sub(r'\(', ' ( ', expression)
        expression = re.sub(r'\)', ' ) ', expression)
        
        # 連続する空白を1つにまとめる
        expression = re.sub(r'\s+', ' ', expression)
        
        # トークンに分割
        if expression:
            tokens = expression.split(' ')
            # 空のトークンを削除
            tokens = [token for token in tokens if token]
            return tokens
        return []
    
    def parse(self, filter_expression: str) -> Any:
        """
        フィルター式を解析して構文木を構築する
        
        Args:
            filter_expression: フィルター式
            
        Returns:
            構文木のルートノード
        """
        # フィルター式が空の場合はNoneを返す
        if not filter_expression or filter_expression.strip() == '':
            return None
        
        # フィルター式をトークンに分割
        self.tokens = self.tokenize(filter_expression)
        if not self.tokens:
            return None
        
        # 解析を開始
        self.current_token_index = 0
        self.current_token = self.tokens[0]
        
        # 式を解析
        return self.parse_expression()
    
    def get_next_token(self):
        """次のトークンに進む"""
        self.current_token_index += 1
        if self.current_token_index < len(self.tokens):
            self.current_token = self.tokens[self.current_token_index]
        else:
            self.current_token = None
    
    def parse_expression(self) -> Dict[str, Any]:
        """
        式を解析する
        
        文法:
        expression = term { OR term }
        term = factor { AND factor }
        factor = KEYWORD | "(" expression ")"
        """
        left = self.parse_term()
        
        while self.current_token and self.current_token.upper() == 'OR':
            self.get_next_token()  # 'OR'をスキップ
            right = self.parse_term()
            left = {'type': 'OR', 'left': left, 'right': right}
        
        return left
    
    def parse_term(self) -> Dict[str, Any]:
        """項を解析する"""
        left = self.parse_factor()
        
        while self.current_token and self.current_token.upper() == 'AND':
            self.get_next_token()  # 'AND'をスキップ
            right = self.parse_factor()
            left = {'type': 'AND', 'left': left, 'right': right}
        
        return left
    
    def parse_factor(self) -> Dict[str, Any]:
        """因子を解析する"""
        if not self.current_token:
            raise SyntaxError("予期しないトークンの終わり")
        
        # カッコで囲まれた式
        if self.current_token == '(':
            self.get_next_token()  # '('をスキップ
            expression = self.parse_expression()
            
            if not self.current_token or self.current_token != ')':
                raise SyntaxError("閉じカッコがありません")
            
            self.get_next_token()  # ')'をスキップ
            return expression
        
        # キーワード
        if self.current_token.upper() not in ['AND', 'OR', '(', ')']:
            keyword = self.current_token
            self.get_next_token()
            return {'type': 'KEYWORD', 'value': keyword}
        
        raise SyntaxError(f"予期しないトークン: {self.current_token}")
    
    def evaluate(self, ast: Dict[str, Any], text: str) -> bool:
        """
        構文木を評価して、テキストがフィルター条件にマッチするかどうかを判定する
        
        Args:
            ast: 構文木
            text: 評価対象のテキスト
            
        Returns:
            テキストがフィルター条件にマッチする場合はTrue、そうでない場合はFalse
        """
        if not ast:
            return False
        
        # テキストを小文字に変換（大文字小文字を区別しない）
        text_lower = text.lower()
        
        # ノードのタイプに応じて評価
        node_type = ast.get('type')
        
        if node_type == 'KEYWORD':
            keyword = ast.get('value', '').lower()
            return keyword in text_lower
        
        elif node_type == 'AND':
            left = self.evaluate(ast.get('left', {}), text)
            right = self.evaluate(ast.get('right', {}), text)
            return left and right
        
        elif node_type == 'OR':
            left = self.evaluate(ast.get('left', {}), text)
            right = self.evaluate(ast.get('right', {}), text)
            return left or right
        
        return False
    
    def get_matching_keywords(self, ast: Dict[str, Any], text: str) -> List[str]:
        """
        構文木を評価して、テキストにマッチするキーワードのリストを取得する
        
        Args:
            ast: 構文木
            text: 評価対象のテキスト
            
        Returns:
            マッチしたキーワードのリスト
        """
        if not ast:
            return []
        
        # テキストを小文字に変換（大文字小文字を区別しない）
        text_lower = text.lower()
        
        # ノードのタイプに応じて評価
        node_type = ast.get('type')
        
        if node_type == 'KEYWORD':
            keyword = ast.get('value', '')
            keyword_lower = keyword.lower()
            if keyword_lower in text_lower:
                return [keyword]
            return []
        
        elif node_type == 'AND':
            left_matches = self.get_matching_keywords(ast.get('left', {}), text)
            right_matches = self.get_matching_keywords(ast.get('right', {}), text)
            # ANDの場合は両方のキーワードがマッチする必要がある
            if left_matches and right_matches:
                return left_matches + right_matches
            return []
        
        elif node_type == 'OR':
            left_matches = self.get_matching_keywords(ast.get('left', {}), text)
            right_matches = self.get_matching_keywords(ast.get('right', {}), text)
            # ORの場合はいずれかのキーワードがマッチすればよい
            return left_matches + right_matches
        
        return []
    
    def parse_and_evaluate(self, filter_expression: str, text: str) -> Tuple[bool, List[str]]:
        """
        フィルター式を解析して評価し、テキストがフィルター条件にマッチするかどうかと
        マッチしたキーワードのリストを返す
        
        Args:
            filter_expression: フィルター式
            text: 評価対象のテキスト
            
        Returns:
            (マッチするかどうか, マッチしたキーワードのリスト)
        """
        try:
            # フィルター式を解析
            ast = self.parse(filter_expression)
            if not ast:
                return False, []
            
            # 評価
            matches = self.evaluate(ast, text)
            matching_keywords = self.get_matching_keywords(ast, text)
            
            return matches, matching_keywords
        except Exception as e:
            logger.error(f"フィルター式の解析中にエラーが発生しました: {e}")
            # エラーが発生した場合は、単純なカンマ区切りのキーワードとして扱う
            keywords = [kw.strip() for kw in filter_expression.split(',') if kw.strip()]
            matching_keywords = []
            for keyword in keywords:
                if keyword.lower() in text.lower():
                    matching_keywords.append(keyword)
            
            return len(matching_keywords) > 0, matching_keywords


# 使用例
if __name__ == "__main__":
    parser = FilterParser()
    
    # 単純なキーワード
    logger.info(parser.parse_and_evaluate("python", "This is a Python tutorial"))  # True, ['python']
    
    # OR演算
    logger.info(parser.parse_and_evaluate("python OR javascript", "This is a Python tutorial"))  # True, ['python']
    logger.info(parser.parse_and_evaluate("python OR javascript", "This is a JavaScript tutorial"))  # True, ['javascript']
    
    # AND演算
    logger.info(parser.parse_and_evaluate("python AND tutorial", "This is a Python tutorial"))  # True, ['python', 'tutorial']
    logger.info(parser.parse_and_evaluate("python AND javascript", "This is a Python tutorial"))  # False, []
    
    # グループ化
    logger.info(parser.parse_and_evaluate("(python OR javascript) AND tutorial", "This is a Python tutorial"))  # True, ['python', 'tutorial']
    logger.info(parser.parse_and_evaluate("(python OR javascript) AND tutorial", "This is a JavaScript tutorial"))  # True, ['javascript', 'tutorial']
    logger.info(parser.parse_and_evaluate("(python OR javascript) AND (tutorial OR guide)", "This is a JavaScript guide"))  # True, ['javascript', 'guide']

# main.py
"""
libclang C Parser API - 個別エンドポイント版
C言語コードの解析結果を目的別に取得できるAPI
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import clang.cindex
import tempfile
import os

# Flaskアプリ初期化
app = Flask(__name__)
CORS(app)  # フロントエンドからのアクセスを許可

# libclangライブラリの場所を指定（Railway環境用）
clang.cindex.conf.set_library_file('/usr/lib/x86_64-linux-gnu/libclang-1.so')

# ================================
# ユーティリティ関数
# ================================

def create_temp_file(code):
    """
    C言語コードを一時ファイルに保存
    libclangはファイル単位でパースするため
    """
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False)
    temp_file.write(code)
    temp_file.close()
    return temp_file.name

def parse_with_libclang(code):
    """
    libclangでC言語コードをパース
    戻り値: translation_unit (libclangの解析結果)
    """
    # libclangインデックス作成
    index = clang.cindex.Index.create()
    
    # 一時ファイル作成
    temp_path = create_temp_file(code)
    
    try:
        # libclangでファイルをパース
        translation_unit = index.parse(temp_path)
        return translation_unit, temp_path
    except Exception as e:
        # エラーが発生した場合、一時ファイルを削除
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise e

def cleanup_temp_file(temp_path):
    """一時ファイルを削除"""
    if os.path.exists(temp_path):
        os.unlink(temp_path)

def validate_request():
    """
    リクエストの妥当性をチェック
    戻り値: (code, error_response)
    """
    if not request.is_json:
        return None, jsonify({"success": False, "error": "Content-Type must be application/json"}), 400
    
    data = request.get_json()
    if not data or 'code' not in data:
        return None, jsonify({"success": False, "error": "Missing 'code' field"}), 400
    
    code = data['code']
    if not isinstance(code, str):
        return None, jsonify({"success": False, "error": "'code' must be string"}), 400
    
    return code, None, None

# ================================
# 個別エンドポイント
# ================================

@app.route('/api/tokens', methods=['POST'])
def get_tokens():
    """
    字句解析結果（トークン）を取得
    
    Request: {"code": "int main() { return 0; }"}
    Response: {"success": true, "tokens": [...]}
    """
    try:
        # リクエスト検証
        code, error_response, status_code = validate_request()
        if error_response:
            return error_response, status_code
        
        # libclangでパース
        translation_unit, temp_path = parse_with_libclang(code)
        
        try:
            # トークン情報を抽出
            tokens = []
            for token in translation_unit.get_tokens(extent=translation_unit.cursor.extent):
                tokens.append({
                    'kind': token.kind.name,          # トークンの種類 (KEYWORD, IDENTIFIER等)
                    'spelling': token.spelling,       # トークンの文字列
                    'location': {
                        'line': token.location.line,
                        'column': token.location.column
                    }
                })
            
            return jsonify({
                "success": True,
                "tokens": tokens
            })
            
        finally:
            cleanup_temp_file(temp_path)
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/ast', methods=['POST'])
def get_ast():
    """
    構文解析結果（AST: 抽象構文木）を取得
    
    Request: {"code": "int main() { return 0; }"}
    Response: {"success": true, "ast": {...}}
    """
    try:
        # リクエスト検証
        code, error_response, status_code = validate_request()
        if error_response:
            return error_response, status_code
        
        # libclangでパース
        translation_unit, temp_path = parse_with_libclang(code)
        
        try:
            # AST情報を抽出
            ast = cursor_to_dict(translation_unit.cursor)
            
            return jsonify({
                "success": True,
                "ast": ast
            })
            
        finally:
            cleanup_temp_file(temp_path)
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/diagnostics', methods=['POST'])
def get_diagnostics():
    """
    診断情報（エラー・警告）を取得
    
    Request: {"code": "int x = ;"}  # 構文エラーのあるコード
    Response: {"success": true, "diagnostics": [...]}
    """
    try:
        # リクエスト検証
        code, error_response, status_code = validate_request()
        if error_response:
            return error_response, status_code
        
        # libclangでパース
        translation_unit, temp_path = parse_with_libclang(code)
        
        try:
            # 診断情報を抽出
            diagnostics = []
            for diag in translation_unit.diagnostics:
                diagnostics.append({
                    'severity': diag.severity,                    # エラーレベル
                    'spelling': diag.spelling,                    # エラーメッセージ
                    'location': {
                        'line': diag.location.line,
                        'column': diag.location.column,
                        'file': diag.location.file.name if diag.location.file else None
                    },
                    'category_name': diag.category_name,          # エラーカテゴリ
                    'option': diag.option                         # 関連するコンパイラオプション
                })
            
            return jsonify({
                "success": True,
                "diagnostics": diagnostics
            })
            
        finally:
            cleanup_temp_file(temp_path)
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/includes', methods=['POST'])
def get_includes():
    """
    インクルード情報を取得
    
    Request: {"code": "#include <stdio.h>\nint main() { return 0; }"}
    Response: {"success": true, "includes": [...]}
    """
    try:
        # リクエスト検証
        code, error_response, status_code = validate_request()
        if error_response:
            return error_response, status_code
        
        # libclangでパース
        translation_unit, temp_path = parse_with_libclang(code)
        
        try:
            # インクルード情報を抽出
            includes = []
            for include in translation_unit.get_includes():
                includes.append({
                    'source': include.source.name if include.source else None,     # インクルード元ファイル
                    'include': include.include.name if include.include else None,  # インクルードされるファイル
                    'location': {
                        'line': include.location.line,
                        'column': include.location.column
                    },
                    'depth': include.depth                        # インクルードの深度
                })
            
            return jsonify({
                "success": True,
                "includes": includes
            })
            
        finally:
            cleanup_temp_file(temp_path)
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/all', methods=['POST'])
def get_all():
    """
    全ての解析結果をまとめて取得
    
    Request: {"code": "int main() { return 0; }"}
    Response: {"success": true, "tokens": [...], "ast": {...}, "diagnostics": [...], "includes": [...]}
    """
    try:
        # リクエスト検証
        code, error_response, status_code = validate_request()
        if error_response:
            return error_response, status_code
        
        # libclangでパース（一度だけ実行）
        translation_unit, temp_path = parse_with_libclang(code)
        
        try:
            # 全ての情報を一度に抽出
            result = {
                "success": True,
                "tokens": [],
                "ast": {},
                "diagnostics": [],
                "includes": []
            }
            
            # 1. トークン情報
            for token in translation_unit.get_tokens(extent=translation_unit.cursor.extent):
                result["tokens"].append({
                    'kind': token.kind.name,
                    'spelling': token.spelling,
                    'location': {
                        'line': token.location.line,
                        'column': token.location.column
                    }
                })
            
            # 2. AST情報
            result["ast"] = cursor_to_dict(translation_unit.cursor)
            
            # 3. 診断情報
            for diag in translation_unit.diagnostics:
                result["diagnostics"].append({
                    'severity': diag.severity,
                    'spelling': diag.spelling,
                    'location': {
                        'line': diag.location.line,
                        'column': diag.location.column,
                        'file': diag.location.file.name if diag.location.file else None
                    },
                    'category_name': diag.category_name,
                    'option': diag.option
                })
            
            # 4. インクルード情報
            for include in translation_unit.get_includes():
                result["includes"].append({
                    'source': include.source.name if include.source else None,
                    'include': include.include.name if include.include else None,
                    'location': {
                        'line': include.location.line,
                        'column': include.location.column
                    },
                    'depth': include.depth
                })
            
            return jsonify(result)
            
        finally:
            cleanup_temp_file(temp_path)
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ================================
# AST変換ヘルパー関数
# ================================

def cursor_to_dict(cursor):
    """
    libclangのCursorオブジェクトを辞書形式に変換
    
    Args:
        cursor: libclangのCursorオブジェクト
    
    Returns:
        dict: AST情報を含む辞書
    """
    result = {
        'kind': cursor.kind.name,                    # カーソルの種類 (FUNCTION_DECL, VAR_DECL等)
        'spelling': cursor.spelling,                 # 識別子名
        'type': cursor.type.spelling,                # 型情報
        'location': {
            'line': cursor.location.line,
            'column': cursor.location.column,
            'file': cursor.location.file.name if cursor.location.file else None
        }
    }
    
    # 子要素を再帰的に処理
    children = []
    for child in cursor.get_children():
        children.append(cursor_to_dict(child))
    
    if children:
        result['children'] = children
    
    return result

# ================================
# API情報エンドポイント
# ================================

@app.route('/', methods=['GET'])
def api_info():
    """API の使用方法を表示"""
    return jsonify({
        "name": "libclang C Parser API",
        "version": "1.0.0",
        "description": "C言語コードの解析結果を目的別に取得できるAPI",
        "endpoints": {
            "POST /api/tokens": "字句解析結果（トークン）を取得",
            "POST /api/ast": "構文解析結果（AST）を取得",
            "POST /api/diagnostics": "診断情報（エラー・警告）を取得", 
            "POST /api/includes": "インクルード情報を取得",
            "POST /api/all": "全ての解析結果をまとめて取得"
        },
        "request_format": {
            "code": "string (required) - C言語のソースコード"
        },
        "example": {
            "url": "/api/tokens",
            "method": "POST",
            "body": {"code": "int main() { return 0; }"}
        }
    })

# ================================
# サーバー起動
# ================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print("🚀 libclang C Parser API")
    print(f"   Port: {port}")
    print("📍 Available endpoints:")
    print("   GET  / - API information")
    print("   POST /api/tokens - Get lexical analysis results")
    print("   POST /api/ast - Get syntax analysis results")  
    print("   POST /api/diagnostics - Get error/warning diagnostics")
    print("   POST /api/includes - Get include information")
    print("   POST /api/all - Get all analysis results")
    
    app.run(host='0.0.0.0', port=port)

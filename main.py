# main.py
"""
Enhanced libclang C Parser API - リッチなAST解析版
C言語コードの解析結果をより詳細に取得できるAPI
ループ終了位置の正確な検出、関数メタデータ、変数ライフサイクル等を含む
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import clang.cindex
from clang.cindex import CursorKind, TypeKind, TokenKind
import tempfile
import os
import re
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, asdict

# Flaskアプリ初期化
app = Flask(__name__)
CORS(app)  # フロントエンドからのアクセスを許可

# libclangライブラリの場所を自動検出
import subprocess
import os

def find_libclang():
    """libclangライブラリのパスを自動検出"""
    possible_paths = [
        '/usr/lib/x86_64-linux-gnu/libclang-1.so',
        '/usr/lib/libclang.so',
        '/usr/lib/libclang-16.so',
        '/usr/lib/x86_64-linux-gnu/libclang.so',
        '/usr/lib/x86_64-linux-gnu/libclang-16.so',
        '/usr/local/lib/libclang.so',
    ]
    
    # 各パスを試す
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    # ldconfigで検索
    try:
        result = subprocess.run(['ldconfig', '-p'], capture_output=True, text=True)
        for line in result.stdout.split('\n'):
            if 'libclang' in line:
                # libclang.so.1 => /usr/lib/x86_64-linux-gnu/libclang.so.1 の形式から抽出
                parts = line.split(' => ')
                if len(parts) > 1:
                    return parts[1].strip()
    except:
        pass
    
    # 最後の手段: find コマンド
    try:
        result = subprocess.run(['find', '/usr', '-name', 'libclang*.so*', '-type', 'f'], 
                              capture_output=True, text=True, timeout=10)
        lines = result.stdout.strip().split('\n')
        if lines and lines[0]:
            return lines[0]
    except:
        pass
    
    return None

# libclangライブラリを自動検出して設定
libclang_path = find_libclang()
if libclang_path:
    print(f"🔍 Found libclang at: {libclang_path}")
    clang.cindex.conf.set_library_file(libclang_path)
else:
    print("⚠️  libclang not found, trying default configuration")

# ================================
# データクラス定義（リッチな解析結果用）
# ================================

@dataclass
class LoopInfo:
    """ループ構造の詳細情報"""
    start_line: int
    end_line: int
    body_start_line: Optional[int] = None
    body_end_line: Optional[int] = None
    condition_line: Optional[int] = None
    increment_line: Optional[int] = None
    nested_level: int = 0
    has_break: bool = False
    has_continue: bool = False
    estimated_complexity: str = "unknown"

@dataclass
class FunctionInfo:
    """関数の詳細メタデータ"""
    complexity_score: int = 0
    max_nesting_depth: int = 0
    parameter_count: int = 0
    local_variable_count: int = 0
    calls_functions: List[str] = None
    return_points: List[Dict[str, Any]] = None
    memory_operations: Dict[str, List[Dict]] = None
    
    def __post_init__(self):
        if self.calls_functions is None:
            self.calls_functions = []
        if self.return_points is None:
            self.return_points = []
        if self.memory_operations is None:
            self.memory_operations = {"allocations": [], "deallocations": []}

@dataclass
class VariableInfo:
    """変数の生存期間・スコープ情報"""
    scope_start_line: int
    scope_end_line: int
    usage_locations: List[int] = None
    modification_locations: List[int] = None
    is_initialized: bool = False
    initialization_line: Optional[int] = None
    data_flow: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.usage_locations is None:
            self.usage_locations = []
        if self.modification_locations is None:
            self.modification_locations = []
        if self.data_flow is None:
            self.data_flow = []

@dataclass
class ControlFlowInfo:
    """制御フローの詳細情報"""
    condition_complexity: str = "simple"
    has_else: bool = False
    else_if_chain_length: int = 0
    branches: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.branches is None:
            self.branches = []

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
# リッチな解析関数群
# ================================

def get_precise_extent_info(cursor):
    """
    カーソルの正確な範囲情報を取得
    特にループ構造の開始と終了位置を詳細に分析
    """
    extent = cursor.extent
    start_location = extent.start
    end_location = extent.end
    
    extent_info = {
        "start_line": start_location.line,
        "start_column": start_location.column,
        "end_line": end_location.line,
        "end_column": end_location.column,
        "start_offset": start_location.offset if hasattr(start_location, 'offset') else None,
        "end_offset": end_location.offset if hasattr(end_location, 'offset') else None
    }
    
    return extent_info

def analyze_loop_structure(cursor, nesting_level=0):
    """
    ループ構造の詳細分析
    FOR文、WHILE文、DO-WHILE文の正確な終了位置を特定
    """
    if cursor.kind not in [CursorKind.FOR_STMT, CursorKind.WHILE_STMT, CursorKind.DO_STMT]:
        return None
    
    extent_info = get_precise_extent_info(cursor)
    
    loop_info = LoopInfo(
        start_line=extent_info["start_line"],
        end_line=extent_info["end_line"],
        nested_level=nesting_level
    )
    
    # 子要素を分析してより詳細な情報を取得
    children = list(cursor.get_children())
    
    if cursor.kind == CursorKind.FOR_STMT:
        # FOR文の構造: [初期化], [条件], [増分], [本体]
        if len(children) >= 4:
            # 条件部分の行番号
            condition_cursor = children[1] if len(children) > 1 else None
            if condition_cursor:
                loop_info.condition_line = condition_cursor.location.line
            
            # 増分部分の行番号
            increment_cursor = children[2] if len(children) > 2 else None
            if increment_cursor:
                loop_info.increment_line = increment_cursor.location.line
            
            # 本体部分の範囲
            body_cursor = children[3] if len(children) > 3 else None
            if body_cursor:
                body_extent = get_precise_extent_info(body_cursor)
                loop_info.body_start_line = body_extent["start_line"]
                loop_info.body_end_line = body_extent["end_line"]
    
    elif cursor.kind == CursorKind.WHILE_STMT:
        # WHILE文の構造: [条件], [本体]
        if len(children) >= 2:
            # 条件部分
            condition_cursor = children[0]
            loop_info.condition_line = condition_cursor.location.line
            
            # 本体部分
            body_cursor = children[1]
            body_extent = get_precise_extent_info(body_cursor)
            loop_info.body_start_line = body_extent["start_line"]
            loop_info.body_end_line = body_extent["end_line"]
    
    # ループ内のbreak/continue文を検出
    break_continue_finder = BreakContinueFinder()
    break_continue_finder.visit_cursor(cursor)
    loop_info.has_break = break_continue_finder.has_break
    loop_info.has_continue = break_continue_finder.has_continue
    
    return loop_info

class BreakContinueFinder:
    """ループ内のbreak/continue文を検出するクラス"""
    
    def __init__(self):
        self.has_break = False
        self.has_continue = False
    
    def visit_cursor(self, cursor):
        if cursor.kind == CursorKind.BREAK_STMT:
            self.has_break = True
        elif cursor.kind == CursorKind.CONTINUE_STMT:
            self.has_continue = True
        
        # 子要素を再帰的に探索（ただし、ネストしたループは除外）
        for child in cursor.get_children():
            if child.kind not in [CursorKind.FOR_STMT, CursorKind.WHILE_STMT, CursorKind.DO_STMT]:
                self.visit_cursor(child)

def analyze_function_complexity(cursor):
    """
    関数の複雑度を分析
    """
    if cursor.kind != CursorKind.FUNCTION_DECL:
        return None
    
    complexity_analyzer = FunctionComplexityAnalyzer()
    complexity_analyzer.visit_cursor(cursor)
    
    function_info = FunctionInfo(
        complexity_score=complexity_analyzer.complexity_score,
        max_nesting_depth=complexity_analyzer.max_nesting_depth,
        parameter_count=len([c for c in cursor.get_children() if c.kind == CursorKind.PARM_DECL]),
        local_variable_count=complexity_analyzer.local_var_count,
        calls_functions=complexity_analyzer.function_calls,
        return_points=complexity_analyzer.return_points,
        memory_operations=complexity_analyzer.memory_ops
    )
    
    return function_info

class FunctionComplexityAnalyzer:
    """関数の複雑度を分析するクラス"""
    
    def __init__(self):
        self.complexity_score = 1  # 基本複雑度
        self.current_nesting_depth = 0
        self.max_nesting_depth = 0
        self.local_var_count = 0
        self.function_calls = []
        self.return_points = []
        self.memory_ops = {"allocations": [], "deallocations": []}
    
    def visit_cursor(self, cursor, depth=0):
        # ネストレベルを更新
        if cursor.kind in [CursorKind.IF_STMT, CursorKind.FOR_STMT, CursorKind.WHILE_STMT, 
                          CursorKind.SWITCH_STMT, CursorKind.DO_STMT]:
            depth += 1
            self.complexity_score += 1
            self.max_nesting_depth = max(self.max_nesting_depth, depth)
        
        # ローカル変数をカウント
        if cursor.kind == CursorKind.VAR_DECL:
            self.local_var_count += 1
        
        # 関数呼び出しを記録
        if cursor.kind == CursorKind.CALL_EXPR:
            func_name = cursor.spelling or "unknown"
            if func_name not in self.function_calls:
                self.function_calls.append(func_name)
            
            # メモリ操作を特別に記録
            if func_name in ['malloc', 'calloc', 'realloc']:
                self.memory_ops["allocations"].append({
                    "line": cursor.location.line,
                    "function": func_name
                })
            elif func_name == 'free':
                self.memory_ops["deallocations"].append({
                    "line": cursor.location.line,
                    "function": func_name
                })
        
        # return文を記録
        if cursor.kind == CursorKind.RETURN_STMT:
            self.return_points.append({
                "line": cursor.location.line,
                "type": "normal"
            })
        
        # 子要素を再帰的に処理
        for child in cursor.get_children():
            self.visit_cursor(child, depth)

def analyze_control_flow(cursor):
    """
    制御フローの詳細分析
    """
    if cursor.kind != CursorKind.IF_STMT:
        return None
    
    control_flow = ControlFlowInfo()
    
    # 子要素を分析
    children = list(cursor.get_children())
    branch_count = 0
    
    for i, child in enumerate(children):
        if child.kind == CursorKind.COMPOUND_STMT:
            branch_count += 1
            branch_info = {
                "type": "if_true" if branch_count == 1 else f"else_branch_{branch_count}",
                "start_line": child.extent.start.line,
                "end_line": child.extent.end.line
            }
            control_flow.branches.append(branch_info)
        elif child.kind == CursorKind.IF_STMT:
            # else if の場合
            control_flow.else_if_chain_length += 1
    
    control_flow.has_else = branch_count > 1
    
    return control_flow

# ================================
# 拡張されたエンドポイント
# ================================

@app.route('/api/enhanced-ast', methods=['POST'])
def get_enhanced_ast():
    """
    リッチなAST解析結果を取得
    ループ終了位置、関数複雑度、制御フロー等の詳細情報を含む
    
    Request: {"code": "int main() { for(int i=0; i<10; i++) { printf(\"%d\", i); } return 0; }"}
    Response: {"success": true, "enhanced_ast": {...}}
    """
    try:
        # リクエスト検証
        code, error_response, status_code = validate_request()
        if error_response:
            return error_response, status_code
        
        # libclangでパース
        translation_unit, temp_path = parse_with_libclang(code)
        
        try:
            # 拡張AST情報を抽出
            enhanced_ast = enhanced_cursor_to_dict(translation_unit.cursor)
            
            return jsonify({
                "success": True,
                "enhanced_ast": enhanced_ast,
                "analysis_metadata": {
                    "total_functions": count_functions(translation_unit.cursor),
                    "total_loops": count_loops(translation_unit.cursor),
                    "total_variables": count_variables(translation_unit.cursor),
                    "max_nesting_depth": get_max_nesting_depth(translation_unit.cursor)
                }
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
            # 従来のAST情報を抽出（下位互換性のため）
            ast = cursor_to_dict(translation_unit.cursor)
            
            return jsonify({
                "success": True,
                "ast": ast
            })
            
        finally:
            cleanup_temp_file(temp_path)
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ================================
# 拡張AST変換関数
# ================================

def enhanced_cursor_to_dict(cursor, nesting_level=0):
    """
    libclangのCursorオブジェクトをリッチな辞書形式に変換
    ループ終了位置、関数メタデータ、変数情報等を含む
    """
    # 基本情報
    result = {
        'kind': cursor.kind.name,
        'spelling': cursor.spelling,
        'type': cursor.type.spelling,
        'location': {
            'line': cursor.location.line,
            'column': cursor.location.column,
            'file': cursor.location.file.name if cursor.location.file else None
        }
    }
    
    # 正確な範囲情報を追加
    extent_info = get_precise_extent_info(cursor)
    result['extent'] = extent_info
    
    # トークン情報を追加
    tokens = []
    if cursor.extent.start.line != 0 or cursor.extent.end.line != 0:
        try:
            for token in cursor.get_tokens():
                tokens.append({
                    'kind': token.kind.name,
                    'spelling': token.spelling,
                    'location': {
                        'line': token.location.line,
                        'column': token.location.column
                    }
                })
        except Exception as e:
            app.logger.debug(f"Failed to get tokens for cursor {cursor.kind.name}: {e}")
    
    if tokens:
        result['tokens'] = tokens
    
    # ループ構造の詳細分析
    if cursor.kind in [CursorKind.FOR_STMT, CursorKind.WHILE_STMT, CursorKind.DO_STMT]:
        loop_info = analyze_loop_structure(cursor, nesting_level)
        if loop_info:
            result['loop_info'] = asdict(loop_info)
    
    # 関数の詳細分析
    if cursor.kind == CursorKind.FUNCTION_DECL:
        result['result_type_spelling'] = cursor.result_type.spelling
        function_info = analyze_function_complexity(cursor)
        if function_info:
            result['function_info'] = asdict(function_info)
    
    # 制御フローの分析
    if cursor.kind == CursorKind.IF_STMT:
        control_flow_info = analyze_control_flow(cursor)
        if control_flow_info:
            result['control_flow_info'] = asdict(control_flow_info)
    
    # 変数情報の分析
    if cursor.kind == CursorKind.VAR_DECL:
        var_info = analyze_variable_info(cursor)
        if var_info:
            result['variable_info'] = asdict(var_info)
    
    # 子要素を再帰的に処理
    children = []
    child_nesting = nesting_level
    if cursor.kind in [CursorKind.IF_STMT, CursorKind.FOR_STMT, CursorKind.WHILE_STMT]:
        child_nesting += 1
    
    for child in cursor.get_children():
        children.append(enhanced_cursor_to_dict(child, child_nesting))
    
    if children:
        result['children'] = children
    
    return result

def analyze_variable_info(cursor):
    """
    変数の詳細情報を分析
    """
    if cursor.kind != CursorKind.VAR_DECL:
        return None
    
    # 基本的な変数情報
    var_info = VariableInfo(
        scope_start_line=cursor.location.line,
        scope_end_line=cursor.location.line,  # 実際のスコープ終了は親スコープから判断
        is_initialized=has_initializer(cursor),
        initialization_line=cursor.location.line if has_initializer(cursor) else None
    )
    
    return var_info

def has_initializer(cursor):
    """
    変数が初期化されているかチェック
    """
    for child in cursor.get_children():
        if child.kind != CursorKind.TYPE_REF:  # 型参照以外があれば初期化子
            return True
    return False

# ================================
# 統計関数群
# ================================

def count_functions(cursor):
    """関数の総数をカウント"""
    count = 0
    if cursor.kind == CursorKind.FUNCTION_DECL:
        count += 1
    
    for child in cursor.get_children():
        count += count_functions(child)
    
    return count

def count_loops(cursor):
    """ループの総数をカウント"""
    count = 0
    if cursor.kind in [CursorKind.FOR_STMT, CursorKind.WHILE_STMT, CursorKind.DO_STMT]:
        count += 1
    
    for child in cursor.get_children():
        count += count_loops(child)
    
    return count

def count_variables(cursor):
    """変数の総数をカウント"""
    count = 0
    if cursor.kind == CursorKind.VAR_DECL:
        count += 1
    
    for child in cursor.get_children():
        count += count_variables(child)
    
    return count

def get_max_nesting_depth(cursor, current_depth=0):
    """最大ネストレベルを取得"""
    max_depth = current_depth
    
    if cursor.kind in [CursorKind.IF_STMT, CursorKind.FOR_STMT, CursorKind.WHILE_STMT, 
                      CursorKind.SWITCH_STMT, CursorKind.DO_STMT]:
        current_depth += 1
    
    for child in cursor.get_children():
        child_max = get_max_nesting_depth(child, current_depth)
        max_depth = max(max_depth, child_max)
    
    return max_depth

# ================================
# 従来のエンドポイント（下位互換性のため）
# ================================

def cursor_to_dict(cursor):
    """
    従来のAST変換関数（下位互換性のため保持）
    """
    result = {
        'kind': cursor.kind.name,
        'spelling': cursor.spelling,
        'type': cursor.type.spelling,
        'location': {
            'line': cursor.location.line,
            'column': cursor.location.column,
            'file': cursor.location.file.name if cursor.location.file else None
        }
    }
    
    # extent情報を追加（ループ終了位置検出のため）
    extent_info = get_precise_extent_info(cursor)
    result['extent'] = extent_info
    
    # トークン情報を追加
    tokens = []
    if cursor.extent.start.line != 0 or cursor.extent.end.line != 0:
        try:
            for token in cursor.get_tokens():
                tokens.append({
                    'kind': token.kind.name,
                    'spelling': token.spelling,
                    'location': {
                        'line': token.location.line,
                        'column': token.location.column
                    }
                })
        except Exception as e:
            app.logger.debug(f"Failed to get tokens for cursor {cursor.kind.name}: {e}")
    
    if tokens:
        result['tokens'] = tokens

    # FUNCTION_DECLの戻り値型を追加
    if cursor.kind == CursorKind.FUNCTION_DECL:
        result['result_type_spelling'] = cursor.result_type.spelling

    # 子要素を再帰的に処理
    children = []
    for child in cursor.get_children():
        children.append(cursor_to_dict(child))
    
    if children:
        result['children'] = children
    
    return result

# ================================
# その他の既存エンドポイント
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
                    'kind': token.kind.name,
                    'spelling': token.spelling,
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
        code, error_response, status_code

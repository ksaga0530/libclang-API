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
import subprocess

# Flaskアプリ初期化
app = Flask(__name__)
CORS(app)  # フロントエンドからのアクセスを許可

# ================================
# データクラス定義（簡略版：dataclassを使わずに辞書で）
# ================================

def create_loop_info(start_line, end_line, **kwargs):
    """ループ情報を作成"""
    return {
        "start_line": start_line,
        "end_line": end_line,
        "body_start_line": kwargs.get("body_start_line"),
        "body_end_line": kwargs.get("body_end_line"),
        "condition_line": kwargs.get("condition_line"),
        "increment_line": kwargs.get("increment_line"),
        "nested_level": kwargs.get("nested_level", 0),
        "has_break": kwargs.get("has_break", False),
        "has_continue": kwargs.get("has_continue", False),
        "estimated_complexity": kwargs.get("estimated_complexity", "unknown")
    }

def create_function_info(**kwargs):
    """関数情報を作成"""
    return {
        "complexity_score": kwargs.get("complexity_score", 0),
        "max_nesting_depth": kwargs.get("max_nesting_depth", 0),
        "parameter_count": kwargs.get("parameter_count", 0),
        "local_variable_count": kwargs.get("local_variable_count", 0),
        "calls_functions": kwargs.get("calls_functions", []),
        "return_points": kwargs.get("return_points", []),
        "memory_operations": kwargs.get("memory_operations", {"allocations": [], "deallocations": []})
    }

def create_variable_info(scope_start_line, scope_end_line, **kwargs):
    """変数情報を作成"""
    return {
        "scope_start_line": scope_start_line,
        "scope_end_line": scope_end_line,
        "usage_locations": kwargs.get("usage_locations", []),
        "modification_locations": kwargs.get("modification_locations", []),
        "is_initialized": kwargs.get("is_initialized", False),
        "initialization_line": kwargs.get("initialization_line"),
        "data_flow": kwargs.get("data_flow", [])
    }

def create_control_flow_info(**kwargs):
    """制御フロー情報を作成"""
    return {
        "condition_complexity": kwargs.get("condition_complexity", "simple"),
        "has_else": kwargs.get("has_else", False),
        "else_if_chain_length": kwargs.get("else_if_chain_length", 0),
        "branches": kwargs.get("branches", [])
    }

# ================================
# libclang自動検出
# ================================

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
# ユーティリティ関数
# ================================

def create_temp_file(code):
    """C言語コードを一時ファイルに保存"""
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False)
    temp_file.write(code)
    temp_file.close()
    return temp_file.name

def parse_with_libclang(code):
    """libclangでC言語コードをパース"""
    index = clang.cindex.Index.create()
    temp_path = create_temp_file(code)
    
    try:
        translation_unit = index.parse(temp_path)
        return translation_unit, temp_path
    except Exception as e:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise e

def cleanup_temp_file(temp_path):
    """一時ファイルを削除"""
    if os.path.exists(temp_path):
        os.unlink(temp_path)

def validate_request():
    """リクエストの妥当性をチェック"""
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
    """カーソルの正確な範囲情報を取得"""
    extent = cursor.extent
    start_location = extent.start
    end_location = extent.end
    
    return {
        "start_line": start_location.line,
        "start_column": start_location.column,
        "end_line": end_location.line,
        "end_column": end_location.column
    }

def analyze_loop_structure(cursor, nesting_level=0):
    """ループ構造の詳細分析"""
    if cursor.kind not in [CursorKind.FOR_STMT, CursorKind.WHILE_STMT, CursorKind.DO_STMT]:
        return None
    
    extent_info = get_precise_extent_info(cursor)
    
    loop_info = create_loop_info(
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
                loop_info["condition_line"] = condition_cursor.location.line
            
            # 増分部分の行番号
            increment_cursor = children[2] if len(children) > 2 else None
            if increment_cursor:
                loop_info["increment_line"] = increment_cursor.location.line
            
            # 本体部分の範囲
            body_cursor = children[3] if len(children) > 3 else None
            if body_cursor:
                body_extent = get_precise_extent_info(body_cursor)
                loop_info["body_start_line"] = body_extent["start_line"]
                loop_info["body_end_line"] = body_extent["end_line"]
    
    elif cursor.kind == CursorKind.WHILE_STMT:
        # WHILE文の構造: [条件], [本体]
        if len(children) >= 2:
            # 条件部分
            condition_cursor = children[0]
            loop_info["condition_line"] = condition_cursor.location.line
            
            # 本体部分
            body_cursor = children[1]
            body_extent = get_precise_extent_info(body_cursor)
            loop_info["body_start_line"] = body_extent["start_line"]
            loop_info["body_end_line"] = body_extent["end_line"]
    
    # ループ内のbreak/continue文を検出
    break_continue_finder = BreakContinueFinder()
    break_continue_finder.visit_cursor(cursor)
    loop_info["has_break"] = break_continue_finder.has_break
    loop_info["has_continue"] = break_continue_finder.has_continue
    
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
    """関数の複雑度を分析"""
    if cursor.kind != CursorKind.FUNCTION_DECL:
        return None
    
    complexity_analyzer = FunctionComplexityAnalyzer()
    complexity_analyzer.visit_cursor(cursor)
    
    return create_function_info(
        complexity_score=complexity_analyzer.complexity_score,
        max_nesting_depth=complexity_analyzer.max_nesting_depth,
        parameter_count=len([c for c in cursor.get_children() if c.kind == CursorKind.PARM_DECL]),
        local_variable_count=complexity_analyzer.local_var_count,
        calls_functions=complexity_analyzer.function_calls,
        return_points=complexity_analyzer.return_points,
        memory_operations=complexity_analyzer.memory_ops
    )

class FunctionComplexityAnalyzer:
    """関数の複雑度を分析するクラス"""
    
    def __init__(self):
        self.complexity_score = 1
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
    """制御フローの詳細分析"""
    if cursor.kind != CursorKind.IF_STMT:
        return None
    
    control_flow = create_control_flow_info()
    
    # 子要素を分析
    children = list(cursor.get_children())
    branch_count = 0
    branches = []
    
    for i, child in enumerate(children):
        if child.kind == CursorKind.COMPOUND_STMT:
            branch_count += 1
            branch_info = {
                "type": "if_true" if branch_count == 1 else f"else_branch_{branch_count}",
                "start_line": child.extent.start.line,
                "end_line": child.extent.end.line
            }
            branches.append(branch_info)
        elif child.kind == CursorKind.IF_STMT:
            # else if の場合
            control_flow["else_if_chain_length"] += 1
    
    control_flow["branches"] = branches
    control_flow["has_else"] = branch_count > 1
    
    return control_flow

def analyze_variable_info(cursor):
    """変数の詳細情報を分析"""
    if cursor.kind != CursorKind.VAR_DECL:
        return None
    
    return create_variable_info(
        scope_start_line=cursor.location.line,
        scope_end_line=cursor.location.line,
        is_initialized=has_initializer(cursor),
        initialization_line=cursor.location.line if has_initializer(cursor) else None
    )

def has_initializer(cursor):
    """変数が初期化されているかチェック"""
    for child in cursor.get_children():
        if child.kind != CursorKind.TYPE_REF:
            return True
    return False

# ================================
# AST変換関数
# ================================

def enhanced_cursor_to_dict(cursor, nesting_level=0):
    """libclangのCursorオブジェクトをリッチな辞書形式に変換"""
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
            result['loop_info'] = loop_info
    
    # 関数の詳細分析
    if cursor.kind == CursorKind.FUNCTION_DECL:
        result['result_type_spelling'] = cursor.result_type.spelling
        function_info = analyze_function_complexity(cursor)
        if function_info:
            result['function_info'] = function_info
    
    # 制御フローの分析
    if cursor.kind == CursorKind.IF_STMT:
        control_flow_info = analyze_control_flow(cursor)
        if control_flow_info:
            result['control_flow_info'] = control_flow_info
    
    # 変数情報の分析
    if cursor.kind == CursorKind.VAR_DECL:
        var_info = analyze_variable_info(cursor)
        if var_info:
            result['variable_info'] = var_info
    
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

def cursor_to_dict(cursor):
    """従来のAST変換関数（下位互換性のため保持）"""
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

def calculate_overall_complexity(cursor):
    """プログラム全体の複雑度を計算"""
    complexity = 0
    
    def visit_cursor(cursor):
        nonlocal complexity
        if cursor.kind in [CursorKind.IF_STMT, CursorKind.FOR_STMT, CursorKind.WHILE_STMT, 
                          CursorKind.SWITCH_STMT, CursorKind.DO_STMT]:
            complexity += 1
        
        for child in cursor.get_children():
            visit_cursor(child)
    
    visit_cursor(cursor)
    return complexity

# ================================
# エンドポイント定義
# ================================

@app.route('/api/enhanced-ast', methods=['POST'])
def get_enhanced_ast():
    """リッチなAST解析結果を取得"""
    try:
        code, error_response, status_code = validate_request()
        if error_response:
            return error_response, status_code
        
        translation_unit, temp_path = parse_with_libclang(code)
        
        try:
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
    """構文解析結果（AST: 抽象構文木）を取得"""
    try:
        code, error_response, status_code = validate_request()
        if error_response:
            return error_response, status_code
        
        translation_unit, temp_path = parse_with_libclang(code)
        
        try:
            ast = cursor_to_dict(translation_unit.cursor)
            
            return jsonify({
                "success": True,
                "ast": ast
            })
            
        finally:
            cleanup_temp_file(temp_path)
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/tokens', methods=['POST'])
def get_tokens():
    """字句解析結果（トークン）を取得"""
    try:
        code, error_response, status_code = validate_request()
        if error_response:
            return error_response, status_code
        
        translation_unit, temp_path = parse_with_libclang(code)
        
        try:
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
    """診断情報（エラー・警告）を取得"""
    try:
        code, error_response, status_code = validate_request()
        if error_response:
            return error_response, status_code
        
        translation_unit, temp_path = parse_with_libclang(code)
        
        try:
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
            # 4. 診断情報
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
            
            # 5. インクルード情報
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
            
            # 6. 解析サマリー情報
            result["analysis_summary"] = {
                "total_functions": count_functions(translation_unit.cursor),
                "total_loops": count_loops(translation_unit.cursor),
                "total_variables": count_variables(translation_unit.cursor),
                "max_nesting_depth": get_max_nesting_depth(translation_unit.cursor),
                "total_tokens": len(result["tokens"]),
                "has_errors": len(result["diagnostics"]) > 0,
                "complexity_score": calculate_overall_complexity(translation_unit.cursor)
            }
            
            return jsonify(result)
            
        finally:
            cleanup_temp_file(temp_path)
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/loop-analysis', methods=['POST'])
def get_loop_analysis():
    """ループ構造専用の詳細分析"""
    try:
        code, error_response, status_code = validate_request()
        if error_response:
            return error_response, status_code
        
        translation_unit, temp_path = parse_with_libclang(code)
        
        try:
            loops = []
            loop_finder = LoopFinder()
            loop_finder.visit_cursor(translation_unit.cursor)
            
            for loop_cursor in loop_finder.loops:
                loop_info = analyze_loop_structure(loop_cursor)
                if loop_info:
                    loop_data = {
                        "cursor_info": {
                            "kind": loop_cursor.kind.name,
                            "location": {
                                "line": loop_cursor.location.line,
                                "column": loop_cursor.location.column
                            }
                        },
                        "loop_details": loop_info,
                        "source_text": get_source_text(loop_cursor, code)
                    }
                    loops.append(loop_data)
            
            return jsonify({
                "success": True,
                "loops": loops,
                "loop_count": len(loops),
                "analysis_metadata": {
                    "nested_loops": count_nested_loops(translation_unit.cursor),
                    "infinite_loop_warnings": detect_potential_infinite_loops(loops)
                }
            })
            
        finally:
            cleanup_temp_file(temp_path)
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ================================
# 追加のヘルパークラス・関数
# ================================

class LoopFinder:
    """ループを検出するクラス"""
    
    def __init__(self):
        self.loops = []
    
    def visit_cursor(self, cursor):
        if cursor.kind in [CursorKind.FOR_STMT, CursorKind.WHILE_STMT, CursorKind.DO_STMT]:
            self.loops.append(cursor)
        
        for child in cursor.get_children():
            self.visit_cursor(child)

def get_source_text(cursor, original_code):
    """カーソルに対応するソーステキストを抽出"""
    try:
        lines = original_code.split('\n')
        start_line = cursor.extent.start.line - 1
        end_line = cursor.extent.end.line - 1
        
        if start_line == end_line:
            # 単一行の場合
            if start_line < len(lines):
                line = lines[start_line]
                start_col = cursor.extent.start.column - 1
                end_col = cursor.extent.end.column - 1
                return line[start_col:end_col]
        else:
            # 複数行の場合
            if start_line < len(lines) and end_line < len(lines):
                result_lines = []
                for i in range(start_line, end_line + 1):
                    if i == start_line:
                        # 最初の行
                        start_col = cursor.extent.start.column - 1
                        result_lines.append(lines[i][start_col:])
                    elif i == end_line:
                        # 最後の行
                        end_col = cursor.extent.end.column - 1
                        result_lines.append(lines[i][:end_col])
                    else:
                        # 中間の行
                        result_lines.append(lines[i])
                return '\n'.join(result_lines)
    except Exception as e:
        app.logger.debug(f"Failed to extract source text: {e}")
    
    return "unable to extract"

def count_nested_loops(cursor, in_loop=False):
    """ネストしたループの数をカウント"""
    nested_count = 0
    current_is_loop = cursor.kind in [CursorKind.FOR_STMT, CursorKind.WHILE_STMT, CursorKind.DO_STMT]
    
    if current_is_loop and in_loop:
        nested_count += 1
    
    for child in cursor.get_children():
        nested_count += count_nested_loops(child, in_loop or current_is_loop)
    
    return nested_count

def detect_potential_infinite_loops(loops):
    """無限ループの可能性を検出"""
    warnings = []
    
    for loop_data in loops:
        loop_info = loop_data.get("loop_details", {})
        
        # 簡易的な無限ループ検出
        if (not loop_info.get("has_break", False) and 
            not loop_info.get("has_continue", False) and
            loop_data["cursor_info"]["kind"] == "WHILE_STMT"):
            warnings.append({
                "line": loop_data["cursor_info"]["location"]["line"],
                "type": "potential_infinite_loop",
                "message": "WHILE loop without break statement detected"
            })
    
    return warnings

# ================================
# API情報エンドポイント
# ================================

@app.route('/', methods=['GET'])
def api_info():
    """API の使用方法を表示"""
    return jsonify({
        "name": "Enhanced libclang C Parser API",
        "version": "2.0.0",
        "description": "C言語コードのリッチな解析結果を取得できるAPI（ループ終了位置、関数複雑度等を含む）",
        "endpoints": {
            "POST /api/tokens": "字句解析結果（トークン）を取得",
            "POST /api/ast": "構文解析結果（従来のAST）を取得",
            "POST /api/enhanced-ast": "リッチなAST解析結果を取得（推奨）",
            "POST /api/loop-analysis": "ループ構造専用の詳細分析",
            "POST /api/diagnostics": "診断情報（エラー・警告）を取得", 
            "POST /api/includes": "インクルード情報を取得",
            "POST /api/all": "全ての解析結果をまとめて取得（拡張版）"
        },
        "new_features": {
            "loop_end_detection": "ループの正確な終了位置を検出",
            "function_complexity": "関数の複雑度分析",
            "control_flow_analysis": "制御フローの詳細分析",
            "variable_lifecycle": "変数のライフサイクル追跡",
            "memory_operation_tracking": "メモリ操作の追跡",
            "nesting_depth_analysis": "ネストレベルの分析"
        },
        "request_format": {
            "code": "string (required) - C言語のソースコード"
        },
        "enhanced_example": {
            "url": "/api/enhanced-ast",
            "method": "POST",
            "body": {"code": "int main() { for(int i=0; i<10; i++) { printf(\"%d\", i); } return 0; }"},
            "response_includes": [
                "precise loop end positions",
                "function complexity metrics", 
                "variable scope information",
                "control flow analysis"
            ]
        }
    })

# ================================
# サーバー起動
# ================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print("🚀 Enhanced libclang C Parser API v2.0")
    print(f"   Port: {port}")
    print("📍 Available endpoints:")
    print("   GET  / - API information")
    print("   POST /api/tokens - Get lexical analysis results")
    print("   POST /api/ast - Get syntax analysis results (legacy)")  
    print("   POST /api/enhanced-ast - Get rich AST analysis results (NEW)")
    print("   POST /api/loop-analysis - Get detailed loop structure analysis (NEW)")
    print("   POST /api/diagnostics - Get error/warning diagnostics")
    print("   POST /api/includes - Get include information")
    print("   POST /api/all - Get all analysis results (enhanced)")
    print("\n🎯 New Features:")
    print("   ✅ Precise loop end position detection")
    print("   ✅ Function complexity analysis")
    print("   ✅ Control flow detailed analysis")
    print("   ✅ Variable lifecycle tracking")
    print("   ✅ Memory operation tracking")
    print("   ✅ Nesting depth analysis")
    
    # 本番環境ではgunicornが推奨だが、開発時はFlask開発サーバーを使用
    if os.environ.get('FLASK_ENV') == 'development':
        app.run(host='0.0.0.0', port=port, debug=True)
    else:
        # 本番環境: gunicornで起動される（Dockerfileで指定）
        # 直接実行時はFlask開発サーバーを使用
        app.run(host='0.0.0.0', port=port, debug=False)ag.category_name,
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
    """インクルード情報を取得"""
    try:
        code, error_response, status_code = validate_request()
        if error_response:
            return error_response, status_code
        
        translation_unit, temp_path = parse_with_libclang(code)
        
        try:
            includes = []
            for include in translation_unit.get_includes():
                includes.append({
                    'source': include.source.name if include.source else None,
                    'include': include.include.name if include.include else None,
                    'location': {
                        'line': include.location.line,
                        'column': include.location.column
                    },
                    'depth': include.depth
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
    """全ての解析結果をまとめて取得（拡張版）"""
    try:
        code, error_response, status_code = validate_request()
        if error_response:
            return error_response, status_code
        
        translation_unit, temp_path = parse_with_libclang(code)
        
        try:
            result = {
                "success": True,
                "tokens": [],
                "ast": {},
                "enhanced_ast": {},
                "diagnostics": [],
                "includes": [],
                "analysis_summary": {}
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
            
            # 2. 従来のAST情報（下位互換性）
            result["ast"] = cursor_to_dict(translation_unit.cursor)
            
            # 3. 拡張AST情報
            result["enhanced_ast"] = enhanced_cursor_to_dict(translation_unit.cursor)
            
            # 4. 診断情報
            for diag in translation_unit.diagnostics:
                result["diagnostics"].append({
                    'severity': diag.severity,
                    'spelling': diag.spelling,
                    'location': {
                        'line': diag.location.line,
                        'column': diag.location.column,
                        'file': diag.location.file.name if diag.location.file else None
                    },
                    'category_name': di

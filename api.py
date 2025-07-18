# api.py
from flask import Flask, request, jsonify
import clang.cindex
import tempfile
import os

app = Flask(__name__)

@app.route('/api/parse', methods=['POST'])
def parse_c():
    try:
        code = request.get_json()['code']
        
        # libclang実行
        index = clang.cindex.Index.create()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False) as f:
            f.write(code)
            temp_path = f.name
        
        try:
            tu = index.parse(temp_path)
            ast = cursor_to_dict(tu.cursor)
            return jsonify({"success": True, "libclang_output": ast})
        finally:
            os.unlink(temp_path)
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

def cursor_to_dict(cursor):
    return {
        'kind': cursor.kind.name,
        'spelling': cursor.spelling,
        'type': cursor.type.spelling,
        'location': {'line': cursor.location.line, 'column': cursor.location.column},
        'children': [cursor_to_dict(child) for child in cursor.get_children()]
    }

# Railway用の起動設定
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

# 依存関係（コメントで記載）
# pip install Flask==2.3.3 libclang==16.0.6

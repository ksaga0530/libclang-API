#!/usr/bin/env python3
"""
libclang API テストスクリプト - 個別エンドポイント版
各エンドポイントの動作を確認
"""

import requests
import json

# APIのベースURL
BASE_URL = "http://localhost:5000"
# デプロイ後は以下のようなURLに変更
# BASE_URL = "https://your-app.railway.app"

def test_endpoint(endpoint, description, code):
    """
    指定されたエンドポイントをテスト
    
    Args:
        endpoint: テストするエンドポイント (/api/tokens等)
        description: テストの説明
        code: テスト用のC言語コード
    """
    print(f"\n🧪 {description}")
    print(f"   Endpoint: {endpoint}")
    print("-" * 50)
    
    try:
        response = requests.post(
            f"{BASE_URL}{endpoint}",
            headers={"Content-Type": "application/json"},
            json={"code": code}
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ Success")
                
                # 結果の要約を表示
                if 'tokens' in data:
                    print(f"   Tokens: {len(data['tokens'])} items")
                    # 最初の3つのトークンを表示
                    for i, token in enumerate(data['tokens'][:3]):
                        print(f"     {i+1}. {token['kind']}: '{token['spelling']}'")
                
                if 'ast' in data:
                    print(f"   AST Root: {data['ast'].get('kind')}")
                    print(f"   Children: {len(data['ast'].get('children', []))}")
                
                if 'diagnostics' in data:
                    diag_count = len(data['diagnostics'])
                    print(f"   Diagnostics: {diag_count} issues")
                    for diag in data['diagnostics'][:2]:  # 最初の2つのみ表示
                        print(f"     Line {diag['location']['line']}: {diag['spelling']}")
                
                if 'includes' in data:
                    print(f"   Includes: {len(data['includes'])} files")
                    for inc in data['includes']:
                        print(f"     {inc['include']} (line {inc['location']['line']})")
                        
            else:
                print(f"❌ API Error: {data.get('error')}")
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            print(f"   Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection Error: {e}")
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")

def main():
    """メインテスト関数"""
    print("🚀 libclang API Individual Endpoints Test")
    print("=" * 60)
    
    # テストケース
    test_cases = [
        {
            "name": "Simple C code",
            "code": """#include <stdio.h>

int main() {
    int x = 10;
    printf("Hello, World!\\n");
    return 0;
}"""
        },
        {
            "name": "Function with arguments",
            "code": """int add(int a, int b) {
    return a + b;
}

int main() {
    int result = add(5, 3);
    return 0;
}"""
        },
        {
            "name": "Code with syntax error",
            "code": "int x = ;"  # 意図的なエラー
        }
    ]
    
    # 各テストケースについて全エンドポイントをテスト
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'='*60}")
        print(f"Test Case {i}: {test_case['name']}")
        print('='*60)
        print(f"Code:\n{test_case['code']}")
        
        # 各エンドポイントをテスト
        endpoints = [
            ("/api/tokens", "Tokens (字句解析)"),
            ("/api/ast", "AST (構文解析)"), 
            ("/api/diagnostics", "Diagnostics (エラー・警告)"),
            ("/api/includes", "Includes (インクルード情報)"),
            ("/api/all", "All (全情報)")
        ]
        
        for endpoint, description in endpoints:
            test_endpoint(endpoint, description, test_case['code'])
    
    # API情報エンドポイントのテスト
    print(f"\n{'='*60}")
    print("API Information Endpoint Test")
    print('='*60)
    
    try:
        response = requests.get(f"{BASE_URL}/")
        print(f"GET / - Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print("✅ API Info retrieved successfully")
            print(f"   API Name: {data.get('name')}")
            print(f"   Version: {data.get('version')}")
        else:
            print("❌ Failed to get API info")
    except Exception as e:
        print(f"❌ API Info test failed: {e}")
    
    print(f"\n{'='*60}")
    print("🏁 All tests completed!")
    print('='*60)

if __name__ == "__main__":
    main()

# libclang C Parser API

C言語コードの解析結果を目的別に取得できるREST API

## 🚀 Features

- **字句解析**: トークン情報を取得
- **構文解析**: AST（抽象構文木）を取得  
- **診断情報**: エラー・警告を取得
- **インクルード情報**: #include の依存関係を取得
- **個別取得**: 必要な情報だけを効率的に取得可能

## 📍 Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API情報を取得 |
| POST | `/api/tokens` | 字句解析結果（トークン）を取得 |
| POST | `/api/ast` | 構文解析結果（AST）を取得 |
| POST | `/api/diagnostics` | 診断情報（エラー・警告）を取得 |
| POST | `/api/includes` | インクルード情報を取得 |
| POST | `/api/all` | 全ての解析結果をまとめて取得 |

## 📝 Request Format

```json
{
  "code": "int main() { return 0; }"
}
```

## 📋 Response Examples

### Tokens (`/api/tokens`)
```json
{
  "success": true,
  "tokens": [
    {
      "kind": "KEYWORD",
      "spelling": "int",
      "location": {"line": 1, "column": 1}
    },
    {
      "kind": "IDENTIFIER", 
      "spelling": "main",
      "location": {"line": 1, "column": 5}
    }
  ]
}
```

### AST (`/api/ast`)
```json
{
  "success": true,
  "ast": {
    "kind": "TRANSLATION_UNIT",
    "spelling": "tmp.c",
    "type": "",
    "location": {"line": 0, "column": 0, "file": null},
    "children": [...]
  }
}
```

### Diagnostics (`/api/diagnostics`)
```json
{
  "success": true,
  "diagnostics": [
    {
      "severity": 3,
      "spelling": "expected expression",
      "location": {"line": 1, "column": 9, "file": "tmp.c"},
      "category_name": "Parse Issue",
      "option": null
    }
  ]
}
```

## 🛠️ Local Development

### Prerequisites
- Python 3.11+
- libclang

### Setup
```bash
# Clone repository
git clone <repository-url>
cd libclang-api

# Install dependencies
pip install -r requirements.txt

# Run server
python main.py
```

### Testing
```bash
# Run test script
python test_api.py
```

## 🚀 Deployment

### Railway
1. Connect GitHub repository to Railway
2. Railway will automatically detect Python project
3. Set environment variables if needed
4. Deploy automatically

### Docker
```bash
# Build image
docker build -t libclang-api .

# Run container
docker run -p 5000:5000 libclang-api
```

## 🧪 API Testing

### Using curl
```bash
# Test tokens endpoint
curl -X POST http://localhost:5000/api/tokens \
  -H "Content-Type: application/json" \
  -d '{"code": "int x = 10;"}'

# Test AST endpoint  
curl -X POST http://localhost:5000/api/ast \
  -H "Content-Type: application/json" \
  -d '{"code": "int main() { return 0; }"}'
```

### Using Python
```python
import requests

response = requests.post(
    'http://localhost:5000/api/tokens',
    json={'code': 'int main() { return 0; }'}
)

data = response.json()
print(data)
```

## 📚 libclang Information

This API uses libclang (LLVM/Clang Python bindings) for C language parsing:

- **Version**: 16.0.6
- **Backend**: LLVM/Clang compiler infrastructure
- **Standards**: Full C11/C17 support
- **Features**: Complete lexical and syntax analysis

## ⚠️ Error Handling

All endpoints return consistent error format:

```json
{
  "success": false,
  "error": "Error description"
}
```

Common HTTP status codes:
- `200`: Success
- `400`: Bad Request (invalid JSON, missing fields)
- `500`: Internal Server Error (libclang parsing error)

## 📄 License

MIT License - see LICENSE file for details

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

---

Powered by [libclang](https://clang.llvm.org/doxygen/group__CINDEX.html) & [Flask](https://flask.palletsprojects.com/)

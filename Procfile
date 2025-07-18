# Railway用 Procfile
# 本番環境用のWebサーバー起動コマンド

# Gunicorn使用（推奨：本番環境向け）
web: gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 30 main:app

# Flask開発サーバー使用（代替手段）
# web: python main.py

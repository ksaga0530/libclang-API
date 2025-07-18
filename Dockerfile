# Multi-stage Dockerfile for libclang C Parser API
# Railway用の最適化されたDockerfile

FROM python:3.11-slim as base

# 環境変数設定
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# システムパッケージ更新とlibclang関連のインストール
RUN apt-get update && apt-get install -y \
    # libclang関連
    libclang-16-dev \
    clang-16 \
    llvm-16-dev \
    # ビルドツール（必要最小限）
    gcc \
    # クリーンアップ
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 作業ディレクトリ設定
WORKDIR /app

# Python依存関係をまずコピー（キャッシュ効率化）
COPY requirements.txt .

# Python パッケージインストール
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# 非rootユーザー作成（セキュリティ向上）
RUN groupadd -r appuser && useradd -r -g appuser appuser && \
    chown -R appuser:appuser /app
USER appuser

# ポート設定
EXPOSE 5000

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/')" || exit 1

# 本番環境設定
ENV FLASK_ENV=production

# アプリケーション起動（本番用サーバー使用）
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "30", "main:app"]

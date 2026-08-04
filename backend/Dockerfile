FROM python:3.12-slim

WORKDIR /app

# 视频合成 / 时长探测需要系统 FFmpeg；中文字幕需要字体
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-wqy-zenhei \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# 依赖以仓库根目录 pyproject.toml 为准（不再使用 requirements.txt）
COPY pyproject.toml README.md ./
COPY backend/ ./backend/

RUN pip install --no-cache-dir . -i https://pypi.tuna.tsinghua.edu.cn/simple \
    && playwright install --with-deps chromium

WORKDIR /app/backend

EXPOSE 3456

CMD ["python", "app.py"]

FROM python:3.11-slim

WORKDIR /app

# 国内 apt 镜像（否则 deb.debian.org 可能极慢）
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources; \
      sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources; \
    fi; \
    if [ -f /etc/apt/sources.list ]; then \
      sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list; \
      sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list; \
    fi

# 视频合成需要 FFmpeg；中文字幕用文泉驿即可（比 fonts-noto-cjk 小很多）
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

# 依赖以 backend/pyproject.toml 为准
COPY backend/ ./backend/
WORKDIR /app/backend

RUN pip install --no-cache-dir . -i https://pypi.tuna.tsinghua.edu.cn/simple \
    && playwright install --with-deps chromium

EXPOSE 3456

CMD ["python", "app.py"]

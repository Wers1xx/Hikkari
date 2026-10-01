FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    DOCKER=true \
    GIT_PYTHON_REFRESH=quiet

RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    curl \
    ffmpeg \
    gcc \
    git \
    libmagic1 \
    openssh-client \
    && curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared \
    && chmod +x /usr/local/bin/cloudflared \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /data

# Clone Hikkari (or use build context)
ARG HIKKARI_REPO=https://github.com/Wers1xx/Hikkari.git
ARG HIKKARI_REF=master
RUN git clone --depth 1 --branch "${HIKKARI_REF}" "${HIKKARI_REPO}" /data/Hikkari

WORKDIR /data/Hikkari

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "hikkaritl>=1.1.2" || true

VOLUME ["/data/Hikkari/sessions", "/data/Hikkari"]

CMD ["python3", "-m", "hikkari", "--no-tty"]

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        nodejs \
        npm \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libcairo2 \
        libcups2 \
        libdrm2 \
        libgbm1 \
        libnss3 \
        libpango-1.0-0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxkbcommon0 \
        libxrandr2 \
    && rm -rf /var/lib/apt/lists/*

COPY services/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY services/worker/app ./app
COPY studio ./studio
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY packages/renderer/package.json packages/renderer/tsconfig.json ./packages/renderer/
COPY packages/renderer/src ./packages/renderer/src
RUN npm install --prefix /app/packages/renderer
RUN cd /app/packages/renderer && npx --no-install remotion browser ensure

ENV RENDERER_ROOT=/app/packages/renderer

CMD ["celery", "-A", "app.celery_app:celery_app", "worker", "--loglevel=INFO"]

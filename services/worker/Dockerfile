FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg nodejs npm \
    && rm -rf /var/lib/apt/lists/*

COPY services/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY services/worker/app ./app
COPY studio ./studio
COPY packages/renderer/package.json packages/renderer/tsconfig.json ./packages/renderer/
COPY packages/renderer/src ./packages/renderer/src
RUN npm install --prefix /app/packages/renderer

ENV RENDERER_ROOT=/app/packages/renderer

CMD ["celery", "-A", "app.celery_app:celery_app", "worker", "--loglevel=INFO"]

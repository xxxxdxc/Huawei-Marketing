FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM node:22-bookworm-slim AS node
FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY backend/requirements.lock.txt /app/backend/requirements.lock.txt
RUN pip install --no-cache-dir -r backend/requirements.lock.txt
COPY backend/ /app/backend/
COPY --from=frontend /build/frontend/dist /app/frontend/dist
RUN useradd --create-home --uid 1000 app && mkdir -p /app/.local && chown -R app:app /app
ENV PYTHONUNBUFFERED=1 HUAWEI_DATA_DIR=/app/.local
USER app
EXPOSE 7860
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]

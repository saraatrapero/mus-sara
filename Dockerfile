FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY bots ./bots
COPY config ./config
RUN pip install --no-cache-dir ".[web]"
ENV MUSST_DB=/data/musst.sqlite3 PORT=8000
RUN mkdir -p /data
EXPOSE 8000
CMD ["sh", "-c", "uvicorn musst.server.app:app --host 0.0.0.0 --port ${PORT}"]

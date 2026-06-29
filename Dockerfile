FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic/ alembic/
COPY alembic.ini .
COPY app/ app/
COPY entrypoint.sh .

RUN mkdir -p static/avatars

EXPOSE 8000

CMD ["sh", "entrypoint.sh"]
FROM python:3.11-slim

WORKDIR /app

# Установить системные зависимости для asyncpg и криптографии
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# По умолчанию запускать API; для бота переопределить CMD в Railway
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

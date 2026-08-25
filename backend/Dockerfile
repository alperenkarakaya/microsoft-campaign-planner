FROM python:3.11-slim

WORKDIR /app

# Sistem bağımlılıklarını yükle
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Requirements'ı kopyala ve yükle
COPY requirements.txt . 
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama kodunu kopyala
COPY .  .

# Port aç
EXPOSE 8000

# Uygulama çalıştır
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
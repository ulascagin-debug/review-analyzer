FROM mcr.microsoft.com/playwright/python:v1.50.0-jammy

WORKDIR /app

# Python bağımlılıklarını kur
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Proje dosyalarını kopyala
COPY . .

# API Portu
EXPOSE 8001

# Sunucuyu başlat
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8001"]

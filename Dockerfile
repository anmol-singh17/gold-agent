FROM python:3.12-slim

WORKDIR /app

# System deps for Playwright (needed for Kijiji/FB messaging, not scraping)
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
    libgbm1 libasound2 libpangocairo-1.0-0 libpango-1.0-0 \
    libcairo2 libxshmfence1 libglu1-mesa fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright Chromium (for messaging only — scraping now via Apify)
RUN python -m playwright install chromium

COPY . .

RUN mkdir -p sessions

CMD ["python", "agent/main.py"]

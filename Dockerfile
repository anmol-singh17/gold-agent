FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and its Chromium dependencies
RUN pip install playwright && python -m playwright install chromium && python -m playwright install-deps chromium

COPY . .

# Create sessions directory (will be populated via env vars on Railway)
RUN mkdir -p sessions

CMD ["python", "agent/main.py"]

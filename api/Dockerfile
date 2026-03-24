FROM python:3.11-slim-bookworm

WORKDIR /app

# System dependencies for OCR runtimes (Tesseract + PaddleOCR/OpenCV).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-chi-sim \
        fonts-wqy-zenhei \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run the API service by default.
CMD ["sh", "/app/scripts/run_api.sh"]

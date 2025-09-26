FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set Chrome Driver path
ENV CHROME_DRIVER_PATH=/usr/bin/chromedriver
ENV CHROME_BIN=/usr/bin/chromium

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/output /app/temp_uploads /app/logs

# Create non-root user
RUN useradd -m -u 1000 apiuser && \
    chown -R apiuser:apiuser /app

USER apiuser

# Expose port
EXPOSE 5682

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:5682/health || exit 1

# Run the application
# Use fewer workers in development to avoid resource conflicts
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5682", "--workers", "2"]



FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Fix line endings and make start script executable
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh

# Create non-root user
RUN useradd -m -u 1000 fluxvpn && chown -R fluxvpn:fluxvpn /app

# Receipts directory (named volume mount target; owned by fluxvpn so the
# app process can write receipt JPEGs after the volume is mounted).
RUN mkdir -p /data/receipts && chown fluxvpn:fluxvpn /data/receipts

USER fluxvpn

# Expose port (PORT env var can override default)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8080}/health')" || exit 1

# Use start script that handles migrations
CMD ["./start.sh"]

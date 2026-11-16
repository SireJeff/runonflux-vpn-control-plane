FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set PYTHONPATH so bot module can be found
ENV PYTHONPATH=/app

# Create non-root user
RUN useradd -m -u 1000 fluxvpn && chown -R fluxvpn:fluxvpn /app
USER fluxvpn

# Default command - use -m to run as module
CMD ["python", "-m", "bot.main"]

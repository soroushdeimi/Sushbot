FROM python:3.12-slim-bookworm

# Security: Run apt-get update to get latest security patches
WORKDIR /app

# Install system dependencies with security updates
RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create logs directory
RUN mkdir -p logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Run the bot
CMD ["python", "-m", "bot.main"]








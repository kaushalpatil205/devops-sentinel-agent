FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install kubectl
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sentinel/ ./sentinel/

ENV SENTINEL_ENV=production
ENV SENTINEL_PORT=8000
ENV AUTO_REMEDIATE=true
ENV AUTO_ROLLBACK=true

EXPOSE 8000

CMD ["python", "-m", "sentinel.cli.main", "serve", "--host", "0.0.0.0", "--port", "8000"]

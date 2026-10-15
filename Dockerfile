FROM python:3.11-slim

# Install system dependencies: ffmpeg for audio conversion, nodejs for YouTube JS challenges, curl, ca-certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Download precompiled bgutil-pot binary for Proof-of-Origin token generation
RUN curl -L -s -o /usr/local/bin/bgutil-pot "https://github.com/jim60105/bgutil-ytdlp-pot-provider-rs/releases/download/v0.8.1/bgutil-pot-linux-x86_64" \
    && chmod +x /usr/local/bin/bgutil-pot

# Non-root user
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Install Python requirements
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY --chown=user:user . .

# Expose port (Render uses 10000 by default)
EXPOSE 10000

CMD ["sh", "-c", "bgutil-pot server --host 127.0.0.1 --port 4416 & uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000}"]

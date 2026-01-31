FROM python:3.11-slim

WORKDIR /app

# Base deps
# Upgrade packages to fix OS-level CVEs (e.g. libssl3, libc6)
RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    curl \
  && rm -rf /var/lib/apt/lists/*

# Python deps
# Upgrade pip & setuptools to fix CVE-2025-8869 and vendor vulnerabilities (jaraco.context, wheel)
RUN pip install --upgrade pip==25.3 setuptools>=70.0.0 wheel>=0.46.3
COPY services/signal/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY core /app/core
COPY services/signal /app/services/signal
# Ensure python package layout for module execution
RUN mkdir -p /app/services \
  && touch /app/services/__init__.py \
  && touch /app/services/signal/__init__.py

# Run as non-root
RUN useradd -m -u 1000 signaluser \
  && chown -R signaluser:signaluser /app
USER signaluser

# Optional: container-level healthcheck (compose also defines one)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -f http://localhost:8005/health || exit 1

CMD ["python", "-m", "services.signal.service"]

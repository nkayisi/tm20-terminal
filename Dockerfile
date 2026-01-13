# ============================================
# Stage 1: Builder (compilation des dépendances)
# ============================================
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Installation des dépendances de build
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Installation des dépendances Python dans un virtualenv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ============================================
# Stage 2: Runtime (image finale légère)
# ============================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Installation uniquement des dépendances runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copie du virtualenv depuis le builder
COPY --from=builder /opt/venv /opt/venv

# Copie du code source
COPY . .

# Collecte des fichiers statiques (build time)
RUN python manage.py collectstatic --noinput || true

# Création d'un utilisateur non-root pour la sécurité
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# Script d'entrypoint pour exécuter les migrations avant le démarrage
RUN echo '#!/bin/bash\n\
set -e\n\
echo "🔄 Running database migrations..."\n\
python manage.py migrate --noinput\n\
echo "✅ Migrations completed"\n\
echo "🚀 Starting Gunicorn..."\n\
exec "$@"' > /app/docker-entrypoint.sh && \
    chmod +x /app/docker-entrypoint.sh && \
    chown appuser:appuser /app/docker-entrypoint.sh

USER appuser

ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Port unique pour HTTP + WebSocket
EXPOSE 7788

# Healthcheck pour Render
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7788/admin/login/?next=/admin/').read()" || exit 1

# Commande de démarrage: Gunicorn + UvicornWorker (ASGI)
# Architecture unifiée: HTTP + WebSocket sur port 7788
CMD ["gunicorn", "config.asgi:application", \
     "--config", "gunicorn.conf.py"]

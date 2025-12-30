"""
Gunicorn Configuration - Production Ready pour Render
Architecture ASGI unifiée (HTTP + WebSocket sur port 7788)
"""

import multiprocessing
import os

# Bind sur le port fourni par Render (ou 7788 par défaut)
bind = f"0.0.0.0:{os.getenv('PORT', '7788')}"

# Worker class: UvicornWorker pour ASGI (HTTP + WebSocket)
worker_class = "uvicorn.workers.UvicornWorker"

# Nombre de workers
# Formule recommandée: (2 x CPU) + 1
# Pour 100+ terminaux: minimum 4 workers
workers = int(os.getenv("WEB_CONCURRENCY", multiprocessing.cpu_count() * 2 + 1))

# Threads par worker (pour I/O bound)
threads = int(os.getenv("GUNICORN_THREADS", 2))

# Timeout
# Important pour WebSocket: timeout élevé (300s = 5min)
# Les terminaux biométriques maintiennent des connexions longues
timeout = 300
keepalive = 120

# Graceful timeout pour arrêt propre
graceful_timeout = 30

# Logs
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = os.getenv("LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Preload app pour économiser mémoire
preload_app = True

# Limites
max_requests = 1000  # Redémarre worker après 1000 requêtes (évite memory leaks)
max_requests_jitter = 50

# Worker tmp directory (pour heartbeat)
worker_tmp_dir = "/dev/shm" if os.path.exists("/dev/shm") else None

# Hooks
def on_starting(server):
    """Hook appelé au démarrage du serveur"""
    print(f"🚀 Starting Gunicorn on {bind}")
    print(f"👷 Workers: {workers} (class: {worker_class})")
    print(f"⏱️  Timeout: {timeout}s, Keepalive: {keepalive}s")

def worker_int(worker):
    """Hook appelé quand worker reçoit SIGINT"""
    print(f"⚠️  Worker {worker.pid} interrupted")

def post_fork(server, worker):
    """Hook appelé après fork d'un worker"""
    print(f"✅ Worker {worker.pid} spawned")

# Pourquoi cette configuration?
# 1. UvicornWorker: Supporte ASGI (HTTP + WebSocket)
# 2. Timeout élevé: Connexions WebSocket longue durée
# 3. Preload: Économise mémoire en chargeant app une fois
# 4. Multiple workers: Scalabilité horizontale
# 5. Graceful shutdown: Fermeture propre des connexions

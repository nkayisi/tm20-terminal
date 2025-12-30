# Recommandations de Scalabilité - TM20 Server

## Architecture Actuelle

### Capacité estimée (1 serveur)

| Métrique             | Valeur  |
| -------------------- | ------- |
| Terminaux simultanés | 100-200 |
| Messages/seconde     | ~500    |
| Logs/seconde         | ~100    |
| Latence moyenne      | <50ms   |

### Bottlenecks potentiels

1. **Connexions WebSocket** - Limité par la mémoire
2. **Écriture DB** - Limité par PostgreSQL
3. **Redis Channel Layer** - Limité par la bande passante

---

## Optimisations Implémentées

### 1. Batch Writes (Écriture groupée)

```python
# Au lieu d'écrire log par log
AttendanceLog.objects.bulk_create(logs_to_create)
```

**Gain** : 5-10x plus rapide pour les lots de logs

### 2. Device Manager Singleton

- Pool de connexions centralisé
- Lock async pour thread-safety
- Métriques intégrées

### 3. Event Bus Découplé

- Communication asynchrone
- Pas de blocage du consumer
- Extensible pour pub/sub

### 4. Métriques temps réel

- Compteurs sans lock (atomiques)
- Histogrammes pour latence
- Rate limiters intégrés

---

## Scaling Horizontal (100+ terminaux)

### Option 1 : Load Balancer + Sticky Sessions

```
                    ┌─────────────┐
                    │   HAProxy   │
                    │   (LB)      │
                    └──────┬──────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
    ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
    │  Django 1   │ │  Django 2   │ │  Django 3   │
    │  (Daphne)   │ │  (Daphne)   │ │  (Daphne)   │
    └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
           │               │               │
           └───────────────┼───────────────┘
                           │
                    ┌──────▼──────┐
                    │    Redis    │
                    │  (Cluster)  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  PostgreSQL │
                    │  (Primary)  │
                    └─────────────┘
```

**Configuration HAProxy** :

```haproxy
frontend websocket
    bind *:7788
    mode http
    default_backend tm20_servers

backend tm20_servers
    mode http
    balance source  # Sticky sessions par IP
    option httpchk GET /health/
    server tm20_1 django1:7788 check
    server tm20_2 django2:7788 check
    server tm20_3 django3:7788 check
```

### Option 2 : Redis Pub/Sub pour Synchronisation

Pour les commandes cross-server :

```python
# Publier une commande
await redis.publish(f'device:{sn}:command', json.dumps(command))

# Chaque serveur s'abonne
async for message in redis.subscribe(f'device:*:command'):
    sn = message.channel.split(':')[1]
    if sn in local_devices:
        await send_to_device(sn, message.data)
```

---

## Configuration PostgreSQL Optimisée

### postgresql.conf

```ini
# Connexions
max_connections = 200
shared_buffers = 256MB

# Écriture
wal_level = minimal
synchronous_commit = off  # ⚠️ Risque perte données

# Mémoire
work_mem = 16MB
maintenance_work_mem = 128MB

# Checkpoint
checkpoint_completion_target = 0.9
```

### Index recommandés

```sql
-- Déjà créés par Django
CREATE INDEX idx_logs_terminal_time ON tm20_attendance_logs(terminal_id, time);
CREATE INDEX idx_logs_enrollid_time ON tm20_attendance_logs(enrollid, time);

-- Optionnel pour dashboards
CREATE INDEX idx_logs_time_desc ON tm20_attendance_logs(time DESC);
```

---

## Configuration Redis Optimisée

### redis.conf

```ini
# Mémoire
maxmemory 512mb
maxmemory-policy allkeys-lru

# Persistance (désactiver si non critique)
save ""
appendonly no

# Connexions
maxclients 10000
tcp-keepalive 300
```

---

## Monitoring et Alertes

### Métriques à surveiller

| Métrique           | Seuil Warning | Seuil Critical |
| ------------------ | ------------- | -------------- |
| Connexions actives | >80% capacité | >95%           |
| Latence P95        | >100ms        | >500ms         |
| Queue size         | >100          | >500           |
| Mémoire            | >70%          | >90%           |
| CPU                | >70%          | >90%           |

### Prometheus Metrics

```python
# Ajouter à metrics.py
from prometheus_client import Counter, Gauge, Histogram

CONNECTIONS = Gauge('tm20_connections_active', 'Active connections')
MESSAGES = Counter('tm20_messages_total', 'Total messages', ['direction'])
LATENCY = Histogram('tm20_latency_seconds', 'Message latency')
```

### Alertes Recommandées

```yaml
# alertmanager.yml
groups:
  - name: tm20
    rules:
      - alert: HighLatency
        expr: tm20_latency_seconds{quantile="0.95"} > 0.5
        for: 5m

      - alert: ConnectionsDrop
        expr: rate(tm20_connections_active[5m]) < -10
        for: 2m
```

---

## Limites Connues

### Limites par Instance

| Ressource         | Limite | Raison                 |
| ----------------- | ------ | ---------------------- |
| Connexions WS     | ~1000  | File descriptors Linux |
| Mémoire/connexion | ~2MB   | Buffer + état          |
| Messages/sec      | ~1000  | Event loop Python      |

### Recommandations

- **< 50 terminaux** : 1 serveur suffit
- **50-200 terminaux** : 2-3 serveurs + LB
- **> 200 terminaux** : Cluster avec Redis Pub/Sub

---

## Migration vers Architecture Cluster

### Étape 1 : Redis Cluster

```bash
# docker-compose.prod.yml
redis:
  image: redis:7-alpine
  command: redis-server --cluster-enabled yes
  deploy:
    replicas: 3
```

### Étape 2 : PostgreSQL avec Réplication

```yaml
postgres-primary:
  image: postgres:15
  environment:
    - POSTGRES_REPLICATION_MODE=master

postgres-replica:
  image: postgres:15
  environment:
    - POSTGRES_REPLICATION_MODE=slave
    - POSTGRES_MASTER_HOST=postgres-primary
```

### Étape 3 : Django Stateless

- Stocker les sessions dans Redis
- Pas d'état local dans le consumer
- Device Manager synchronisé via Redis

---

## Checklist Production

- [ ] PostgreSQL : Connexions poolées (pgbouncer)
- [ ] Redis : Sentinel pour HA
- [ ] Django : Gunicorn workers = 2\*CPU + 1
- [ ] Daphne : Workers = CPU count
- [ ] Logs : Centralisés (ELK/Loki)
- [ ] Backups : PostgreSQL WAL archiving
- [ ] Monitoring : Prometheus + Grafana
- [ ] Alertes : PagerDuty/Slack

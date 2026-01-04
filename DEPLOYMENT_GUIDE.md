# Guide de Déploiement - Nouvelles Fonctionnalités TM20

## Fonctionnalités Ajoutées

### 1. Synchronisation avec Services Tiers

- Configuration de connexions API vers des systèmes externes
- Récupération automatique des utilisateurs depuis services tiers
- Envoi automatique des pointages vers services tiers
- Gestion des statuts de synchronisation (pending, sent, failed)

### 2. Gestion des Horaires par Terminal

- Configuration d'horaires de travail par jour de la semaine
- Définition des heures d'arrivée, pause et sortie
- Tolérance de retard configurable
- Synchronisation des horaires vers les terminaux physiques

### 3. Tâches Automatiques

- Synchronisation périodique des pointages (toutes les 15 minutes)
- Retry automatique des pointages échoués (toutes les heures)
- Gestion des erreurs et tentatives multiples

## Installation

### 1. Installer les nouvelles dépendances

```bash
pip install -r requirements.txt
```

Nouvelles dépendances ajoutées:

- `celery>=5.3.0` - Tâches asynchrones
- `django-celery-beat>=2.5.0` - Tâches périodiques
- `httpx>=0.26.0` - Client HTTP asynchrone

### 2. Appliquer les migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

Nouveaux modèles créés:

- `ThirdPartyConfig` - Configuration des services tiers
- `TerminalSchedule` - Horaires de travail par terminal
- `TerminalThirdPartyMapping` - Mapping terminal ↔ service tiers
- Champs ajoutés à `AttendanceLog`: `sync_status`, `sync_attempts`, `synced_at`, `sync_error`

### 3. Démarrer Celery Worker

```bash
# Worker pour les tâches asynchrones
celery -A config worker -l info

# Beat pour les tâches périodiques
celery -A config beat -l info
```

Pour production, utilisez un gestionnaire de processus comme Supervisor:

```ini
[program:tm20_celery_worker]
command=/path/to/venv/bin/celery -A config worker -l info
directory=/path/to/tm20_server
user=appuser
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/tm20/celery_worker.log

[program:tm20_celery_beat]
command=/path/to/venv/bin/celery -A config beat -l info
directory=/path/to/tm20_server
user=appuser
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/tm20/celery_beat.log
```

### 4. Configuration Docker (optionnel)

Ajoutez ces services au `docker-compose.yml`:

```yaml
celery-worker:
  build: .
  container_name: tm20_celery_worker
  command: celery -A config worker -l info
  volumes:
    - .:/app
  environment:
    - DATABASE_URL=postgres://tm20_user:tm20_password@postgres:5432/tm20_db
    - REDIS_URL=redis://redis:6379/0
  depends_on:
    - postgres
    - redis

celery-beat:
  build: .
  container_name: tm20_celery_beat
  command: celery -A config beat -l info
  volumes:
    - .:/app
  environment:
    - DATABASE_URL=postgres://tm20_user:tm20_password@postgres:5432/tm20_db
    - REDIS_URL=redis://redis:6379/0
  depends_on:
    - postgres
    - redis
```

## Utilisation

### 1. Configuration d'un Service Tiers

#### Via l'Admin Django

1. Accédez à `/admin/devices/thirdpartyconfig/`
2. Créez une nouvelle configuration avec:
   - Nom du service
   - URL de base de l'API
   - Endpoints (utilisateurs et pointages)
   - Type d'authentification et token
   - Intervalle de synchronisation

#### Via l'API REST

```bash
curl -X POST http://localhost:8000/devices/api/third-party-configs/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Mon Service RH",
    "base_url": "https://api.monservice.com",
    "users_endpoint": "/api/v1/employees",
    "attendance_endpoint": "/api/v1/attendance",
    "auth_type": "bearer",
    "auth_token": "your-api-token-here",
    "sync_interval_minutes": 15
  }'
```

#### Via le Dashboard

1. Accédez à `/devices/dashboard/management/`
2. Cliquez sur "Gérer les Configurations"
3. Créez une nouvelle configuration

### 2. Synchronisation des Utilisateurs

#### Récupérer les utilisateurs depuis un service tiers

```bash
curl -X POST http://localhost:8000/devices/api/sync/users/from-third-party/ \
  -H "Content-Type: application/json" \
  -d '{
    "terminal_id": 1,
    "config_id": 1
  }'
```

#### Charger les utilisateurs sur un terminal

```bash
curl -X POST http://localhost:8000/devices/api/sync/users/to-terminal/ \
  -H "Content-Type: application/json" \
  -d '{
    "terminal_id": 1,
    "user_ids": [1, 2, 3]  # Optionnel, null = tous
  }'
```

### 3. Configuration des Horaires

#### Créer un horaire pour un terminal

```bash
curl -X POST http://localhost:8000/devices/api/terminals/1/schedules/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Horaire Standard",
    "weekday": 0,
    "check_in_time": "08:00",
    "check_out_time": "17:00",
    "break_start_time": "12:00",
    "break_end_time": "13:00",
    "tolerance_minutes": 15
  }'
```

#### Synchroniser les horaires vers le terminal

```bash
curl -X POST http://localhost:8000/devices/api/terminals/1/schedules/sync/ \
  -H "Content-Type: application/json" \
  -d '{
    "schedule_id": 1  # Optionnel, null = tous les horaires
  }'
```

### 4. Gestion de la Synchronisation des Pointages

#### Vérifier le statut de synchronisation

```bash
curl http://localhost:8000/devices/api/attendance/sync-status/?status=pending
```

#### Déclencher manuellement une synchronisation

```bash
curl -X POST http://localhost:8000/devices/api/attendance/manual-sync/ \
  -H "Content-Type: application/json" \
  -d '{
    "config_id": 1,
    "terminal_id": 1  # Optionnel
  }'
```

## Format des Données pour Services Tiers

### Format attendu pour les utilisateurs (GET)

```json
{
  "users": [
    {
      "enrollid": 123,
      "name": "John Doe",
      "admin": 0,
      "is_enabled": true,
      "weekzone": 1,
      "group": 0
    }
  ]
}
```

### Format d'envoi des pointages (POST)

```json
{
  "attendance": [
    {
      "terminal_sn": "TM20-001",
      "enrollid": 123,
      "user_name": "John Doe",
      "time": "2025-12-30T10:30:00Z",
      "mode": 0,
      "inout": 0,
      "event": 0,
      "temperature": 36.5,
      "access_granted": true,
      "log_id": 456
    }
  ]
}
```

## Dashboard de Gestion

Accédez au dashboard de gestion à: `/devices/dashboard/management/`

Fonctionnalités disponibles:

- **Services Tiers**: Configuration des connexions API
- **Horaires**: Gestion des horaires par terminal
- **Sync Utilisateurs**: Récupération et chargement des utilisateurs
- **Sync Pointages**: Monitoring et gestion de l'envoi des pointages

## Monitoring

### Vérifier les tâches Celery

```bash
# Voir les tâches actives
celery -A config inspect active

# Voir les tâches planifiées
celery -A config inspect scheduled

# Statistiques
celery -A config inspect stats
```

### Logs

- Logs Celery: `/var/log/tm20/celery_*.log`
- Logs Django: `/path/to/tm20_server/logs/tm20.log`
- Logs synchronisation: Recherchez "sync" dans les logs

### Métriques importantes

- Pointages en attente: `AttendanceLog.objects.filter(sync_status='pending').count()`
- Pointages échoués: `AttendanceLog.objects.filter(sync_status='failed').count()`
- Dernière synchronisation: Vérifiez `TerminalThirdPartyMapping.last_attendance_sync`

## Dépannage

### Les pointages ne sont pas envoyés

1. Vérifiez que Celery Beat est démarré
2. Vérifiez la configuration du service tiers (actif, endpoint correct)
3. Vérifiez les logs pour les erreurs d'API
4. Testez manuellement l'endpoint avec curl

### Les utilisateurs ne se synchronisent pas

1. Vérifiez que le terminal est connecté
2. Vérifiez le format de réponse de l'API externe
3. Vérifiez les logs pour les erreurs de parsing
4. Testez l'API externe directement

### Les horaires ne se chargent pas sur le terminal

1. Vérifiez que le terminal supporte la commande `setschedule`
2. Vérifiez que le terminal est connecté via WebSocket
3. Consultez les logs du consumer WebSocket

## Sécurité

- **Tokens API**: Stockés en base de données, utilisez des variables d'environnement pour la production
- **HTTPS**: Utilisez toujours HTTPS pour les communications avec services tiers
- **Validation**: Toutes les données externes sont validées avant insertion
- **Rate Limiting**: Implémentez un rate limiting sur les endpoints API si nécessaire

## Performance

- Les tâches Celery sont asynchrones et n'impactent pas les performances du serveur principal
- La synchronisation se fait par batch (100 logs par défaut)
- Les retry sont espacés avec backoff exponentiel
- Redis est utilisé pour le cache et la communication entre processus

## Support

Pour toute question ou problème:

1. Consultez les logs
2. Vérifiez la configuration
3. Testez les endpoints manuellement
4. Contactez l'équipe de support

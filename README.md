# TM20 WebSocket Server

Serveur Django pour la communication avec les terminaux biométriques TM20-WIFI via le protocole WebSocket + JSON v2.4.

## Architecture

```
tm20_server/
├── config/                 # Configuration Django
│   ├── settings.py        # Settings (Channels, Redis, PostgreSQL)
│   ├── asgi.py            # Point d'entrée ASGI
│   └── urls.py            # URLs principales
├── devices/               # Application principale
│   ├── consumers.py       # WebSocket Consumer TM20
│   ├── protocol.py        # Parsing/validation protocole
│   ├── services.py        # Logique métier
│   ├── models.py          # Modèles Django
│   ├── routing.py         # Routes WebSocket
│   ├── views.py           # API REST (optionnel)
│   └── admin.py           # Interface admin
├── requirements.txt
├── docker-compose.yml
└── Dockerfile
```

## Prérequis

- Python 3.11+
- PostgreSQL 15+
- Redis 7+

## Installation

### Option 1: Docker (recommandé)

```bash
# Lancer tous les services
docker-compose up -d

# Voir les logs
docker-compose logs -f django
```

### Option 2: Installation manuelle

```bash
# Créer l'environnement virtuel
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou: venv\Scripts\activate  # Windows

# Installer les dépendances
pip install -r requirements.txt

# Copier et configurer l'environnement
cp .env.example .env
# Éditer .env avec vos paramètres

# Migrations
python manage.py migrate

# Créer un superutilisateur
python manage.py createsuperuser

# Lancer le serveur
daphne -b 0.0.0.0 -p 7788 config.asgi:application
```

## Configuration du terminal TM20

1. Accéder aux paramètres réseau du terminal TM20
2. Configurer le mode "Cloud Server"
3. Entrer l'adresse du serveur : `ws://VOTRE_IP:7788/ws/tm20/`
4. Redémarrer le terminal

## Protocole WebSocket

### Port par défaut

- **7788** (configurable via `TM20_WEBSOCKET_PORT`)

### Endpoint WebSocket

- `ws://server:7788/ws/tm20/`

### Messages Terminal → Serveur

#### Enregistrement (reg)

```json
{
  "cmd": "reg",
  "sn": "ZX0006827500",
  "cpusn": "123456789",
  "devinfo": {
    "modelname": "tfs30",
    "usersize": 3000,
    "fpsize": 3000,
    "firmware": "th600w v6.1",
    "time": "2024-01-15 10:30:00",
    "mac": "00-01-A9-01-00-01"
  }
}
```

#### Logs de pointage (sendlog)

```json
{
  "cmd": "sendlog",
  "sn": "ZX0006827500",
  "count": 2,
  "logindex": 10,
  "record": [
    {
      "enrollid": 1,
      "time": "2024-01-15 10:30:00",
      "mode": 0,
      "inout": 0,
      "event": 0
    }
  ]
}
```

#### Envoi utilisateur (senduser)

```json
{
  "cmd": "senduser",
  "enrollid": 1,
  "name": "John Doe",
  "backupnum": 0,
  "admin": 0,
  "record": "base64_fingerprint_data"
}
```

### Messages Serveur → Terminal

#### Définir utilisateur (setuserinfo)

```json
{
  "cmd": "setuserinfo",
  "enrollid": 1,
  "name": "John Doe",
  "backupnum": 0,
  "admin": 0,
  "record": "base64_fingerprint_data"
}
```

#### Supprimer utilisateur (deleteuser)

```json
{
  "cmd": "deleteuser",
  "enrollid": 1,
  "backupnum": 13
}
```

#### Ouvrir la porte (opendoor)

```json
{
  "cmd": "opendoor",
  "door": 1,
  "delay": 5
}
```

#### Synchroniser l'heure (settime)

```json
{
  "cmd": "settime",
  "cloudtime": "2024-01-15 10:30:00"
}
```

## API REST

### Endpoints disponibles

| Méthode | URL                            | Description              |
| ------- | ------------------------------ | ------------------------ |
| GET     | `/api/terminals/`              | Liste des terminaux      |
| GET     | `/api/terminals/{sn}/`         | Détail d'un terminal     |
| PATCH   | `/api/terminals/{sn}/`         | Modifier un terminal     |
| POST    | `/api/terminals/{sn}/command/` | Envoyer une commande     |
| GET     | `/api/terminals/{sn}/users/`   | Utilisateurs du terminal |
| GET     | `/api/terminals/{sn}/logs/`    | Logs de pointage         |
| GET     | `/api/connected/`              | Terminaux connectés      |

### Exemples d'utilisation

```bash
# Lister les terminaux
curl http://localhost:7788/api/terminals/

# Ouvrir la porte
curl -X POST http://localhost:7788/api/terminals/ZX0006827500/command/ \
  -H "Content-Type: application/json" \
  -d '{"command": "opendoor", "params": {"door": 1, "delay": 5}}'

# Synchroniser l'heure
curl -X POST http://localhost:7788/api/terminals/ZX0006827500/command/ \
  -H "Content-Type: application/json" \
  -d '{"command": "settime"}'

# Récupérer les logs
curl "http://localhost:7788/api/terminals/ZX0006827500/logs/?limit=50"
```

## Test WebSocket

### Avec websocat

```bash
# Installer websocat
brew install websocat  # Mac
# ou: cargo install websocat

# Connecter et envoyer un message de test
echo '{"cmd":"reg","sn":"TEST001","devinfo":{"modelname":"test"}}' | \
  websocat ws://localhost:7788/ws/tm20/
```

### Avec Python

```python
import asyncio
import websockets
import json

async def test_terminal():
    uri = "ws://localhost:7788/ws/tm20/"
    async with websockets.connect(uri) as ws:
        # Enregistrement
        reg = {
            "cmd": "reg",
            "sn": "TEST001",
            "devinfo": {"modelname": "test", "firmware": "v1.0"}
        }
        await ws.send(json.dumps(reg))
        response = await ws.recv()
        print(f"Réponse: {response}")

asyncio.run(test_terminal())
```

## Modèles de données

### Terminal

- `sn`: Numéro de série (unique)
- `model`: Modèle du terminal
- `firmware`: Version firmware
- `is_active`: Terminal actif
- `is_whitelisted`: Autorisé à se connecter
- `last_seen`: Dernière connexion

### BiometricUser

- `terminal`: Terminal associé
- `enrollid`: ID d'enrôlement
- `name`: Nom de l'utilisateur
- `admin`: Niveau admin (0=normal, 1=admin, 2=super)
- `is_enabled`: Utilisateur activé

### BiometricCredential

- `user`: Utilisateur associé
- `backupnum`: Type (0-9=empreintes, 10=password, 11=carte, 20-27=visage, 50=photo)
- `record`: Données biométriques (base64)

### AttendanceLog

- `terminal`: Terminal source
- `user`: Utilisateur (si connu)
- `enrollid`: ID d'enrôlement
- `time`: Date/heure du pointage
- `mode`: Mode de vérification
- `inout`: Entrée/Sortie
- `access_granted`: Accès accordé

## Interface d'administration

Accéder à l'admin Django : `http://localhost:7788/admin/`

## Variables d'environnement

| Variable                  | Description              | Défaut                     |
| ------------------------- | ------------------------ | -------------------------- |
| `DJANGO_SECRET_KEY`       | Clé secrète Django       | (requis en prod)           |
| `DEBUG`                   | Mode debug               | `0`                        |
| `DATABASE_URL`            | URL PostgreSQL           | `postgres://...`           |
| `REDIS_URL`               | URL Redis                | `redis://localhost:6379/0` |
| `TM20_WEBSOCKET_PORT`     | Port WebSocket           | `7788`                     |
| `TM20_HEARTBEAT_INTERVAL` | Intervalle heartbeat (s) | `30`                       |
| `TM20_CONNECTION_TIMEOUT` | Timeout connexion (s)    | `120`                      |
| `TM20_REQUIRE_WHITELIST`  | Activer whitelist        | `0`                        |

## Sécurité

- **Whitelist**: Activez `TM20_REQUIRE_WHITELIST=1` pour n'accepter que les terminaux pré-enregistrés
- **HTTPS/WSS**: Utilisez un reverse proxy (nginx) avec TLS en production
- **Firewall**: Limitez l'accès au port 7788 aux IPs des terminaux
- **Logs**: Les messages sont journalisés dans `logs/tm20.log`

## Développement

```bash
# Lancer les tests
python manage.py test

# Vérifier les migrations
python manage.py makemigrations --check

# Shell Django
python manage.py shell
```

## Licence

Propriétaire - Tous droits réservés

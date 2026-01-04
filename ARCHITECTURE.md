# Architecture du Projet TM20 Server

## 📁 Structure du Projet

```
tm20_server/
├── config/                 # Configuration Django
│   ├── settings.py        # Paramètres Django
│   ├── urls.py           # URLs principales
│   └── asgi.py           # Configuration ASGI (WebSocket)
├── devices/               # Application principale
│   ├── models.py         # Modèles de données
│   ├── consumers.py      # WebSocket consumers
│   ├── routing.py        # Routing WebSocket
│   ├── api/              # API REST
│   │   ├── urls.py
│   │   └── views.py
│   ├── dashboard/        # Dashboard de gestion
│   │   ├── views.py      # Vues temps réel
│   │   ├── management_views.py  # Vues de gestion
│   │   ├── forms.py      # Formulaires Django
│   │   └── urls.py
│   ├── core/             # Logique métier
│   │   ├── device_manager.py
│   │   ├── protocol.py
│   │   ├── metrics.py
│   │   └── events.py
│   ├── services/         # Services métier
│   │   ├── user_sync_service.py
│   │   └── attendance_sync_service.py
│   ├── integrations/     # Intégrations services tiers
│   │   ├── base.py
│   │   └── adapters/
│   └── jobs/             # Tâches planifiées
│       ├── user_sync_job.py
│       └── attendance_sync_job.py
└── templates/
    └── devices/
        └── dashboard/    # Templates du dashboard
            ├── base.html
            ├── index.html
            ├── management.html
            ├── third_party_configs.html
            ├── terminal_schedules.html
            ├── user_sync.html
            └── attendance_sync.html
```

## 🎯 Principes de Conception

### 1. **Architecture en Couches**

- **Modèles** : Définition des données (Django ORM)
- **Services** : Logique métier réutilisable
- **Vues** : Présentation et interaction utilisateur
- **API** : Endpoints REST pour intégrations

### 2. **Séparation des Responsabilités**

- **Core** : Gestion des terminaux et protocole
- **Services** : Synchronisation et intégrations
- **Dashboard** : Interface utilisateur
- **Jobs** : Tâches asynchrones

### 3. **Django Pur**

- Formulaires Django natifs (`forms.py`)
- Validation côté serveur
- Messages Django pour feedback
- POST/Redirect/GET pattern
- Pas de dépendance JavaScript pour les fonctionnalités critiques

## 🔧 Bonnes Pratiques Appliquées

### Templates

- ✅ Héritage de templates (`base.html`)
- ✅ Blocs Django pour réutilisabilité
- ✅ CSRF tokens sur tous les formulaires POST
- ✅ Messages Django pour feedback utilisateur
- ✅ Tailwind CSS pour le styling

### Vues

- ✅ Class-Based Views (CBV)
- ✅ Méthodes GET et POST séparées
- ✅ Validation avec formulaires Django
- ✅ Redirections après POST
- ✅ Messages de succès/erreur

### Modèles

- ✅ Relations explicites (ForeignKey, ManyToMany)
- ✅ Contraintes de base de données
- ✅ Indexes pour performance
- ✅ Méthodes `__str__()` descriptives
- ✅ Timestamps automatiques

### Services

- ✅ Classes de service réutilisables
- ✅ Adapters pour intégrations tierces
- ✅ Gestion d'erreurs robuste
- ✅ Logging approprié

## 🚀 Fonctionnalités Principales

### 1. **Gestion des Terminaux**

- Connexion WebSocket temps réel
- Synchronisation bidirectionnelle
- Gestion des commandes
- Monitoring en direct

### 2. **Synchronisation Utilisateurs**

- Import depuis services tiers
- Mapping terminal ↔ configuration
- Validation et déduplication
- Logs de synchronisation

### 3. **Synchronisation Pointages**

- Envoi automatique vers services tiers
- Système de retry avec backoff
- Dead-letter queue pour échecs
- Statistiques en temps réel

### 4. **Gestion des Horaires**

- Configuration par terminal
- Horaires par jour de semaine
- Tolérance de retard
- Pauses configurables

## 🔐 Sécurité

- ✅ CSRF protection sur tous les formulaires
- ✅ Validation côté serveur
- ✅ Authentification requise pour le dashboard
- ✅ Tokens d'API sécurisés
- ✅ Pas de données sensibles en frontend

## 📊 Performance

- ✅ Indexes sur colonnes fréquemment requêtées
- ✅ Select_related/Prefetch_related pour optimiser les requêtes
- ✅ Pagination des listes
- ✅ Cache Redis pour données partagées
- ✅ WebSocket pour communication temps réel

## 🧪 Tests

- Tests unitaires pour services
- Tests d'intégration pour API
- Tests de vues Django
- Tests WebSocket

## 📝 Conventions de Code

### Nommage

- **Modèles** : PascalCase (ex: `BiometricUser`)
- **Vues** : PascalCase + suffixe View (ex: `DashboardView`)
- **Fonctions** : snake_case (ex: `sync_users`)
- **Templates** : snake_case.html (ex: `user_sync.html`)

### Documentation

- Docstrings pour toutes les classes et fonctions
- Commentaires pour logique complexe
- README pour chaque module important

### Git

- Commits atomiques et descriptifs
- Branches feature pour nouvelles fonctionnalités
- Pull requests pour review de code

## 🔄 Workflow de Développement

1. **Créer une branche feature**
2. **Développer avec tests**
3. **Valider localement**
4. **Commit et push**
5. **Pull request et review**
6. **Merge vers main**
7. **Déploiement**

## 📚 Ressources

- [Django Documentation](https://docs.djangoproject.com/)
- [Tailwind CSS](https://tailwindcss.com/)
- [Alpine.js](https://alpinejs.dev/)
- [Django Channels](https://channels.readthedocs.io/)

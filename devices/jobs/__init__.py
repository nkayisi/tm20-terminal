"""
Jobs - Tâches asynchrones et planifiées

Ce module contient les tâches Celery pour:
- Synchronisation périodique des pointages
- Retry des pointages échoués
- Synchronisation des utilisateurs
- Nettoyage des dead-letter
"""

from .sync_tasks import (
    sync_pending_attendance,
    retry_failed_attendance,
    sync_users_from_third_party,
    sync_all_configs_attendance,
    cleanup_dead_letter_logs,
)

__all__ = [
    'sync_pending_attendance',
    'retry_failed_attendance', 
    'sync_users_from_third_party',
    'sync_all_configs_attendance',
    'cleanup_dead_letter_logs',
]

"""
Configuration Celery pour tâches asynchrones et périodiques
"""

import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('tm20_server')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks(['devices.jobs'])

app.conf.beat_schedule = {
    'auto-sync-attendance-every-minute': {
        'task': 'devices.auto_sync_all_attendance',
        'schedule': crontab(minute='*'),  # Toutes les minutes
    },
    'retry-failed-attendance-hourly': {
        'task': 'devices.retry_failed_attendance',
        'schedule': crontab(minute=0),  # Toutes les heures
    },
    'cleanup-dead-letter-weekly': {
        'task': 'devices.cleanup_dead_letter_logs',
        'schedule': crontab(hour=3, minute=0, day_of_week=0),  # Dimanche à 3h
        'kwargs': {'days_old': 30},
    },
}

app.conf.timezone = 'UTC'

app.conf.task_routes = {
    'devices.sync_*': {'queue': 'sync'},
    'devices.auto_*': {'queue': 'sync'},
    'devices.retry_*': {'queue': 'sync'},
    'devices.cleanup_*': {'queue': 'maintenance'},
}

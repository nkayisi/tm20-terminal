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
    'sync-all-attendance-every-15-minutes': {
        'task': 'devices.sync_all_configs_attendance',
        'schedule': crontab(minute='*/15'),
    },
    'retry-failed-attendance-hourly': {
        'task': 'devices.retry_failed_attendance',
        'schedule': crontab(minute=0),
    },
    'cleanup-dead-letter-weekly': {
        'task': 'devices.cleanup_dead_letter_logs',
        'schedule': crontab(hour=3, minute=0, day_of_week=0),
        'kwargs': {'days_old': 30},
    },
}

app.conf.timezone = 'UTC'

app.conf.task_routes = {
    'devices.sync_*': {'queue': 'sync'},
    'devices.retry_*': {'queue': 'sync'},
    'devices.cleanup_*': {'queue': 'maintenance'},
}

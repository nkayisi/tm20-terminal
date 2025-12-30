"""
Configuration Celery pour tâches asynchrones et périodiques
"""

import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('tm20_server')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()

app.conf.beat_schedule = {
    'sync-pending-attendance-every-15-minutes': {
        'task': 'devices.tasks.sync_pending_attendance_task',
        'schedule': crontab(minute='*/15'),
    },
    'retry-failed-attendance-hourly': {
        'task': 'devices.tasks.retry_failed_attendance_task',
        'schedule': crontab(minute=0),
    },
}

app.conf.timezone = 'UTC'

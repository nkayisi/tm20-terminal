"""
Health check endpoint pour les conteneurs Docker
"""
from django.http import JsonResponse
from django.db import connection
from django.core.cache import cache
import redis
import os


def health_check(request):
    """
    Endpoint de health check pour Docker et Dokploy
    Vérifie la connexion à la base de données et Redis
    """
    health_status = {
        'status': 'healthy',
        'database': 'unknown',
        'redis': 'unknown',
        'cache': 'unknown',
    }
    
    status_code = 200
    
    # Test de la base de données
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        health_status['database'] = 'connected'
    except Exception as e:
        health_status['database'] = f'error: {str(e)}'
        health_status['status'] = 'unhealthy'
        status_code = 503
    
    # Test de Redis
    try:
        redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
        r = redis.from_url(redis_url)
        r.ping()
        health_status['redis'] = 'connected'
    except Exception as e:
        health_status['redis'] = f'error: {str(e)}'
        health_status['status'] = 'unhealthy'
        status_code = 503
    
    # Test du cache Django
    try:
        cache.set('health_check', 'ok', 10)
        if cache.get('health_check') == 'ok':
            health_status['cache'] = 'working'
        else:
            health_status['cache'] = 'not_working'
    except Exception as e:
        health_status['cache'] = f'error: {str(e)}'
    
    return JsonResponse(health_status, status=status_code)

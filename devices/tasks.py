"""
Tâches Celery pour synchronisation automatique
"""

import logging
from celery import shared_task
from asgiref.sync import async_to_sync
from django.utils import timezone

from .models import ThirdPartyConfig, TerminalThirdPartyMapping, AttendanceLog
from .services.third_party_sync import AttendanceSyncService

logger = logging.getLogger('devices.tasks')


@shared_task(bind=True, max_retries=3)
def sync_pending_attendance_task(self):
    """
    Tâche périodique: Synchronise les pointages en attente vers les services tiers
    Exécutée toutes les 15 minutes (configurable)
    """
    try:
        logger.info("🔄 Démarrage synchronisation pointages en attente")
        
        active_configs = ThirdPartyConfig.objects.filter(
            is_active=True,
            attendance_endpoint__isnull=False
        ).exclude(attendance_endpoint='')
        
        total_sent = 0
        total_failed = 0
        
        for config in active_configs:
            try:
                sent, failed, error = async_to_sync(
                    AttendanceSyncService.sync_pending_attendance
                )(config, batch_size=100)
                
                total_sent += sent
                total_failed += failed
                
                if error:
                    logger.error(f"Erreur sync pour {config.name}: {error}")
                    
            except Exception as e:
                logger.exception(f"Exception sync pour {config.name}: {e}")
                continue
        
        logger.info(
            f"✅ Synchronisation terminée: {total_sent} envoyés, {total_failed} échoués"
        )
        
        return {
            'status': 'success',
            'sent': total_sent,
            'failed': total_failed,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.exception(f"Erreur critique dans sync_pending_attendance_task: {e}")
        raise self.retry(exc=e, countdown=300)


@shared_task(bind=True, max_retries=2)
def retry_failed_attendance_task(self):
    """
    Tâche périodique: Retente l'envoi des pointages échoués
    Exécutée toutes les heures
    """
    try:
        logger.info("🔄 Démarrage retry pointages échoués")
        
        active_configs = ThirdPartyConfig.objects.filter(
            is_active=True,
            attendance_endpoint__isnull=False
        ).exclude(attendance_endpoint='')
        
        total_sent = 0
        total_still_failed = 0
        
        for config in active_configs:
            try:
                sent, still_failed = async_to_sync(
                    AttendanceSyncService.retry_failed_attendance
                )(config, max_attempts=5)
                
                total_sent += sent
                total_still_failed += still_failed
                
            except Exception as e:
                logger.exception(f"Exception retry pour {config.name}: {e}")
                continue
        
        logger.info(
            f"✅ Retry terminé: {total_sent} récupérés, {total_still_failed} toujours échoués"
        )
        
        return {
            'status': 'success',
            'recovered': total_sent,
            'still_failed': total_still_failed,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.exception(f"Erreur critique dans retry_failed_attendance_task: {e}")
        raise self.retry(exc=e, countdown=600)


@shared_task
def sync_users_from_third_party_task(terminal_id: int, config_id: int):
    """
    Tâche asynchrone: Synchronise les utilisateurs depuis un service tiers
    
    Args:
        terminal_id: ID du terminal
        config_id: ID de la configuration service tiers
    """
    from .models import Terminal
    from .services.third_party_sync import UserSyncService
    
    try:
        logger.info(f"🔄 Synchronisation utilisateurs: terminal={terminal_id}, config={config_id}")
        
        terminal = Terminal.objects.get(id=terminal_id)
        config = ThirdPartyConfig.objects.get(id=config_id)
        
        created, updated, error = async_to_sync(
            UserSyncService.sync_users_for_terminal
        )(terminal, config)
        
        if error:
            logger.error(f"Erreur sync utilisateurs: {error}")
            return {
                'status': 'error',
                'error': error,
                'terminal_sn': terminal.sn
            }
        
        logger.info(
            f"✅ Utilisateurs synchronisés pour {terminal.sn}: "
            f"{created} créés, {updated} mis à jour"
        )
        
        return {
            'status': 'success',
            'terminal_sn': terminal.sn,
            'created': created,
            'updated': updated,
            'timestamp': timezone.now().isoformat()
        }
        
    except Terminal.DoesNotExist:
        error = f"Terminal {terminal_id} introuvable"
        logger.error(error)
        return {'status': 'error', 'error': error}
        
    except ThirdPartyConfig.DoesNotExist:
        error = f"Configuration {config_id} introuvable"
        logger.error(error)
        return {'status': 'error', 'error': error}
        
    except Exception as e:
        logger.exception(f"Exception sync utilisateurs: {e}")
        return {'status': 'error', 'error': str(e)}


@shared_task
def sync_users_to_terminal_device_task(terminal_id: int, user_ids: list = None):
    """
    Tâche asynchrone: Envoie les utilisateurs vers le terminal physique
    
    Args:
        terminal_id: ID du terminal
        user_ids: Liste des IDs utilisateurs (None = tous)
    """
    from .models import Terminal
    from .services.third_party_sync import UserSyncService
    
    try:
        logger.info(f"🔄 Envoi utilisateurs vers terminal {terminal_id}")
        
        terminal = Terminal.objects.get(id=terminal_id)
        
        success, error = async_to_sync(
            UserSyncService.sync_users_to_terminal_device
        )(terminal, user_ids)
        
        if not success:
            logger.error(f"Erreur envoi utilisateurs vers {terminal.sn}: {error}")
            return {
                'status': 'error',
                'error': error,
                'terminal_sn': terminal.sn
            }
        
        logger.info(f"✅ Utilisateurs envoyés vers {terminal.sn}")
        
        return {
            'status': 'success',
            'terminal_sn': terminal.sn,
            'message': error or 'Tous les utilisateurs synchronisés',
            'timestamp': timezone.now().isoformat()
        }
        
    except Terminal.DoesNotExist:
        error = f"Terminal {terminal_id} introuvable"
        logger.error(error)
        return {'status': 'error', 'error': error}
        
    except Exception as e:
        logger.exception(f"Exception envoi utilisateurs: {e}")
        return {'status': 'error', 'error': str(e)}


@shared_task
def sync_schedule_to_terminal_task(terminal_id: int, schedule_id: int = None):
    """
    Tâche asynchrone: Synchronise les horaires vers le terminal
    
    Args:
        terminal_id: ID du terminal
        schedule_id: ID de l'horaire spécifique (None = tous)
    """
    from .models import Terminal, TerminalSchedule
    from .services.schedule_manager import ScheduleManager
    
    try:
        logger.info(f"🔄 Synchronisation horaires vers terminal {terminal_id}")
        
        terminal = Terminal.objects.get(id=terminal_id)
        
        if schedule_id:
            schedule = TerminalSchedule.objects.get(id=schedule_id)
            success, error = async_to_sync(
                ScheduleManager.sync_schedule_to_terminal
            )(terminal, schedule)
            
            if not success:
                return {
                    'status': 'error',
                    'error': error,
                    'terminal_sn': terminal.sn
                }
            
            return {
                'status': 'success',
                'terminal_sn': terminal.sn,
                'synced_schedules': 1,
                'timestamp': timezone.now().isoformat()
            }
        else:
            success_count, failed_count = async_to_sync(
                ScheduleManager.sync_all_schedules_to_terminal
            )(terminal)
            
            return {
                'status': 'success',
                'terminal_sn': terminal.sn,
                'synced_schedules': success_count,
                'failed_schedules': failed_count,
                'timestamp': timezone.now().isoformat()
            }
        
    except Terminal.DoesNotExist:
        error = f"Terminal {terminal_id} introuvable"
        logger.error(error)
        return {'status': 'error', 'error': error}
        
    except TerminalSchedule.DoesNotExist:
        error = f"Horaire {schedule_id} introuvable"
        logger.error(error)
        return {'status': 'error', 'error': error}
        
    except Exception as e:
        logger.exception(f"Exception sync horaires: {e}")
        return {'status': 'error', 'error': str(e)}

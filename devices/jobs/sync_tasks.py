"""
Sync Tasks - Tâches Celery pour la synchronisation

Tâches planifiées pour:
- Envoi automatique des pointages vers services tiers
- Retry des pointages échoués
- Synchronisation des utilisateurs
"""

import logging
from typing import Dict, Any, Optional

from celery import shared_task
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name='devices.sync_pending_attendance',
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def sync_pending_attendance(
    self,
    config_id: int,
    terminal_id: int = None,
    batch_size: int = 100
) -> Dict[str, Any]:
    """
    Synchronise les pointages en attente vers un service tiers.
    
    Args:
        config_id: ID de la configuration du service tiers
        terminal_id: ID du terminal (optionnel)
        batch_size: Taille des batches
        
    Returns:
        Résultat de la synchronisation
    """
    from ..services.attendance_sync_service import AttendanceSyncManager
    
    logger.info(f"Tâche sync_pending_attendance démarrée - config_id={config_id}")
    
    try:
        result = async_to_sync(AttendanceSyncManager.sync_config_attendance)(
            config_id=config_id,
            terminal_id=terminal_id,
            batch_size=batch_size
        )
        
        logger.info(
            f"Synchronisation terminée: {result.sent} envoyés, "
            f"{result.failed} échoués"
        )
        
        return result.to_dict()
        
    except Exception as e:
        logger.exception(f"Erreur sync_pending_attendance: {e}")
        raise


@shared_task(
    bind=True,
    name='devices.retry_failed_attendance',
    max_retries=2,
    default_retry_delay=300,
)
def retry_failed_attendance(self, config_id: int = None) -> Dict[str, Any]:
    """
    Retente l'envoi des pointages échoués.
    
    Args:
        config_id: ID de la configuration (optionnel, sinon toutes)
        
    Returns:
        Résultat du retry
    """
    from ..services.attendance_sync_service import AttendanceSyncService, AttendanceSyncManager
    from ..models import ThirdPartyConfig
    
    logger.info(f"Tâche retry_failed_attendance démarrée - config_id={config_id}")
    
    try:
        if config_id:
            config = ThirdPartyConfig.objects.get(id=config_id)
            service = AttendanceSyncService(config)
            result = async_to_sync(service.retry_failed_attendance)()
            return {config.name: result.to_dict()}
        else:
            configs = ThirdPartyConfig.objects.filter(
                is_active=True,
                attendance_endpoint__gt=''
            )
            
            results = {}
            for config in configs:
                service = AttendanceSyncService(config)
                result = async_to_sync(service.retry_failed_attendance)()
                results[config.name] = result.to_dict()
            
            return results
            
    except Exception as e:
        logger.exception(f"Erreur retry_failed_attendance: {e}")
        raise


@shared_task(
    bind=True,
    name='devices.sync_users_from_third_party',
    max_retries=3,
    default_retry_delay=120,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def sync_users_from_third_party(
    self,
    terminal_id: int,
    config_id: int,
    **fetch_params
) -> Dict[str, Any]:
    """
    Synchronise les utilisateurs depuis un service tiers vers un terminal.
    
    Args:
        terminal_id: ID du terminal
        config_id: ID de la configuration du service tiers
        **fetch_params: Paramètres pour la requête
        
    Returns:
        Résultat de la synchronisation
    """
    from ..services.user_sync_service import UserSyncManager
    
    logger.info(
        f"Tâche sync_users_from_third_party démarrée - "
        f"terminal_id={terminal_id}, config_id={config_id}"
    )
    
    try:
        result = async_to_sync(UserSyncManager.sync_terminal_users)(
            terminal_id=terminal_id,
            config_id=config_id,
            **fetch_params
        )
        
        logger.info(
            f"Synchronisation utilisateurs terminée: {result.created} créés, "
            f"{result.updated} mis à jour"
        )
        
        return result.to_dict()
        
    except Exception as e:
        logger.exception(f"Erreur sync_users_from_third_party: {e}")
        raise


@shared_task(
    name='devices.sync_all_configs_attendance',
)
def sync_all_configs_attendance() -> Dict[str, Any]:
    """
    Synchronise les pointages pour toutes les configurations actives.
    
    Cette tâche est destinée à être exécutée périodiquement (cron).
    """
    from ..services.attendance_sync_service import AttendanceSyncManager
    
    logger.info("Tâche sync_all_configs_attendance démarrée")
    
    try:
        results = async_to_sync(AttendanceSyncManager.sync_all_pending)()
        
        total_sent = sum(r.sent for r in results.values())
        total_failed = sum(r.failed for r in results.values())
        
        logger.info(
            f"Synchronisation globale terminée: {total_sent} envoyés, "
            f"{total_failed} échoués sur {len(results)} configurations"
        )
        
        return {
            name: result.to_dict() 
            for name, result in results.items()
        }
        
    except Exception as e:
        logger.exception(f"Erreur sync_all_configs_attendance: {e}")
        raise


@shared_task(
    name='devices.cleanup_dead_letter_logs',
)
def cleanup_dead_letter_logs(days_old: int = 30) -> Dict[str, Any]:
    """
    Nettoie les pointages en échec permanent (dead-letter) anciens.
    
    Args:
        days_old: Âge minimum en jours pour suppression
        
    Returns:
        Nombre de logs archivés/supprimés
    """
    from datetime import timedelta
    from django.utils import timezone
    from ..models import AttendanceLog
    
    logger.info(f"Tâche cleanup_dead_letter_logs démarrée - days_old={days_old}")
    
    try:
        cutoff_date = timezone.now() - timedelta(days=days_old)
        
        old_failed_logs = AttendanceLog.objects.filter(
            sync_status='failed',
            time__lt=cutoff_date
        )
        
        count = old_failed_logs.count()
        
        if count > 0:
            old_failed_logs.delete()
            logger.info(f"Supprimé {count} pointages échoués anciens")
        
        return {
            'deleted': count,
            'cutoff_date': cutoff_date.isoformat(),
        }
        
    except Exception as e:
        logger.exception(f"Erreur cleanup_dead_letter_logs: {e}")
        raise


@shared_task(
    name='devices.sync_users_to_terminal',
)
def sync_users_to_terminal(terminal_id: int) -> Dict[str, Any]:
    """
    Charge les utilisateurs en attente vers un terminal physique.
    
    Cette tâche envoie les commandes setuserinfo au terminal
    pour les utilisateurs avec sync_status='pending_sync'.
    """
    from ..models import Terminal, BiometricUser
    from ..services.user_sync_service import UserSyncService
    from ..protocol import CommandBuilder
    from ..core.device_manager import DeviceManager
    
    logger.info(f"Tâche sync_users_to_terminal démarrée - terminal_id={terminal_id}")
    
    try:
        terminal = Terminal.objects.get(id=terminal_id)
        
        users_to_sync = BiometricUser.objects.filter(
            terminal=terminal,
            sync_status='pending_sync'
        )
        
        synced_ids = []
        failed_ids = []
        
        device_manager = DeviceManager.get_instance()
        
        for user in users_to_sync:
            payload = CommandBuilder.setuserinfo(
                enrollid=user.enrollid,
                name=user.name,
                admin=user.admin,
                enable=1 if user.is_enabled else 0,
                weekzone=user.weekzone,
                group=user.group,
            )
            
            sent = async_to_sync(device_manager.send_to_device)(
                terminal.sn, 
                payload
            )
            
            if sent:
                synced_ids.append(user.id)
            else:
                failed_ids.append(user.id)
        
        if synced_ids:
            BiometricUser.objects.filter(id__in=synced_ids).update(
                sync_status='synced_to_terminal',
                last_synced_at=timezone.now()
            )
        
        logger.info(
            f"Synchronisation terminal terminée: {len(synced_ids)} réussis, "
            f"{len(failed_ids)} échoués"
        )
        
        return {
            'terminal_sn': terminal.sn,
            'synced': len(synced_ids),
            'failed': len(failed_ids),
            'synced_ids': synced_ids,
            'failed_ids': failed_ids,
        }
        
    except Exception as e:
        logger.exception(f"Erreur sync_users_to_terminal: {e}")
        raise


@shared_task(
    bind=True,
    name='devices.auto_sync_all_attendance',
    max_retries=2,
    default_retry_delay=120,
)
def auto_sync_all_attendance(self) -> Dict[str, Any]:
    """
    Tâche cron pour synchroniser automatiquement tous les pointages en attente.
    
    Cette tâche est exécutée périodiquement (toutes les 5-10 minutes) pour
    envoyer automatiquement les pointages vers tous les services tiers actifs.
    
    Returns:
        Résultats de synchronisation par configuration
    """
    from ..services.attendance_sync_service import AttendanceSyncManager
    
    logger.info("Tâche auto_sync_all_attendance démarrée (cron)")
    
    try:
        results = async_to_sync(AttendanceSyncManager.sync_all_pending)()
        
        total_sent = sum(r.sent for r in results.values())
        total_failed = sum(r.failed for r in results.values())
        
        logger.info(
            f"Auto-sync terminée: {total_sent} pointages envoyés, "
            f"{total_failed} échoués sur {len(results)} configurations"
        )
        
        return {
            config_name: result.to_dict()
            for config_name, result in results.items()
        }
        
    except Exception as e:
        logger.exception(f"Erreur auto_sync_all_attendance: {e}")
        raise

"""
Service de gestion des logs de pointage
Optimisé pour le traitement batch et haute performance
"""

import asyncio
import logging
import time
from typing import List, Optional, Tuple

from asgiref.sync import sync_to_async
from django.db import transaction
from django.utils import timezone

from ..models import AttendanceLog, BiometricUser, Terminal
from ..protocol import LogRecord, SendLogMessage, TM20Parser
from ..core.events import EventBus, EventType
from ..core.metrics import MetricsCollector

logger = logging.getLogger('devices.services')


class AttendanceService:
    """
    Service de traitement des logs de pointage
    
    Fonctionnalités :
    - Traitement batch des logs
    - Vérification d'accès
    - Émission d'événements temps réel
    - Métriques de performance
    """
    
    def __init__(self):
        self._event_bus = EventBus.get_instance()
        self._metrics = MetricsCollector.get_instance()
        self._batch_queue: asyncio.Queue = asyncio.Queue()
        self._batch_size = 50
        self._batch_timeout = 2.0  # seconds
    
    async def process_logs(
        self,
        terminal: Terminal,
        log_msg: SendLogMessage
    ) -> Tuple[int, bool]:
        """
        Traite les logs de pointage reçus
        Retourne (nombre_traités, access_granted)
        """
        start_time = time.perf_counter()
        
        processed, access_granted = await self._process_logs_sync(
            terminal, log_msg
        )
        
        # Métriques
        elapsed = time.perf_counter() - start_time
        self._metrics.record_log(terminal.sn, processed)
        self._metrics.record_latency('db_write', elapsed)
        
        # Événement
        await self._event_bus.emit(
            EventType.ATTENDANCE_LOG_RECEIVED,
            {
                'sn': terminal.sn,
                'count': processed,
                'logindex': log_msg.logindex,
                'latency_ms': round(elapsed * 1000, 2),
            },
            source='AttendanceService'
        )
        
        return processed, access_granted
    
    @sync_to_async
    def _process_logs_sync(
        self,
        terminal: Terminal,
        log_msg: SendLogMessage
    ) -> Tuple[int, bool]:
        """Traitement synchrone des logs (dans thread pool)"""
        processed = 0
        access_granted = True
        
        with transaction.atomic():
            logs_to_create = []
            
            for record in log_msg.records:
                try:
                    log = self._prepare_log(terminal, record)
                    logs_to_create.append(log)
                    
                    # Vérification d'accès pour le dernier log
                    if record.enrollid > 0:
                        access_granted = self._check_access(
                            terminal, record.enrollid
                        )
                except Exception as e:
                    logger.error(f"Error preparing log: {e}")
                    continue
            
            # Insertion batch
            if logs_to_create:
                AttendanceLog.objects.bulk_create(logs_to_create)
                processed = len(logs_to_create)
        
        logger.info(f"[{terminal.sn}] {processed}/{len(log_msg.records)} logs processed")
        return processed, access_granted
    
    def _prepare_log(self, terminal: Terminal, record: LogRecord) -> AttendanceLog:
        """Prépare un objet AttendanceLog sans l'insérer"""
        log_time = TM20Parser.parse_datetime(record.time)
        if not log_time:
            log_time = timezone.now()
        
        # Recherche de l'utilisateur
        user = None
        if record.enrollid > 0:
            user = BiometricUser.objects.filter(
                terminal=terminal,
                enrollid=record.enrollid
            ).first()
        
        # Détermination automatique du statut entrée/sortie
        # Si le terminal envoie déjà un inout valide (0 ou 1), on le garde
        # Sinon, on détermine automatiquement basé sur le dernier pointage
        inout_status = record.inout
        
        if record.enrollid > 0:
            # Déterminer automatiquement l'entrée/sortie basé sur l'historique
            inout_status = AttendanceLog.determine_inout_status(
                enrollid=record.enrollid,
                terminal=terminal,
                current_time=log_time
            )
            
            logger.debug(
                f"[{terminal.sn}] User {record.enrollid}: "
                f"Auto-determined inout={inout_status} "
                f"({'Entrée' if inout_status == 0 else 'Sortie'})"
            )
        
        return AttendanceLog(
            terminal=terminal,
            user=user,
            enrollid=record.enrollid,
            time=log_time,
            mode=record.mode,
            inout=inout_status,  # Utilise le statut déterminé automatiquement
            event=record.event,
            temperature=record.temp,
            verifymode=record.verifymode,
            image=record.image or '',
            raw_payload=record.to_dict(),
        )
    
    def _check_access(self, terminal: Terminal, enrollid: int) -> bool:
        """Vérifie si un utilisateur a accès"""
        try:
            user = BiometricUser.objects.get(
                terminal=terminal,
                enrollid=enrollid
            )
            
            if not user.is_enabled:
                return False
            
            now = timezone.now()
            if user.starttime and now < user.starttime:
                return False
            if user.endtime and now > user.endtime:
                return False
            
            return True
            
        except BiometricUser.DoesNotExist:
            # Utilisateur inconnu = accès autorisé par défaut
            return True
    
    @sync_to_async
    def get_recent_logs(
        self,
        terminal: Terminal = None,
        limit: int = 100
    ) -> List[dict]:
        """Récupère les logs récents pour le dashboard"""
        queryset = AttendanceLog.objects.all()
        
        if terminal:
            queryset = queryset.filter(terminal=terminal)
        
        queryset = queryset.select_related('terminal', 'user')[:limit]
        
        return [
            {
                'id': log.id,
                'sn': log.terminal.sn,
                'enrollid': log.enrollid,
                'user_name': log.user.name if log.user else None,
                'time': log.time.isoformat(),
                'mode': log.get_mode_display(),
                'inout': log.get_inout_display(),
                'access_granted': log.access_granted,
            }
            for log in queryset
        ]
    
    @sync_to_async
    def get_logs_count(self, terminal: Terminal = None) -> dict:
        """Compte les logs pour les stats"""
        from django.db.models import Count
        from django.db.models.functions import TruncDate
        
        queryset = AttendanceLog.objects.all()
        if terminal:
            queryset = queryset.filter(terminal=terminal)
        
        total = queryset.count()
        today = queryset.filter(
            time__date=timezone.now().date()
        ).count()
        
        return {
            'total': total,
            'today': today,
        }


# Instance par défaut
attendance_service = AttendanceService()

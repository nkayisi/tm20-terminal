"""
Attendance Sync Service - Service de synchronisation des pointages

Gère l'envoi des pointages vers les services tiers avec:
- Gestion des statuts (pending, sent, failed)
- Retry automatique avec backoff exponentiel
- Dead-letter queue pour les échecs permanents
- Batch processing pour les gros volumes
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from asgiref.sync import sync_to_async

from ..models import Terminal, AttendanceLog, ThirdPartyConfig, TerminalThirdPartyMapping
from ..integrations import AdapterFactory, AdapterResponse, AttendanceData
from ..protocol import to_terminal_time

logger = logging.getLogger(__name__)


@dataclass
class AttendanceSyncResult:
    """Résultat d'une opération de synchronisation de pointages"""
    success: bool
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)
    failed_log_ids: List[int] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def total_processed(self) -> int:
        return self.sent + self.failed + self.skipped
    
    def to_dict(self) -> dict:
        return {
            'success': self.success,
            'sent': self.sent,
            'failed': self.failed,
            'skipped': self.skipped,
            'total_processed': self.total_processed,
            'errors': self.errors,
            'failed_log_ids': self.failed_log_ids,
            'details': self.details,
        }


class AttendanceSyncService:
    """
    Service de synchronisation des pointages vers les services tiers.
    
    Responsabilités:
    - Récupérer les pointages en attente (pending)
    - Les envoyer par batch vers le service tiers
    - Mettre à jour les statuts (sent/failed)
    - Gérer les retry avec backoff exponentiel
    """
    
    DEFAULT_BATCH_SIZE = 100
    MAX_RETRY_ATTEMPTS = 5
    RETRY_BACKOFF_MINUTES = [1, 5, 15, 60, 240]
    
    def __init__(self, config: ThirdPartyConfig, terminal: Terminal = None):
        self.config = config
        self.terminal = terminal
        self.adapter = AdapterFactory.create(config)
        self.logger = logging.getLogger(f"{__name__}.{config.name}")
        # Pointages ecartes faute de matricule pendant la passe en cours. Ils
        # restent `pending` en base : sans cette memoire, la boucle de
        # `sync_pending_attendance` les relirait indefiniment.
        self._skipped_ids: set = set()
    
    async def sync_pending_attendance(
        self,
        batch_size: int = None,
        max_batches: int = None
    ) -> AttendanceSyncResult:
        """
        Synchronise les pointages en attente vers le service tiers.
        
        Args:
            batch_size: Taille des batches (défaut: 100)
            max_batches: Nombre max de batches à traiter (None = tous)
            
        Returns:
            AttendanceSyncResult avec le détail des opérations
        """
        batch_size = batch_size or self.DEFAULT_BATCH_SIZE
        # Les pointages ecartes a la passe precedente ont pu recevoir leur
        # matricule depuis : on leur redonne leur chance a chaque passe.
        self._skipped_ids.clear()

        total_sent = 0
        total_failed = 0
        total_skipped = 0
        all_errors = []
        all_failed_ids = []
        batches_processed = 0
        
        self.logger.info(f"Début synchronisation pointages pour {self.config.name}")
        
        try:
            while True:
                if max_batches and batches_processed >= max_batches:
                    break
                
                logs = await self._get_pending_logs(batch_size)
                
                if not logs:
                    break
                
                result = await self._send_batch(logs)
                
                total_sent += result.sent
                total_failed += result.failed
                total_skipped += result.skipped
                all_errors.extend(result.errors)
                all_failed_ids.extend(result.failed_log_ids)
                batches_processed += 1
                
                self.logger.info(
                    f"Batch {batches_processed}: {result.sent} envoyés, "
                    f"{result.failed} échoués"
                )
            
            await self._update_mapping_timestamp()
            
            return AttendanceSyncResult(
                success=total_failed == 0,
                sent=total_sent,
                failed=total_failed,
                skipped=total_skipped,
                errors=all_errors,
                failed_log_ids=all_failed_ids,
                details={
                    'config_name': self.config.name,
                    'terminal_sn': self.terminal.sn if self.terminal else 'all',
                    'batches_processed': batches_processed,
                    'timestamp': timezone.now().isoformat(),
                }
            )
            
        except Exception as e:
            self.logger.exception(f"Erreur lors de la synchronisation: {e}")
            return AttendanceSyncResult(
                success=False,
                sent=total_sent,
                failed=total_failed,
                errors=[str(e)] + all_errors,
                details={'exception': type(e).__name__}
            )
        finally:
            await self.adapter.close()
    
    @sync_to_async
    def _get_pending_logs(self, limit: int) -> List[AttendanceLog]:
        """Récupère les pointages en attente de synchronisation"""
        queryset = AttendanceLog.objects.filter(
            sync_status='pending'
        ).select_related('terminal', 'user')
        
        if self.terminal:
            queryset = queryset.filter(terminal=self.terminal)
        else:
            terminal_ids = TerminalThirdPartyMapping.objects.filter(
                config=self.config,
                is_active=True,
                sync_attendance=True
            ).values_list('terminal_id', flat=True)
            queryset = queryset.filter(terminal_id__in=terminal_ids)
        
        queryset = queryset.filter(
            Q(sync_attempts=0) |
            Q(sync_attempts__lt=self.MAX_RETRY_ATTEMPTS)
        )

        if self._skipped_ids:
            queryset = queryset.exclude(id__in=self._skipped_ids)

        return list(queryset.order_by('time')[:limit])
    
    @staticmethod
    def _is_matchable(log: AttendanceLog) -> bool:
        """Le recepteur peut-il rattacher ce pointage a quelqu'un ?

        Il apparie sur le matricule, c'est-a-dire `external_user_id`. Sans lui
        il n'a rien a quoi rattacher la ligne : `enrollid` est un compteur
        interne au terminal, il se recycle, et deux terminaux donnent le meme a
        deux personnes differentes. Le couple `terminal_sn` + `enrollid`
        identifie la ligne, pas l'agent.

        Les evenements de porte (`enrollid == 0`) echappent a la regle : aucun
        agent n'est en cause, aucun matricule ne leur viendra jamais, et les
        retenir ici les laisserait `pending` pour toujours.
        """
        if log.enrollid == 0:
            return True
        return bool(log.user and log.user.external_id)

    async def _send_batch(self, logs: List[AttendanceLog]) -> AttendanceSyncResult:
        """Envoie un batch de pointages vers le service tiers.

        Les pointages sans matricule sont ecartes avant l'envoi plutot
        qu'emis : le recepteur repondrait `200` sans rien avoir enregistre, et
        le serveur les marquerait `sent`. Ils compteraient pour synchronises
        d'un cote, n'existeraient pas de l'autre -- la perte silencieuse exacte
        que le reste de cette chaine s'emploie a eviter.

        Ils restent `pending`, et c'est le point : le jour ou l'`external_id`
        est renseigne sur l'agent, la passe suivante les emporte sans
        intervention. `skipped` les compte pour qu'ils soient visibles entre
        temps.
        """
        sendable, unmatchable = [], []
        for log in logs:
            (sendable if self._is_matchable(log) else unmatchable).append(log)

        if unmatchable:
            self._skipped_ids.update(log.id for log in unmatchable)
            agents = sorted({
                f"{log.terminal.sn}#{log.enrollid}" for log in unmatchable
            })
            self.logger.warning(
                f"{len(unmatchable)} pointage(s) ecarte(s), matricule "
                f"(external_id) absent -- non rattachables cote "
                f"{self.config.name} : {', '.join(agents)}"
            )

        skipped = AttendanceSyncResult(
            success=True,
            skipped=len(unmatchable),
            details={'unmatchable_log_ids': [log.id for log in unmatchable]},
        )

        if not sendable:
            return skipped

        logs = sendable
        attendance_data = [self._log_to_attendance_data(log) for log in logs]

        try:
            response = await self.adapter.send_attendance(attendance_data)
            
            if response.success:
                await self._mark_logs_sent([log.id for log in logs])
                return AttendanceSyncResult(
                    success=True,
                    sent=len(logs),
                    skipped=skipped.skipped,
                    details={'response': response.metadata, **skipped.details}
                )
            else:
                await self._mark_logs_failed(
                    [log.id for log in logs],
                    response.message
                )
                return AttendanceSyncResult(
                    success=False,
                    failed=len(logs),
                    skipped=skipped.skipped,
                    errors=[response.message],
                    failed_log_ids=[log.id for log in logs],
                    details=skipped.details
                )

        except Exception as e:
            self.logger.error(f"Erreur envoi batch: {e}")
            await self._mark_logs_failed([log.id for log in logs], str(e))
            return AttendanceSyncResult(
                success=False,
                failed=len(logs),
                skipped=skipped.skipped,
                errors=[str(e)],
                failed_log_ids=[log.id for log in logs],
                details=skipped.details
            )
    
    def _log_to_attendance_data(self, log: AttendanceLog) -> AttendanceData:
        """Convertit un AttendanceLog en AttendanceData pour l'adapter"""
        return AttendanceData(
            log_id=log.id,
            terminal_sn=log.terminal.sn,
            enrollid=log.enrollid,
            external_user_id=log.user.external_id if log.user else None,
            user_name=log.user.name if log.user else f"User#{log.enrollid}",
            # Heure murale du terminal, offset inclus : le recepteur attend
            # l'heure affichee sur l'ecran au moment du pointage. La base
            # restitue de l'UTC, l'envoyer tel quel decalerait chaque pointage
            # de l'offset du site pour tout recepteur qui ignore le suffixe.
            timestamp=to_terminal_time(log.time).isoformat(),
            mode=log.mode,
            inout=log.inout,
            event=log.event,
            temperature=float(log.temperature) if log.temperature else None,
            access_granted=log.access_granted,
            metadata=self._metadata_for(log),
        )

    @staticmethod
    def _metadata_for(log: AttendanceLog) -> Dict[str, Any]:
        """Trame brute du terminal, avec `inout` aligne sur le sens derive.

        `raw_payload` conserve ce que le terminal a emis, et le terminal emet
        toujours `inout: 0` : la spec reserve ce champ au couple lecteur
        maitre / lecteur esclave (section 6.1-1), c'est le serveur qui tient le
        sens de passage par alternance journaliere. Recopie telle quelle, la
        trame contredisait donc la racine des qu'il s'agissait d'une sortie --
        meme pointage, deux valeurs opposees selon le niveau lu. Un recepteur
        qui descend dans `metadata` (par habitude, ou parce que la racine lui
        manque un jour) comptait la sortie comme une entree, sans rien pour le
        signaler.

        Les deux niveaux portent desormais la valeur derivee. L'alignement se
        fait ici plutot qu'a l'insertion : il couvre ainsi les pointages deja
        en base, dont le `raw_payload` fige un 0 que rien ne reecrira.

        `metadata['time']` reste l'horodatage brut du terminal, sans fuseau :
        c'est `timestamp` a la racine qui porte l'heure murale avec offset.
        """
        metadata = dict(log.raw_payload or {})
        metadata['inout'] = log.inout
        return metadata
    
    @sync_to_async
    def _mark_logs_sent(self, log_ids: List[int]):
        """Marque les pointages comme envoyés"""
        AttendanceLog.objects.filter(id__in=log_ids).update(
            sync_status='sent',
            synced_at=timezone.now(),
            sync_error=''
        )
    
    @sync_to_async
    def _mark_logs_failed(self, log_ids: List[int], error_message: str):
        """Marque les pointages comme échoués et incrémente le compteur de retry"""
        from django.db.models import F
        
        AttendanceLog.objects.filter(id__in=log_ids).update(
            sync_attempts=F('sync_attempts') + 1,
            sync_error=error_message[:500]
        )
        
        AttendanceLog.objects.filter(
            id__in=log_ids,
            sync_attempts__gte=self.MAX_RETRY_ATTEMPTS
        ).update(sync_status='failed')
    
    @sync_to_async
    def _update_mapping_timestamp(self):
        """Met à jour le timestamp de dernière synchronisation"""
        filter_kwargs = {'config': self.config, 'is_active': True}
        if self.terminal:
            filter_kwargs['terminal'] = self.terminal
        
        TerminalThirdPartyMapping.objects.filter(**filter_kwargs).update(
            last_attendance_sync=timezone.now()
        )
    
    async def retry_failed_attendance(self) -> AttendanceSyncResult:
        """
        Retente l'envoi des pointages échoués.
        
        Ne retente que les pointages qui n'ont pas atteint le max de retry
        et dont le délai de backoff est écoulé.
        """
        logs = await self._get_retryable_logs()
        
        if not logs:
            return AttendanceSyncResult(
                success=True,
                skipped=0,
                details={'message': 'Aucun pointage à retenter'}
            )
        
        self.logger.info(f"Retry de {len(logs)} pointages échoués")
        return await self._send_batch(logs)
    
    @sync_to_async
    def _get_retryable_logs(self) -> List[AttendanceLog]:
        """Récupère les pointages éligibles pour retry"""
        now = timezone.now()
        logs = []
        
        queryset = AttendanceLog.objects.filter(
            sync_status='pending',
            sync_attempts__gt=0,
            sync_attempts__lt=self.MAX_RETRY_ATTEMPTS
        ).select_related('terminal', 'user')
        
        if self.terminal:
            queryset = queryset.filter(terminal=self.terminal)
        
        for log in queryset:
            backoff_index = min(log.sync_attempts - 1, len(self.RETRY_BACKOFF_MINUTES) - 1)
            backoff_minutes = self.RETRY_BACKOFF_MINUTES[backoff_index]
            
            if log.updated_at + timedelta(minutes=backoff_minutes) <= now:
                logs.append(log)
        
        return logs[:self.DEFAULT_BATCH_SIZE]


class AttendanceSyncManager:
    """
    Manager pour orchestrer la synchronisation des pointages.
    
    Fournit des méthodes de haut niveau pour:
    - Synchroniser les pointages d'une configuration
    - Synchroniser tous les pointages en attente
    - Obtenir les statistiques de synchronisation
    """
    
    @staticmethod
    async def sync_config_attendance(
        config_id: int,
        terminal_id: int = None,
        batch_size: int = None
    ) -> AttendanceSyncResult:
        """
        Synchronise les pointages pour une configuration.
        
        Args:
            config_id: ID de la configuration du service tiers
            terminal_id: ID du terminal (optionnel, sinon tous les terminaux mappés)
            batch_size: Taille des batches
        """
        config = await sync_to_async(ThirdPartyConfig.objects.get)(id=config_id)
        terminal = None
        if terminal_id:
            terminal = await sync_to_async(Terminal.objects.get)(id=terminal_id)
        
        service = AttendanceSyncService(config, terminal)
        return await service.sync_pending_attendance(batch_size=batch_size)
    
    @staticmethod
    async def sync_all_pending() -> Dict[str, AttendanceSyncResult]:
        """
        Synchronise tous les pointages en attente pour toutes les configurations actives.
        
        Returns:
            Dict mapping config_name -> AttendanceSyncResult
        """
        results = {}
        
        @sync_to_async
        def get_active_configs():
            return list(
                ThirdPartyConfig.objects.filter(
                    is_active=True,
                    attendance_endpoint__gt=''
                )
            )
        
        configs = await get_active_configs()
        
        for config in configs:
            service = AttendanceSyncService(config)
            result = await service.sync_pending_attendance()
            results[config.name] = result
        
        return results
    
    @staticmethod
    @sync_to_async
    def get_sync_statistics(
        terminal_id: int = None,
        config_id: int = None
    ) -> Dict[str, Any]:
        """Retourne les statistiques de synchronisation des pointages"""
        queryset = AttendanceLog.objects.all()
        
        if terminal_id:
            queryset = queryset.filter(terminal_id=terminal_id)
        
        if config_id:
            terminal_ids = TerminalThirdPartyMapping.objects.filter(
                config_id=config_id,
                is_active=True
            ).values_list('terminal_id', flat=True)
            queryset = queryset.filter(terminal_id__in=terminal_ids)
        
        total = queryset.count()
        pending = queryset.filter(sync_status='pending').count()
        sent = queryset.filter(sync_status='sent').count()
        failed = queryset.filter(sync_status='failed').count()
        
        pending_with_retries = queryset.filter(
            sync_status='pending',
            sync_attempts__gt=0
        ).count()
        
        return {
            'total': total,
            'pending': pending,
            'pending_first_attempt': pending - pending_with_retries,
            'pending_retry': pending_with_retries,
            'sent': sent,
            'failed': failed,
            'success_rate': round((sent / total * 100), 2) if total > 0 else 0,
        }
    
    @staticmethod
    @sync_to_async
    def get_dead_letter_logs(limit: int = 100) -> List[Dict[str, Any]]:
        """
        Récupère les pointages en échec permanent (dead-letter).
        
        Ce sont les pointages qui ont atteint le max de retry.
        """
        logs = AttendanceLog.objects.filter(
            sync_status='failed'
        ).select_related('terminal', 'user').order_by('-time')[:limit]
        
        return [
            {
                'id': log.id,
                'terminal_sn': log.terminal.sn,
                'enrollid': log.enrollid,
                'user_name': log.user.name if log.user else None,
                'time': timezone.localtime(log.time).isoformat(),
                'sync_attempts': log.sync_attempts,
                'sync_error': log.sync_error,
            }
            for log in logs
        ]
    
    @staticmethod
    @sync_to_async
    def reset_failed_logs(log_ids: List[int] = None, all_failed: bool = False) -> int:
        """
        Réinitialise les pointages échoués pour permettre un nouveau retry.
        
        Args:
            log_ids: Liste d'IDs spécifiques à réinitialiser
            all_failed: Si True, réinitialise tous les pointages failed
            
        Returns:
            Nombre de pointages réinitialisés
        """
        if all_failed:
            queryset = AttendanceLog.objects.filter(sync_status='failed')
        elif log_ids:
            queryset = AttendanceLog.objects.filter(id__in=log_ids, sync_status='failed')
        else:
            return 0
        
        count = queryset.update(
            sync_status='pending',
            sync_attempts=0,
            sync_error=''
        )
        
        return count

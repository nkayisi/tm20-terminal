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
from ..protocol import LogRecord, SendLogMessage, TM20Parser, make_terminal_aware
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
        """Traitement synchrone des logs (dans thread pool).

        Un seul aller-retour base pour les utilisateurs du lot et pour les
        derniers pointages connus : le volume d'un `sendlog` monte a 40-50
        enregistrements (doc section 1.5), une requete par enregistrement
        n'est pas tenable.
        """
        records = [r for r in log_msg.records if r is not None]
        if not records:
            return 0, True

        # Les enregistrements d'un meme lot doivent etre traites dans l'ordre
        # chronologique : l'alternance entree/sortie en depend.
        prepared = []
        for record in records:
            log_time = make_terminal_aware(TM20Parser.parse_datetime(record.time))
            if not log_time:
                logger.warning(
                    f"[{terminal.sn}] Horodatage illisible ({record.time!r}), "
                    f"remplace par l'heure serveur"
                )
                log_time = timezone.now()
            prepared.append((log_time, record))
        prepared.sort(key=lambda item: item[0])

        # Ecarter les retransmissions AVANT de calculer l'alternance : un lot
        # renvoye ne doit pas faire avancer le sens de passage.
        prepared, duplicates = self._drop_already_stored(terminal, prepared)
        if not prepared:
            logger.info(
                f"[{terminal.sn}] 0/{len(records)} pointages enregistres "
                f"({duplicates} doublon(s) ecarte(s))"
            )
            return 0, True

        enrollids = {r.enrollid for _, r in prepared if r.enrollid > 0}
        users = self._get_users(terminal, enrollids)

        # Horodatage du premier pointage du lot pour chaque utilisateur : il
        # sert d'ancre a la recherche du sens de passage precedent. `prepared`
        # etant deja trie, la premiere occurrence est la plus ancienne.
        first_seen = {}
        for log_time, record in prepared:
            if record.enrollid > 0:
                first_seen.setdefault(record.enrollid, log_time)

        last_inout = self._get_last_inout(terminal, enrollids, first_seen)

        logs_to_create = []
        access_granted = True

        for log_time, record in prepared:
            try:
                log = self._prepare_log(
                    terminal, record, log_time, users, last_inout,
                    log_index=log_msg.logindex or None,
                )
            except Exception as e:
                logger.error(f"[{terminal.sn}] Erreur preparation du log: {e}")
                continue

            logs_to_create.append(log)

            # `access` de la reponse reflete le dernier pointage utilisateur
            # du lot, c'est lui qui commande l'ouverture de la porte.
            if record.enrollid > 0:
                access_granted = log.access_granted

        if not logs_to_create:
            return 0, access_granted

        with transaction.atomic():
            # ignore_conflicts : filet de securite contre la course entre deux
            # envois simultanes du meme lot. La contrainte d'unicite de
            # AttendanceLog rend l'insertion idempotente.
            AttendanceLog.objects.bulk_create(
                logs_to_create, ignore_conflicts=True
            )

        processed = len(logs_to_create)

        logger.info(
            f"[{terminal.sn}] {processed}/{len(records)} pointages enregistres"
            + (f" ({duplicates} doublon(s) ecarte(s))" if duplicates else "")
        )
        return processed, access_granted

    def _drop_already_stored(self, terminal: Terminal, prepared: list) -> tuple:
        """Retire les enregistrements deja en base (retransmissions).

        Un terminal qui n'a pas recu notre reponse renvoie son lot entier. La
        cle naturelle est celle de la contrainte d'unicite de AttendanceLog :
        (terminal, enrollid, time, event).
        """
        if not prepared:
            return [], 0

        existing = set(
            AttendanceLog.objects.filter(
                terminal=terminal,
                enrollid__in={r.enrollid for _, r in prepared},
                time__in={t for t, _ in prepared},
            ).values_list('enrollid', 'time', 'event')
        )
        if not existing:
            return prepared, 0

        kept = [
            (log_time, record)
            for log_time, record in prepared
            if (record.enrollid, log_time, record.event) not in existing
        ]
        return kept, len(prepared) - len(kept)

    def _get_users(self, terminal: Terminal, enrollids: set) -> dict:
        """Charge en une requete les utilisateurs cites dans le lot."""
        if not enrollids:
            return {}
        return {
            user.enrollid: user
            for user in BiometricUser.objects.filter(
                terminal=terminal, enrollid__in=enrollids
            )
        }

    def _get_last_inout(
        self,
        terminal: Terminal,
        enrollids: set,
        first_seen: dict = None,
    ) -> dict:
        """Dernier sens de passage connu par utilisateur (une requete chacun).

        Sert d'amorce a l'alternance entree/sortie. Les enregistrements du lot
        n'etant inseres qu'a la fin, l'etat doit etre tenu en memoire pendant
        la boucle -- sinon tous les pointages d'un meme utilisateur dans un
        meme lot recevraient le meme sens.

        `first_seen` donne, par utilisateur, l'horodatage du premier pointage
        du lot : l'amorce est cherchee STRICTEMENT AVANT lui. Sans cette ancre,
        un lot antidate (backfill `getalllog`/`getnewlog` via
        `ResponseHandler._persist_log_page`) s'amorcait sur un pointage
        POSTERIEUR et inversait toute l'alternance.

        Limite assumee : les lignes deja en base posterieures au lot ne sont
        pas re-derivees. Reecrire l'historique demanderait une reprise globale
        par utilisateur, hors du perimetre de cette correction.
        """
        if not enrollids:
            return {}

        first_seen = first_seen or {}
        last = {}
        for enrollid in enrollids:
            previous = AttendanceLog.get_last_attendance(
                enrollid, terminal, before_time=first_seen.get(enrollid)
            )
            if previous is not None:
                last[enrollid] = previous.inout
        return last

    def _prepare_log(
        self,
        terminal: Terminal,
        record: LogRecord,
        log_time,
        users: dict,
        last_inout: dict,
        log_index: Optional[int] = None,
    ) -> AttendanceLog:
        """Prépare un objet AttendanceLog sans l'insérer"""
        if record.mode not in dict(AttendanceLog.MODE_CHOICES):
            # Doc section 6.1-1 : les tables `mode` de la spec se contredisent.
            # On journalise la valeur brute avant tout mapping.
            logger.info(
                f"[{terminal.sn}] Valeur `mode` inconnue: {record.mode} "
                f"(enrollid={record.enrollid})"
            )

        user = users.get(record.enrollid) if record.enrollid > 0 else None

        if record.enrollid > 0:
            # Alternance entree/sortie : le terminal envoie toujours inout=0,
            # c'est le serveur qui tient le sens de passage.
            previous = last_inout.get(record.enrollid)
            inout_status = 0 if previous is None else (1 if previous == 0 else 0)
            last_inout[record.enrollid] = inout_status
            access_granted = self._check_access(user)
        else:
            # enrollid == 0 : evenement de porte, `inout` est fige a 1 par la
            # spec (section T2) et aucun droit d'acces n'est en jeu.
            inout_status = record.inout
            access_granted = True

        return AttendanceLog(
            terminal=terminal,
            user=user,
            enrollid=record.enrollid,
            time=log_time,
            mode=record.mode,
            inout=inout_status,
            event=record.event,
            temperature=record.temp,
            verifymode=record.verifymode,
            image=record.image or '',
            log_index=log_index,
            access_granted=access_granted,
            raw_payload=record.to_dict(),
        )

    def _check_access(self, user: Optional[BiometricUser]) -> bool:
        """Vérifie si un utilisateur a accès"""
        if user is None:
            # Utilisateur inconnu = accès autorisé par défaut
            return True

        if not user.is_enabled:
            return False

        now = timezone.now()
        if user.starttime and now < user.starttime:
            return False
        if user.endtime and now > user.endtime:
            return False

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

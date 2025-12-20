"""
Services métier pour la gestion des terminaux TM20
"""

import logging
from datetime import datetime
from typing import Any, Optional

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    AttendanceLog,
    BiometricCredential,
    BiometricUser,
    CommandQueue,
    Terminal,
)
from .protocol import (
    LogRecord,
    RegisterMessage,
    SendLogMessage,
    SendUserMessage,
    TM20Protocol,
)

logger = logging.getLogger('devices')


class TerminalService:
    """Service de gestion des terminaux"""
    
    @staticmethod
    @sync_to_async
    def register_terminal(reg_msg: RegisterMessage) -> tuple[Terminal, bool]:
        """
        Enregistre ou met à jour un terminal
        Retourne (terminal, created)
        """
        devinfo = reg_msg.devinfo
        
        defaults = {
            'cpusn': reg_msg.cpusn,
            'last_seen': timezone.now(),
            'is_active': True,
        }
        
        if devinfo:
            defaults.update({
                'model': devinfo.modelname,
                'firmware': devinfo.firmware,
                'mac_address': devinfo.mac,
                'user_capacity': devinfo.usersize,
                'fp_capacity': devinfo.fpsize,
                'card_capacity': devinfo.cardsize,
                'log_capacity': devinfo.logsize,
                'used_users': devinfo.useduser,
                'used_fp': devinfo.usedfp,
                'used_cards': devinfo.usedcard,
                'used_logs': devinfo.usedlog,
                'fp_algo': devinfo.fpalgo,
            })
        
        terminal, created = Terminal.objects.update_or_create(
            sn=reg_msg.sn,
            defaults=defaults
        )
        
        action = "Nouveau terminal enregistré" if created else "Terminal mis à jour"
        logger.info(f"{action}: {terminal.sn} ({terminal.model})")
        
        return terminal, created
    
    @staticmethod
    @sync_to_async
    def get_terminal_by_sn(sn: str) -> Optional[Terminal]:
        """Récupère un terminal par son numéro de série"""
        try:
            return Terminal.objects.get(sn=sn)
        except Terminal.DoesNotExist:
            return None
    
    @staticmethod
    @sync_to_async
    def is_terminal_whitelisted(sn: str) -> bool:
        """Vérifie si un terminal est en liste blanche"""
        if not settings.TM20_SETTINGS.get('REQUIRE_WHITELIST', False):
            return True
        
        try:
            terminal = Terminal.objects.get(sn=sn)
            return terminal.is_whitelisted and terminal.is_active
        except Terminal.DoesNotExist:
            return False
    
    @staticmethod
    @sync_to_async
    def update_terminal_status(sn: str, is_active: bool = True) -> None:
        """Met à jour le statut d'un terminal"""
        Terminal.objects.filter(sn=sn).update(
            is_active=is_active,
            last_seen=timezone.now()
        )
    
    @staticmethod
    @sync_to_async
    def update_last_seen(sn: str) -> None:
        """Met à jour la dernière connexion du terminal"""
        Terminal.objects.filter(sn=sn).update(last_seen=timezone.now())


class AttendanceService:
    """Service de gestion des logs de pointage"""
    
    @staticmethod
    @sync_to_async
    def process_logs(terminal: Terminal, log_msg: SendLogMessage) -> tuple[int, bool]:
        """
        Traite les logs de pointage reçus
        Retourne (nombre_traités, access_granted)
        """
        processed = 0
        access_granted = True
        
        with transaction.atomic():
            for log_record in log_msg.record:
                try:
                    log = AttendanceService._create_log_sync(terminal, log_record)
                    processed += 1
                    
                    # Vérification d'accès basique
                    if log_record.enrollid > 0:
                        access_granted = AttendanceService._check_access_sync(
                            terminal, log_record.enrollid
                        )
                    
                except Exception as e:
                    logger.error(f"Erreur traitement log: {e}")
                    continue
        
        logger.info(f"[{terminal.sn}] {processed}/{len(log_msg.record)} logs traités")
        return processed, access_granted
    
    @staticmethod
    def _create_log_sync(terminal: Terminal, record: LogRecord) -> AttendanceLog:
        """Crée un log de pointage (sync)"""
        log_time = TM20Protocol.parse_datetime(record.time)
        if not log_time:
            log_time = timezone.now()
        
        # Chercher l'utilisateur associé
        user = None
        if record.enrollid > 0:
            user = BiometricUser.objects.filter(
                terminal=terminal,
                enrollid=record.enrollid
            ).first()
        
        return AttendanceLog.objects.create(
            terminal=terminal,
            user=user,
            enrollid=record.enrollid,
            time=log_time,
            mode=record.mode,
            inout=record.inout,
            event=record.event,
            temperature=record.temp,
            verifymode=record.verifymode,
            image=record.image or '',
            raw_payload={
                'enrollid': record.enrollid,
                'time': record.time,
                'mode': record.mode,
                'inout': record.inout,
                'event': record.event,
                'temp': record.temp,
            }
        )
    
    @staticmethod
    def _check_access_sync(terminal: Terminal, enrollid: int) -> bool:
        """Vérifie si un utilisateur a accès (sync)"""
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
            # Utilisateur inconnu, on accorde l'accès par défaut
            return True
    
    @staticmethod
    @sync_to_async
    def get_new_logs_count(terminal: Terminal) -> int:
        """Compte les nouveaux logs non synchronisés"""
        return AttendanceLog.objects.filter(
            terminal=terminal
        ).count()


class UserService:
    """Service de gestion des utilisateurs biométriques"""
    
    @staticmethod
    @sync_to_async
    def process_user(terminal: Terminal, user_msg: SendUserMessage) -> bool:
        """
        Traite un utilisateur envoyé par le terminal
        """
        try:
            with transaction.atomic():
                # Créer ou mettre à jour l'utilisateur
                user, created = BiometricUser.objects.update_or_create(
                    terminal=terminal,
                    enrollid=user_msg.enrollid,
                    defaults={
                        'name': user_msg.name,
                        'admin': user_msg.admin,
                    }
                )
                
                # Créer ou mettre à jour le credential
                if user_msg.record is not None:
                    record_str = str(user_msg.record)
                    BiometricCredential.objects.update_or_create(
                        user=user,
                        backupnum=user_msg.backupnum,
                        defaults={'record': record_str}
                    )
                
                action = "créé" if created else "mis à jour"
                logger.info(
                    f"[{terminal.sn}] Utilisateur {user_msg.enrollid} {action} "
                    f"(backupnum={user_msg.backupnum})"
                )
                return True
                
        except Exception as e:
            logger.error(f"Erreur traitement utilisateur: {e}")
            return False
    
    @staticmethod
    @sync_to_async
    def get_user(terminal: Terminal, enrollid: int) -> Optional[BiometricUser]:
        """Récupère un utilisateur"""
        try:
            return BiometricUser.objects.get(
                terminal=terminal,
                enrollid=enrollid
            )
        except BiometricUser.DoesNotExist:
            return None
    
    @staticmethod
    @sync_to_async
    def set_user_enabled(terminal: Terminal, enrollid: int, enabled: bool) -> bool:
        """Active ou désactive un utilisateur"""
        updated = BiometricUser.objects.filter(
            terminal=terminal,
            enrollid=enrollid
        ).update(is_enabled=enabled)
        return updated > 0
    
    @staticmethod
    @sync_to_async
    def delete_user(terminal: Terminal, enrollid: int) -> bool:
        """Supprime un utilisateur"""
        deleted, _ = BiometricUser.objects.filter(
            terminal=terminal,
            enrollid=enrollid
        ).delete()
        return deleted > 0
    
    @staticmethod
    @sync_to_async
    def get_all_users(terminal: Terminal) -> list[dict]:
        """Récupère tous les utilisateurs d'un terminal"""
        users = BiometricUser.objects.filter(terminal=terminal)
        return [
            {
                'enrollid': u.enrollid,
                'name': u.name,
                'admin': u.admin,
                'is_enabled': u.is_enabled,
            }
            for u in users
        ]


class CommandService:
    """Service de gestion des commandes vers les terminaux"""
    
    @staticmethod
    @sync_to_async
    def queue_command(
        terminal: Terminal,
        command: str,
        payload: dict
    ) -> CommandQueue:
        """Ajoute une commande à la file d'attente"""
        return CommandQueue.objects.create(
            terminal=terminal,
            command=command,
            payload=payload,
            status='pending'
        )
    
    @staticmethod
    @sync_to_async
    def get_pending_commands(terminal: Terminal) -> list[CommandQueue]:
        """Récupère les commandes en attente pour un terminal"""
        return list(
            CommandQueue.objects.filter(
                terminal=terminal,
                status='pending'
            ).order_by('created_at')[:10]
        )
    
    @staticmethod
    @sync_to_async
    def mark_command_sent(command_id: int) -> None:
        """Marque une commande comme envoyée"""
        CommandQueue.objects.filter(id=command_id).update(
            status='sent',
            sent_at=timezone.now()
        )
    
    @staticmethod
    @sync_to_async
    def mark_command_completed(
        command_id: int,
        success: bool,
        response: Optional[dict] = None,
        error: str = ""
    ) -> None:
        """Marque une commande comme terminée"""
        status = 'success' if success else 'failed'
        CommandQueue.objects.filter(id=command_id).update(
            status=status,
            response=response,
            error_message=error,
            completed_at=timezone.now()
        )


class TimeService:
    """Service de synchronisation temporelle"""
    
    @staticmethod
    def get_server_time() -> str:
        """Retourne l'heure serveur formatée"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    @staticmethod
    def build_sync_command() -> dict:
        """Construit la commande de synchronisation horaire"""
        return TM20Protocol.build_settime_command()


class AccessControlService:
    """Service de contrôle d'accès"""
    
    @staticmethod
    @sync_to_async
    def check_user_access(
        terminal: Terminal,
        enrollid: int
    ) -> tuple[bool, str]:
        """
        Vérifie si un utilisateur a accès
        Retourne (access_granted, message)
        """
        try:
            user = BiometricUser.objects.get(
                terminal=terminal,
                enrollid=enrollid
            )
            
            if not user.is_enabled:
                return False, "Utilisateur désactivé"
            
            now = timezone.now()
            
            if user.starttime and now < user.starttime:
                return False, "Accès non encore valide"
            
            if user.endtime and now > user.endtime:
                return False, "Accès expiré"
            
            return True, "Accès autorisé"
            
        except BiometricUser.DoesNotExist:
            # Par défaut, on autorise les utilisateurs inconnus
            # (ils sont peut-être enregistrés localement sur le terminal)
            return True, "Utilisateur non trouvé en base"
    
    @staticmethod
    @sync_to_async
    def check_qrcode_access(
        terminal: Terminal,
        qrcode: str
    ) -> tuple[bool, int, str, str]:
        """
        Vérifie l'accès par QR code
        Retourne (access_granted, enrollid, username, message)
        """
        # Implémentation basique - à personnaliser selon les besoins
        # Le QR code pourrait contenir un enrollid ou un token
        try:
            enrollid = int(qrcode)
            user = BiometricUser.objects.get(
                terminal=terminal,
                enrollid=enrollid
            )
            
            if not user.is_enabled:
                return False, enrollid, user.name, "Utilisateur désactivé"
            
            return True, enrollid, user.name, "Accès autorisé"
            
        except (ValueError, BiometricUser.DoesNotExist):
            return False, 0, "", "QR code invalide"

"""
Service de synchronisation avec services tiers
Gère la récupération des utilisateurs et l'envoi des pointages
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import httpx
from django.utils import timezone
from django.db import transaction

from ..models import (
    ThirdPartyConfig,
    TerminalThirdPartyMapping,
    BiometricUser,
    AttendanceLog,
    Terminal,
)

logger = logging.getLogger('devices.third_party_sync')


class ThirdPartySyncService:
    """Service de synchronisation avec services tiers"""
    
    def __init__(self, config: ThirdPartyConfig):
        self.config = config
        self.client = None
    
    def _get_headers(self) -> Dict[str, str]:
        """Construit les headers HTTP avec authentification"""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        
        if self.config.auth_type == 'bearer':
            headers[self.config.auth_header_name] = f'Bearer {self.config.auth_token}'
        elif self.config.auth_type == 'api_key':
            headers[self.config.auth_header_name] = self.config.auth_token
        elif self.config.auth_type == 'basic':
            headers[self.config.auth_header_name] = f'Basic {self.config.auth_token}'
        
        if self.config.extra_headers:
            headers.update(self.config.extra_headers)
        
        return headers
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        Effectue une requête HTTP vers le service tiers
        
        Returns:
            Tuple[success, response_data, error_message]
        """
        url = f"{self.config.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = self._get_headers()
        
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                if method.upper() == 'GET':
                    response = await client.get(url, headers=headers, params=params)
                elif method.upper() == 'POST':
                    response = await client.post(url, headers=headers, json=data)
                elif method.upper() == 'PUT':
                    response = await client.put(url, headers=headers, json=data)
                else:
                    return False, None, f"Méthode HTTP non supportée: {method}"
                
                response.raise_for_status()
                
                try:
                    response_data = response.json()
                except Exception:
                    response_data = {'status': 'success', 'text': response.text}
                
                return True, response_data, None
                
        except httpx.TimeoutException:
            error = f"Timeout après {self.config.timeout_seconds}s"
            logger.error(f"Timeout requête vers {url}: {error}")
            return False, None, error
            
        except httpx.HTTPStatusError as e:
            error = f"Erreur HTTP {e.response.status_code}: {e.response.text}"
            logger.error(f"Erreur HTTP vers {url}: {error}")
            return False, None, error
            
        except Exception as e:
            error = f"Erreur inattendue: {str(e)}"
            logger.exception(f"Erreur requête vers {url}")
            return False, None, error
    
    async def fetch_users(self, terminal_id: Optional[int] = None) -> Tuple[bool, List[Dict], Optional[str]]:
        """
        Récupère les utilisateurs depuis le service tiers
        
        Args:
            terminal_id: ID du terminal (optionnel, peut être utilisé comme filtre)
        
        Returns:
            Tuple[success, users_list, error_message]
        """
        if not self.config.users_endpoint:
            return False, [], "Endpoint utilisateurs non configuré"
        
        params = {}
        if terminal_id:
            params['terminal_id'] = terminal_id
        
        success, data, error = await self._make_request(
            'GET',
            self.config.users_endpoint,
            params=params
        )
        
        if not success:
            return False, [], error
        
        users = data.get('users', []) if isinstance(data, dict) else data
        
        if not isinstance(users, list):
            return False, [], "Format de réponse invalide: 'users' doit être une liste"
        
        return True, users, None
    
    async def send_attendance(self, attendance_logs: List[AttendanceLog]) -> Tuple[bool, Optional[str]]:
        """
        Envoie les pointages vers le service tiers
        
        Args:
            attendance_logs: Liste des logs de pointage à envoyer
        
        Returns:
            Tuple[success, error_message]
        """
        if not self.config.attendance_endpoint:
            return False, "Endpoint pointages non configuré"
        
        if not attendance_logs:
            return True, None
        
        payload = {
            'attendance': [
                {
                    'terminal_sn': log.terminal.sn,
                    'enrollid': log.enrollid,
                    'user_name': log.user.name if log.user else '',
                    'time': log.time.isoformat(),
                    'mode': log.mode,
                    'inout': log.inout,
                    'event': log.event,
                    'temperature': float(log.temperature) if log.temperature else None,
                    'access_granted': log.access_granted,
                    'log_id': log.id,
                }
                for log in attendance_logs
            ]
        }
        
        success, data, error = await self._make_request(
            'POST',
            self.config.attendance_endpoint,
            data=payload
        )
        
        return success, error


class UserSyncService:
    """Service de synchronisation des utilisateurs depuis service tiers vers terminal"""
    
    @staticmethod
    async def sync_users_for_terminal(
        terminal: Terminal,
        config: ThirdPartyConfig
    ) -> Tuple[int, int, Optional[str]]:
        """
        Synchronise les utilisateurs depuis le service tiers vers un terminal
        
        Returns:
            Tuple[users_created, users_updated, error_message]
        """
        sync_service = ThirdPartySyncService(config)
        
        success, users_data, error = await sync_service.fetch_users(terminal.id)
        
        if not success:
            logger.error(f"Échec récupération utilisateurs pour {terminal.sn}: {error}")
            return 0, 0, error
        
        created_count = 0
        updated_count = 0
        
        for user_data in users_data:
            try:
                enrollid = user_data.get('enrollid') or user_data.get('id')
                if not enrollid:
                    logger.warning(f"Utilisateur sans enrollid: {user_data}")
                    continue
                
                user_defaults = {
                    'name': user_data.get('name', ''),
                    'admin': user_data.get('admin', 0),
                    'is_enabled': user_data.get('is_enabled', True),
                }
                
                if 'weekzone' in user_data:
                    user_defaults['weekzone'] = user_data['weekzone']
                if 'group' in user_data:
                    user_defaults['group'] = user_data['group']
                
                user, created = await BiometricUser.objects.aupdate_or_create(
                    terminal=terminal,
                    enrollid=enrollid,
                    defaults=user_defaults
                )
                
                if created:
                    created_count += 1
                    logger.info(f"Utilisateur créé: {user.name} (enrollid={enrollid})")
                else:
                    updated_count += 1
                    logger.info(f"Utilisateur mis à jour: {user.name} (enrollid={enrollid})")
                    
            except Exception as e:
                logger.exception(f"Erreur création/mise à jour utilisateur: {e}")
                continue
        
        await TerminalThirdPartyMapping.objects.filter(
            terminal=terminal,
            config=config
        ).aupdate(last_user_sync=timezone.now())
        
        logger.info(
            f"Synchronisation terminée pour {terminal.sn}: "
            f"{created_count} créés, {updated_count} mis à jour"
        )
        
        return created_count, updated_count, None
    
    @staticmethod
    async def sync_users_to_terminal_device(
        terminal: Terminal,
        user_ids: Optional[List[int]] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Envoie les utilisateurs vers le terminal physique via WebSocket
        
        Args:
            terminal: Terminal cible
            user_ids: Liste des IDs utilisateurs à synchroniser (None = tous)
        
        Returns:
            Tuple[success, error_message]
        """
        from ..services.commands import CommandService
        from ..core.device_manager import DeviceManager
        
        device_manager = DeviceManager.get_instance()
        
        if not await device_manager.is_connected(terminal.sn):
            return False, f"Terminal {terminal.sn} non connecté"
        
        query = BiometricUser.objects.filter(terminal=terminal, is_enabled=True)
        if user_ids:
            query = query.filter(id__in=user_ids)
        
        users = await query.aprefetch_related('credentials').all()
        
        command_service = CommandService()
        success_count = 0
        
        async for user in users:
            try:
                result = await command_service.send_setuserinfo(
                    terminal.sn,
                    enrollid=user.enrollid,
                    name=user.name,
                    backupnum=0,
                )
                
                if result.get('success'):
                    success_count += 1
                    
            except Exception as e:
                logger.exception(f"Erreur envoi utilisateur {user.enrollid} vers {terminal.sn}: {e}")
                continue
        
        total_users = await query.acount()
        
        if success_count == total_users:
            return True, None
        elif success_count > 0:
            return True, f"Synchronisation partielle: {success_count}/{total_users} utilisateurs"
        else:
            return False, "Aucun utilisateur synchronisé"


class AttendanceSyncService:
    """Service de synchronisation des pointages vers service tiers"""
    
    @staticmethod
    async def sync_pending_attendance(
        config: ThirdPartyConfig,
        terminal: Optional[Terminal] = None,
        batch_size: int = 100
    ) -> Tuple[int, int, Optional[str]]:
        """
        Synchronise les pointages en attente vers le service tiers
        
        Args:
            config: Configuration du service tiers
            terminal: Terminal spécifique (None = tous les terminaux mappés)
            batch_size: Nombre de logs à traiter par batch
        
        Returns:
            Tuple[sent_count, failed_count, error_message]
        """
        sync_service = ThirdPartySyncService(config)
        
        query = AttendanceLog.objects.filter(sync_status='pending')
        
        if terminal:
            query = query.filter(terminal=terminal)
        else:
            mapped_terminals = await TerminalThirdPartyMapping.objects.filter(
                config=config,
                is_active=True,
                sync_attendance=True
            ).values_list('terminal_id', flat=True).all()
            
            query = query.filter(terminal_id__in=list(mapped_terminals))
        
        query = query.select_related('terminal', 'user').order_by('time')
        
        pending_logs = await query[:batch_size].all()
        pending_logs = list(pending_logs)
        
        if not pending_logs:
            return 0, 0, None
        
        for attempt in range(config.retry_attempts):
            success, error = await sync_service.send_attendance(pending_logs)
            
            if success:
                log_ids = [log.id for log in pending_logs]
                
                await AttendanceLog.objects.filter(id__in=log_ids).aupdate(
                    sync_status='sent',
                    synced_at=timezone.now(),
                    sync_error=''
                )
                
                if terminal:
                    await TerminalThirdPartyMapping.objects.filter(
                        terminal=terminal,
                        config=config
                    ).aupdate(last_attendance_sync=timezone.now())
                
                logger.info(
                    f"✅ {len(pending_logs)} pointages synchronisés vers {config.name}"
                )
                
                return len(pending_logs), 0, None
            
            logger.warning(
                f"Tentative {attempt + 1}/{config.retry_attempts} échouée: {error}"
            )
            
            if attempt < config.retry_attempts - 1:
                await asyncio.sleep(2 ** attempt)
        
        log_ids = [log.id for log in pending_logs]
        await AttendanceLog.objects.filter(id__in=log_ids).aupdate(
            sync_status='failed',
            sync_attempts=models.F('sync_attempts') + 1,
            sync_error=error or 'Échec après plusieurs tentatives'
        )
        
        logger.error(
            f"❌ Échec synchronisation de {len(pending_logs)} pointages vers {config.name}: {error}"
        )
        
        return 0, len(pending_logs), error
    
    @staticmethod
    async def retry_failed_attendance(
        config: ThirdPartyConfig,
        max_attempts: int = 5
    ) -> Tuple[int, int]:
        """
        Retente l'envoi des pointages échoués
        
        Returns:
            Tuple[sent_count, still_failed_count]
        """
        failed_logs = await AttendanceLog.objects.filter(
            sync_status='failed',
            sync_attempts__lt=max_attempts
        ).select_related('terminal', 'user').all()
        
        failed_logs = list(failed_logs)
        
        if not failed_logs:
            return 0, 0
        
        sync_service = ThirdPartySyncService(config)
        success, error = await sync_service.send_attendance(failed_logs)
        
        if success:
            log_ids = [log.id for log in failed_logs]
            await AttendanceLog.objects.filter(id__in=log_ids).aupdate(
                sync_status='sent',
                synced_at=timezone.now(),
                sync_error=''
            )
            return len(failed_logs), 0
        else:
            log_ids = [log.id for log in failed_logs]
            await AttendanceLog.objects.filter(id__in=log_ids).aupdate(
                sync_attempts=models.F('sync_attempts') + 1,
                sync_error=error or 'Échec retry'
            )
            return 0, len(failed_logs)


import asyncio
from django.db import models

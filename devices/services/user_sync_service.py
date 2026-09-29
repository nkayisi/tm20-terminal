"""
User Sync Service - Service de synchronisation des utilisateurs

Gère la synchronisation bidirectionnelle des utilisateurs:
- Récupération depuis les services tiers
- Enregistrement dans BiometricUser
- Chargement vers les terminaux physiques
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

from django.db import transaction
from django.utils import timezone
from asgiref.sync import sync_to_async

from ..models import Terminal, BiometricUser, ThirdPartyConfig, TerminalThirdPartyMapping
from ..integrations import AdapterFactory, AdapterResponse, UserData

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Résultat d'une opération de synchronisation"""
    success: bool
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[str] = None
    details: Dict[str, Any] = None
    
    def __post_init__(self):
        self.errors = self.errors or []
        self.details = self.details or {}
    
    @property
    def total_processed(self) -> int:
        return self.created + self.updated + self.skipped
    
    def to_dict(self) -> dict:
        return {
            'success': self.success,
            'created': self.created,
            'updated': self.updated,
            'skipped': self.skipped,
            'total_processed': self.total_processed,
            'errors': self.errors,
            'details': self.details,
        }


class UserSyncService:
    """
    Service de synchronisation des utilisateurs.
    
    Responsabilités:
    - Récupérer les utilisateurs depuis un service tiers
    - Créer/mettre à jour les BiometricUser en base
    - Préparer les utilisateurs pour chargement sur terminal
    - Gérer les doublons via external_id
    """
    
    def __init__(self, terminal: Terminal, config: ThirdPartyConfig):
        self.terminal = terminal
        self.config = config
        self.adapter = AdapterFactory.create(config)
        self.logger = logging.getLogger(f"{__name__}.{terminal.sn}")
    
    async def fetch_and_sync_users(self, **fetch_params) -> SyncResult:
        """
        Récupère les utilisateurs depuis le service tiers et les synchronise en base.
        
        Args:
            **fetch_params: Paramètres optionnels pour la requête (pagination, filtres)
            
        Returns:
            SyncResult avec le détail des opérations
        """
        self.logger.info(f"Début synchronisation utilisateurs pour {self.terminal.sn}")
        
        try:
            response = await self.adapter.fetch_users(**fetch_params)
            
            if not response.success:
                return SyncResult(
                    success=False,
                    errors=[response.message],
                    details={'adapter_response': response.to_dict()}
                )
            
            users_data: List[UserData] = response.data or []
            
            if not users_data:
                self.logger.info("Aucun utilisateur récupéré depuis le service tiers")
                return SyncResult(success=True, details={'message': 'Aucun utilisateur à synchroniser'})
            
            result = await self._sync_users_to_db(users_data)
            
            await self._update_mapping_timestamp()
            
            self.logger.info(
                f"Synchronisation terminée: {result.created} créés, "
                f"{result.updated} mis à jour, {result.skipped} ignorés"
            )
            
            return result
            
        except Exception as e:
            self.logger.exception(f"Erreur lors de la synchronisation: {e}")
            return SyncResult(
                success=False,
                errors=[str(e)],
                details={'exception': type(e).__name__}
            )
        finally:
            await self.adapter.close()
    
    @sync_to_async
    def _sync_users_to_db(self, users_data: List[UserData]) -> SyncResult:
        """Synchronise les utilisateurs en base de données"""
        created = 0
        updated = 0
        skipped = 0
        errors = []
        
        with transaction.atomic():
            for user_data in users_data:
                try:
                    result = self._upsert_user(user_data)
                    if result == 'created':
                        created += 1
                    elif result == 'updated':
                        updated += 1
                    else:
                        skipped += 1
                except Exception as e:
                    errors.append(f"Erreur pour {user_data.external_id}: {str(e)}")
                    self.logger.error(f"Erreur upsert user {user_data.external_id}: {e}")
        
        return SyncResult(
            success=len(errors) == 0,
            created=created,
            updated=updated,
            skipped=skipped,
            errors=errors,
            details={
                'terminal_sn': self.terminal.sn,
                'config_name': self.config.name,
                'timestamp': timezone.now().isoformat(),
            }
        )
    
    def _upsert_user(self, user_data: UserData) -> str:
        """
        Crée ou met à jour un utilisateur biométrique.
        
        Returns:
            'created', 'updated', ou 'skipped'
        """
        existing = BiometricUser.objects.filter(
            terminal=self.terminal,
            external_id=user_data.external_id
        ).first()
        
        if existing:
            changed = False
            
            if existing.name != user_data.fullname:
                existing.name = user_data.fullname
                changed = True
            
            if existing.is_enabled != user_data.is_enabled:
                existing.is_enabled = user_data.is_enabled
                changed = True
            
            if existing.admin != user_data.admin_level:
                existing.admin = user_data.admin_level
                changed = True
            
            if existing.group != user_data.group:
                existing.group = user_data.group
                changed = True
            
            new_metadata = {**existing.metadata, **user_data.metadata}
            if existing.metadata != new_metadata:
                existing.metadata = new_metadata
                changed = True
            
            if changed:
                existing.sync_status = 'pending_sync'
                existing.save()
                return 'updated'
            
            return 'skipped'
        
        enrollid = BiometricUser.get_next_enrollid(self.terminal)
        
        start_date = None
        end_date = None
        
        if user_data.start_date:
            try:
                start_date = datetime.fromisoformat(user_data.start_date.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass
        
        if user_data.end_date:
            try:
                end_date = datetime.fromisoformat(user_data.end_date.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass
        
        BiometricUser.objects.create(
            terminal=self.terminal,
            enrollid=enrollid,
            external_id=user_data.external_id,
            name=user_data.fullname,
            is_enabled=user_data.is_enabled,
            admin=user_data.admin_level,
            group=user_data.group,
            weekzone=user_data.weekzone,
            starttime=start_date,
            endtime=end_date,
            metadata=user_data.metadata,
            source_config=self.config,
            sync_status='pending_sync',
        )
        
        return 'created'
    
    @sync_to_async
    def _update_mapping_timestamp(self):
        """Met à jour le timestamp de dernière synchronisation dans le mapping"""
        TerminalThirdPartyMapping.objects.filter(
            terminal=self.terminal,
            config=self.config
        ).update(last_user_sync=timezone.now())
    
    @sync_to_async
    def get_users_pending_sync(self) -> List[BiometricUser]:
        """Récupère les utilisateurs en attente de synchronisation vers le terminal"""
        return list(
            BiometricUser.objects.filter(
                terminal=self.terminal,
                sync_status='pending_sync'
            ).order_by('enrollid')
        )
    
    @sync_to_async
    def mark_users_synced(self, user_ids: List[int]):
        """Marque les utilisateurs comme synchronisés vers le terminal"""
        BiometricUser.objects.filter(
            id__in=user_ids
        ).update(
            sync_status='synced_to_terminal',
            last_synced_at=timezone.now()
        )
    
    @sync_to_async
    def mark_user_error(self, user_id: int, error_message: str):
        """Marque un utilisateur en erreur de synchronisation"""
        BiometricUser.objects.filter(id=user_id).update(
            sync_status='error',
            metadata={'sync_error': error_message, 'error_at': timezone.now().isoformat()}
        )
    
    async def push_users_to_terminal(self, user_ids: List[int] = None) -> SyncResult:
        """
        Envoie les utilisateurs vers le terminal physique.
        
        Args:
            user_ids: Liste des IDs utilisateurs à envoyer. Si None, envoie tous les utilisateurs pending_sync
            
        Returns:
            SyncResult avec le détail des opérations
        """
        self.logger.info(f"Début envoi utilisateurs vers terminal {self.terminal.sn}")
        
        try:
            if user_ids:
                users = await self._get_users_by_ids(user_ids)
            else:
                users = await self.get_users_pending_sync()
            
            if not users:
                return SyncResult(
                    success=True,
                    details={'message': 'Aucun utilisateur à synchroniser'}
                )
            
            # Envoyer tous les utilisateurs en une seule commande batch
            try:
                success = await self._send_users_batch_to_terminal(users)
                if success:
                    sent = len(users)
                    failed = 0
                    errors = []
                else:
                    sent = 0
                    failed = len(users)
                    errors = [f"Échec envoi batch de {len(users)} utilisateurs"]
            except Exception as e:
                sent = 0
                failed = len(users)
                errors = [f"Erreur envoi batch: {str(e)}"]
                self.logger.error(f"Erreur envoi batch: {e}")
            
            self.logger.info(
                f"Envoi terminé: {sent} envoyés, {failed} échecs"
            )
            
            return SyncResult(
                success=failed == 0,
                created=sent,
                skipped=failed,
                errors=errors,
                details={
                    'terminal_sn': self.terminal.sn,
                    'sent': sent,
                    'failed': failed,
                    'timestamp': timezone.now().isoformat(),
                }
            )
            
        except Exception as e:
            self.logger.exception(f"Erreur lors de l'envoi vers terminal: {e}")
            return SyncResult(
                success=False,
                errors=[str(e)],
                details={'exception': type(e).__name__}
            )
    
    # `setusername` accepte au maximum 50 enregistrements par paquet
    # (doc section S6). Au-dela, le terminal tronque ou rejette le message.
    SETUSERNAME_BATCH_SIZE = 50

    @sync_to_async
    def _get_users_by_ids(self, user_ids: List[int]) -> List[BiometricUser]:
        """Récupère les utilisateurs par leurs IDs"""
        return list(
            BiometricUser.objects.filter(
                id__in=user_ids,
                terminal=self.terminal
            ).order_by('enrollid')
        )

    @sync_to_async
    def _get_credentials(self, users: List[BiometricUser]) -> Dict[int, list]:
        """Credentials à téléverser, groupés par identifiant utilisateur."""
        from ..models import BiometricCredential

        credentials: Dict[int, list] = {}
        queryset = BiometricCredential.objects.filter(
            user__in=users
        ).order_by('user_id', 'backupnum')
        for cred in queryset:
            # Un credential sans donnee n'a rien a televerser : c'est le cas
            # des marqueurs crees par `getuserlist`, qui signalent seulement
            # qu'une empreinte existe deja sur le terminal.
            if not cred.record:
                continue
            credentials.setdefault(cred.user_id, []).append(cred)
        return credentials

    async def _send_users_batch_to_terminal(self, users: List[BiometricUser]) -> bool:
        """
        Envoie plusieurs utilisateurs vers le terminal.

        Deux commandes distinctes, conformement a la spec :
        - `setusername` (section S6) cree/renomme les entrees utilisateur, par
          paquets de 50 au maximum ;
        - `setuserinfo` (section S3) televerse UN credential (empreinte, carte,
          mot de passe, photo) et ne peut pas etre remplace par `setusername`.

        Un utilisateur sans credential enregistre cote serveur ne recoit donc
        que son nom : le gabarit biometrique doit etre enrole sur le terminal
        ou importe au prealable.

        Returns:
            True si toutes les commandes ont ete transmises
        """
        if not users:
            return True

        sent_ok = True

        # 1. Noms, par paquets de 50 (limite protocolaire)
        for start in range(0, len(users), self.SETUSERNAME_BATCH_SIZE):
            chunk = users[start:start + self.SETUSERNAME_BATCH_SIZE]
            if not await self._send_setusername(chunk):
                sent_ok = False

        # 2. Credentials disponibles
        credentials = await self._get_credentials(users)
        if credentials:
            by_id = {user.id: user for user in users}
            for user_id, creds in credentials.items():
                user = by_id.get(user_id)
                if user is None:
                    continue
                for cred in creds:
                    if not await self._send_setuserinfo(user, cred):
                        sent_ok = False
        else:
            self.logger.info(
                f"Aucun credential a televerser pour {len(users)} utilisateur(s) : "
                f"seuls les noms sont envoyes"
            )

        return sent_ok

    async def _send_setusername(self, users: List[BiometricUser]) -> bool:
        """Envoie un paquet `setusername` (<= 50 enregistrements)."""
        from ..protocol.builders import CommandBuilder

        payload = CommandBuilder.setusername(users=[
            {
                'enrollid': user.enrollid,
                'name': user.name or f"User{user.enrollid}",
            }
            for user in users
        ])
        # Metadonnees consommees par le consumer pour correler la reponse.
        payload['_user_ids'] = [user.id for user in users]
        payload['_terminal_id'] = self.terminal.id

        return await self._group_send(
            payload,
            f"setusername pour {len(users)} utilisateur(s) "
            f"(enrollids={[u.enrollid for u in users]})"
        )

    async def _send_setuserinfo(self, user: BiometricUser, credential) -> bool:
        """Téléverse un credential vers le terminal (doc section S3)."""
        from ..protocol.builders import CommandBuilder

        payload = CommandBuilder.setuserinfo(
            enrollid=user.enrollid,
            name=user.name or f"User{user.enrollid}",
            backupnum=credential.backupnum,
            admin=user.admin,
            record=self._coerce_record(credential),
        )
        return await self._group_send(
            payload,
            f"setuserinfo enrollid={user.enrollid} "
            f"backupnum={credential.backupnum}"
        )

    @staticmethod
    def _coerce_record(credential):
        """Type attendu par `record`, dicte par `backupnum` (doc section 1.2).

        Mot de passe (10) et carte RFID (11) sont des NOMBRES ; empreintes,
        visages, paumes et photos sont des chaines.
        """
        if credential.backupnum in (10, 11):
            try:
                return int(credential.record)
            except (TypeError, ValueError):
                return credential.record
        return credential.record

    async def _group_send(self, payload: dict, description: str) -> bool:
        """Transmet une commande au consumer du terminal via Channels."""
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        if not channel_layer:
            self.logger.error("Channel layer non disponible")
            return False

        group_name = f'terminal_{self.terminal.sn}'
        try:
            await channel_layer.group_send(
                group_name, {'type': 'send_command', 'command': payload}
            )
            self.logger.info(f"Envoye vers '{group_name}' : {description}")
            return True
        except Exception as e:
            self.logger.error(f"Echec envoi ({description}) : {e}")
            return False


class UserSyncManager:
    """
    Manager pour orchestrer la synchronisation des utilisateurs.
    
    Fournit des méthodes de haut niveau pour:
    - Synchroniser un terminal spécifique
    - Synchroniser tous les terminaux d'une configuration
    - Obtenir le statut de synchronisation
    """
    
    @staticmethod
    async def sync_terminal_users(
        terminal_id: int,
        config_id: int,
        **fetch_params
    ) -> SyncResult:
        """
        Synchronise les utilisateurs pour un terminal depuis une configuration.
        
        Args:
            terminal_id: ID du terminal
            config_id: ID de la configuration du service tiers
            **fetch_params: Paramètres pour la requête
            
        Returns:
            SyncResult
        """
        terminal = await sync_to_async(Terminal.objects.get)(id=terminal_id)
        config = await sync_to_async(ThirdPartyConfig.objects.get)(id=config_id)
        
        service = UserSyncService(terminal, config)
        return await service.fetch_and_sync_users(**fetch_params)
    
    @staticmethod
    async def sync_all_terminals_for_config(config_id: int) -> Dict[str, SyncResult]:
        """
        Synchronise tous les terminaux associés à une configuration.
        
        Returns:
            Dict mapping terminal_sn -> SyncResult
        """
        results = {}
        
        @sync_to_async
        def get_mappings():
            return list(
                TerminalThirdPartyMapping.objects.filter(
                    config_id=config_id,
                    is_active=True,
                    sync_users=True
                ).select_related('terminal', 'config')
            )
        
        mappings = await get_mappings()
        
        for mapping in mappings:
            service = UserSyncService(mapping.terminal, mapping.config)
            result = await service.fetch_and_sync_users()
            results[mapping.terminal.sn] = result
        
        return results
    
    @staticmethod
    @sync_to_async
    def get_sync_status(terminal_id: int) -> Dict[str, Any]:
        """Retourne le statut de synchronisation pour un terminal"""
        terminal = Terminal.objects.get(id=terminal_id)
        
        users = BiometricUser.objects.filter(terminal=terminal)
        
        return {
            'terminal_sn': terminal.sn,
            'total_users': users.count(),
            'local': users.filter(sync_status='local').count(),
            'synced': users.filter(sync_status='synced').count(),
            'pending_sync': users.filter(sync_status='pending_sync').count(),
            'synced_to_terminal': users.filter(sync_status='synced_to_terminal').count(),
            'error': users.filter(sync_status='error').count(),
        }
    
    @staticmethod
    async def push_all_users_to_terminals() -> Dict[str, SyncResult]:
        """
        Envoie tous les utilisateurs vers leurs terminaux respectifs.
        
        Returns:
            Dict mapping terminal_sn -> SyncResult
        """
        results = {}
        
        @sync_to_async
        def get_terminals_with_pending_users():
            from django.db.models import Q
            return list(
                Terminal.objects.filter(
                    Q(users__sync_status='pending_sync') |
                    Q(users__sync_status='local')
                ).distinct()
            )
        
        terminals = await get_terminals_with_pending_users()
        
        for terminal in terminals:
            @sync_to_async
            def get_config():
                mapping = TerminalThirdPartyMapping.objects.filter(
                    terminal=terminal,
                    is_active=True
                ).select_related('config').first()
                return mapping.config if mapping else None
            
            config = await get_config()
            
            if not config:
                logger.warning(f"Aucune configuration trouvée pour {terminal.sn}")
                continue
            
            service = UserSyncService(terminal, config)
            result = await service.push_users_to_terminal()
            results[terminal.sn] = result
        
        return results
    
    @staticmethod
    async def push_terminal_users(terminal_id: int) -> SyncResult:
        """
        Envoie tous les utilisateurs d'un terminal vers ce terminal.
        
        Args:
            terminal_id: ID du terminal
            
        Returns:
            SyncResult
        """
        @sync_to_async
        def get_terminal_and_config():
            terminal = Terminal.objects.get(id=terminal_id)
            mapping = TerminalThirdPartyMapping.objects.filter(
                terminal=terminal,
                is_active=True
            ).select_related('config').first()
            config = mapping.config if mapping else None
            return terminal, config
        
        terminal, config = await get_terminal_and_config()
        
        if not config:
            return SyncResult(
                success=False,
                errors=["Aucune configuration de service tiers trouvée pour ce terminal"]
            )
        
        service = UserSyncService(terminal, config)
        return await service.push_users_to_terminal()

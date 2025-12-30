"""
WebSocket Consumer pour terminaux TM20-WIFI
Gestion des connexions et du protocole WebSocket + JSON v2.4
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from .models import Terminal
from .protocol import ProtocolError, TM20Protocol
from .services import (
    AccessControlService,
    AttendanceService,
    CommandService,
    TerminalService,
    TimeService,
    UserService,
)

logger = logging.getLogger('devices')


class ConnectionManager:
    """Gestionnaire des connexions WebSocket actives"""
    
    _connections: dict[str, 'TM20Consumer'] = {}
    _lock = asyncio.Lock()
    
    @classmethod
    async def register(cls, sn: str, consumer: 'TM20Consumer') -> None:
        """Enregistre une connexion"""
        async with cls._lock:
            # Fermer l'ancienne connexion si elle existe
            if sn in cls._connections:
                old_consumer = cls._connections[sn]
                try:
                    await old_consumer.close()
                except Exception:
                    pass
            cls._connections[sn] = consumer
            logger.info(f"Terminal {sn} connecté. Total: {len(cls._connections)}")
    
    @classmethod
    async def unregister(cls, sn: str) -> None:
        """Désenregistre une connexion"""
        async with cls._lock:
            if sn in cls._connections:
                del cls._connections[sn]
                logger.info(f"Terminal {sn} déconnecté. Total: {len(cls._connections)}")
    
    @classmethod
    async def get_consumer(cls, sn: str) -> Optional['TM20Consumer']:
        """Récupère le consumer d'un terminal"""
        async with cls._lock:
            return cls._connections.get(sn)
    
    @classmethod
    async def send_to_terminal(cls, sn: str, message: dict) -> bool:
        """Envoie un message à un terminal spécifique"""
        consumer = await cls.get_consumer(sn)
        if consumer:
            await consumer.send_json(message)
            return True
        return False
    
    @classmethod
    async def get_connected_terminals(cls) -> list[str]:
        """Liste des terminaux connectés"""
        async with cls._lock:
            return list(cls._connections.keys())


class TM20Consumer(AsyncWebsocketConsumer):
    """Consumer WebSocket pour terminal TM20"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sn: Optional[str] = None
        self.terminal: Optional[Terminal] = None
        self.registered: bool = False
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.last_message_time: datetime = datetime.now()
    
    async def connect(self):
        """Connexion WebSocket établie"""
        await self.accept()
        logger.info(f"Nouvelle connexion WebSocket: {self.scope['client']}")
        
        # Démarrer le heartbeat
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    
    async def disconnect(self, close_code):
        """Déconnexion WebSocket"""
        logger.info(f"Déconnexion WebSocket: {self.sn or 'unknown'} (code: {close_code})")
        
        # Arrêter le heartbeat
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Désenregistrer la connexion
        if self.sn:
            await ConnectionManager.unregister(self.sn)
            await TerminalService.update_terminal_status(self.sn, is_active=False)
    
    async def receive(self, text_data=None, bytes_data=None):
        """Message reçu du terminal"""
        self.last_message_time = datetime.now()
        
        data = text_data or bytes_data
        if not data:
            return
        
        try:
            message = TM20Protocol.parse_message(data)
            
            if not TM20Protocol.validate_message(message):
                logger.warning(f"Message invalide reçu: {data[:200]}")
                return
            
            await self._handle_message(message)
            
        except ProtocolError as e:
            logger.error(f"Erreur protocole: {e}")
        except Exception as e:
            logger.exception(f"Erreur traitement message: {e}")
    
    async def _handle_message(self, message: dict):
        """Route le message vers le handler approprié"""
        cmd = message.get('cmd', '').lower()
        ret = message.get('ret', '').lower()
        
        # Messages du terminal vers le serveur
        handlers = {
            'reg': self._handle_reg,
            'sendlog': self._handle_sendlog,
            'senduser': self._handle_senduser,
            'sendqrcode': self._handle_sendqrcode,
        }
        
        if cmd in handlers:
            await handlers[cmd](message)
        elif ret:
            # Réponse du terminal à une commande serveur
            await self._handle_response(message)
        else:
            logger.warning(f"Commande non supportée: {cmd or ret}")
    
    async def _handle_reg(self, message: dict):
        """Traite le message d'enregistrement (reg)"""
        sn = message.get('sn', '')
        
        if not sn:
            response = TM20Protocol.build_reg_response(
                success=False,
                reason="SN manquant"
            )
            await self.send_json(response)
            return
        
        # Vérifier la whitelist
        if not await TerminalService.is_terminal_whitelisted(sn):
            logger.warning(f"Terminal non autorisé: {sn}")
            response = TM20Protocol.build_reg_response(
                success=False,
                reason="Terminal non autorisé"
            )
            await self.send_json(response)
            await self.close()
            return
        
        # Parser et enregistrer
        reg_msg = TM20Protocol.parse_register(message)
        self.terminal, created = await TerminalService.register_terminal(reg_msg)
        self.sn = sn
        self.registered = True
        
        # Enregistrer la connexion
        await ConnectionManager.register(sn, self)
        
        # Répondre au terminal avec synchronisation horaire
        response = TM20Protocol.build_reg_response(
            success=True,
            cloudtime=TimeService.get_server_time(),
            nosenduser=True
        )
        await self.send_json(response)
        
        logger.info(f"Terminal enregistré: {sn} (nouveau: {created})")
        
        # Envoyer les commandes en attente
        await self._send_pending_commands()
    
    async def _handle_sendlog(self, message: dict):
        """Traite les logs de pointage (sendlog)"""
        if not self._ensure_registered():
            return
        
        sn = message.get('sn', '')
        if sn != self.sn:
            logger.warning(f"SN mismatch: attendu {self.sn}, reçu {sn}")
            return
        
        log_msg = TM20Protocol.parse_sendlog(message)
        
        # Traiter les logs
        processed, access = await AttendanceService.process_logs(
            self.terminal, log_msg
        )
        
        # Mettre à jour last_seen
        await TerminalService.update_last_seen(self.sn)
        
        # Répondre au terminal
        response = TM20Protocol.build_sendlog_response(
            success=True,
            count=processed,
            logindex=log_msg.logindex,
            access=1 if access else 0
        )
        await self.send_json(response)
    
    async def _handle_senduser(self, message: dict):
        """Traite l'envoi d'utilisateur depuis le terminal (senduser)"""
        if not self._ensure_registered():
            return
        
        user_msg = TM20Protocol.parse_senduser(message)
        
        success = await UserService.process_user(self.terminal, user_msg)
        
        response = TM20Protocol.build_senduser_response(success)
        await self.send_json(response)
    
    async def _handle_sendqrcode(self, message: dict):
        """Traite la vérification QR code"""
        if not self._ensure_registered():
            return
        
        qrcode = message.get('record', '')
        
        access, enrollid, username, msg = await AccessControlService.check_qrcode_access(
            self.terminal, qrcode
        )
        
        response = TM20Protocol.build_sendqrcode_response(
            success=True,
            access=1 if access else 0,
            enrollid=enrollid,
            username=username,
            message=msg
        )
        await self.send_json(response)
    
    async def _handle_response(self, message: dict):
        """Traite une réponse du terminal à une commande serveur"""
        ret = message.get('ret', '')
        result = message.get('result', False)
        
        logger.info(f"[{self.sn}] Réponse {ret}: {result}")
        
        # Ici on pourrait marquer les commandes comme terminées
        # et traiter les données retournées (getuserlist, etc.)
    
    def _ensure_registered(self) -> bool:
        """Vérifie que le terminal est enregistré"""
        if not self.registered or not self.terminal:
            logger.warning("Terminal non enregistré, message ignoré")
            return False
        return True
    
    async def _send_pending_commands(self):
        """Envoie les commandes en attente"""
        if not self.terminal:
            return
        
        commands = await CommandService.get_pending_commands(self.terminal)
        
        for cmd in commands:
            try:
                await self.send_json(cmd.payload)
                await CommandService.mark_command_sent(cmd.id)
                logger.info(f"[{self.sn}] Commande envoyée: {cmd.command}")
            except Exception as e:
                logger.error(f"Erreur envoi commande {cmd.id}: {e}")
    
    async def _heartbeat_loop(self):
        """Boucle de vérification du heartbeat"""
        timeout = settings.TM20_SETTINGS.get('CONNECTION_TIMEOUT', 120)
        interval = settings.TM20_SETTINGS.get('HEARTBEAT_INTERVAL', 30)
        
        while True:
            try:
                await asyncio.sleep(interval)
                
                # Vérifier le timeout
                elapsed = (datetime.now() - self.last_message_time).total_seconds()
                if elapsed > timeout:
                    logger.warning(f"[{self.sn}] Timeout, fermeture connexion")
                    await self.close()
                    break
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erreur heartbeat: {e}")
    
    async def send_json(self, data: dict):
        """Envoie un message JSON au terminal"""
        message = TM20Protocol.serialize_message(data)
        await self.send(text_data=message)
        logger.debug(f"[{self.sn}] Envoyé: {message[:200]}")
    
    # === Méthodes publiques pour envoyer des commandes ===
    
    async def send_setuserinfo(
        self,
        enrollid: int,
        name: str,
        backupnum: int,
        admin: int,
        record: any
    ):
        """Envoie une commande setuserinfo"""
        cmd = TM20Protocol.build_setuserinfo_command(
            enrollid, name, backupnum, admin, record
        )
        await self.send_json(cmd)
    
    async def send_deleteuser(self, enrollid: int, backupnum: int = 13):
        """Envoie une commande deleteuser"""
        cmd = TM20Protocol.build_deleteuser_command(enrollid, backupnum)
        await self.send_json(cmd)
    
    async def send_enableuser(self, enrollid: int, enable: bool = True):
        """Envoie une commande enableuser"""
        cmd = TM20Protocol.build_enableuser_command(enrollid, enable)
        await self.send_json(cmd)
    
    async def send_opendoor(self, door: int = 1, delay: int = 5):
        """Envoie une commande opendoor"""
        cmd = TM20Protocol.build_opendoor_command(door, delay)
        await self.send_json(cmd)
    
    async def send_settime(self):
        """Envoie une commande settime pour synchroniser l'heure"""
        cmd = TM20Protocol.build_settime_command()
        await self.send_json(cmd)
    
    async def send_getuserlist(self, stn: bool = True):
        """Envoie une commande getuserlist"""
        cmd = TM20Protocol.build_getuserlist_command(stn)
        await self.send_json(cmd)
    
    async def send_getnewlog(self, stn: bool = True):
        """Envoie une commande getnewlog"""
        cmd = TM20Protocol.build_getnewlog_command(stn)
        await self.send_json(cmd)
    
    async def send_reboot(self):
        """Envoie une commande reboot"""
        cmd = TM20Protocol.build_reboot_command()
        await self.send_json(cmd)

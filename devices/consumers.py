"""
Consumer WebSocket v2 - Architecture refactorée
Léger, découplé, optimisé pour haute charge

Responsabilités :
- Transport WebSocket uniquement
- Délégation aux handlers
- Intégration Device Manager
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Optional

from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from .models import Terminal
from .protocol import (
    CommandBuilder,
    MessageValidator,
    ResponseBuilder,
    TM20Parser,
    ValidationError,
)
from .handlers import (
    RegistrationHandler,
    AttendanceHandler,
    UserHandler,
    QRCodeHandler,
    ResponseHandler,
    HandlerResult,
)
from .core.device_manager import DeviceManager, DeviceState
from .core.events import EventBus, EventType
from .core.metrics import MetricsCollector
from .services import pending_commands
from .services.commands import CommandService

logger = logging.getLogger('devices.consumer')


class TM20ConsumerV2(AsyncWebsocketConsumer):
    """
    Consumer WebSocket v2 pour terminaux TM20
    
    Architecture :
    - Consumer léger (transport uniquement)
    - Handlers spécialisés par type de message
    - Device Manager centralisé
    - Métriques intégrées
    """
    
    # Handlers (partagés entre instances)
    _handlers: Dict[str, object] = {}
    _handlers_initialized = False
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.sn: Optional[str] = None
        self.terminal: Optional[Terminal] = None
        self.registered: bool = False
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.last_message_at: datetime = datetime.now()
        self.client_ip: Optional[str] = None
        # Etat des commandes paginees en cours (`getuserlist`, `getalllog`,
        # `getnewlog`), par nom de commande. Porte par la connexion : une
        # pagination n'a aucun sens au-dela de la socket qui l'a lancee.
        self._pagination: Dict[str, dict] = {}
        # Horodatage de la derniere sonde applicative envoyee (`gettime`).
        self._last_probe_at: Optional[datetime] = None
        
        # Singletons
        self._device_manager = DeviceManager.get_instance()
        self._event_bus = EventBus.get_instance()
        self._metrics = MetricsCollector.get_instance()
        self._command_service = CommandService()
        
        # Initialiser les handlers (une seule fois)
        self._init_handlers()
    
    @classmethod
    def _init_handlers(cls):
        """Initialise les handlers (partagés)"""
        if cls._handlers_initialized:
            return
        
        cls._handlers = {
            'reg': RegistrationHandler(),
            'sendlog': AttendanceHandler(),
            'senduser': UserHandler(),
            'sendqrcode': QRCodeHandler(),
        }
        cls._response_handler = ResponseHandler()
        cls._handlers_initialized = True
    
    async def connect(self):
        """Connexion WebSocket établie"""
        await self.accept()
        
        client = self.scope.get('client') or ('unknown', 0)
        self.client_ip = client[0] if client[0] != 'unknown' else None
        # Le chemin est journalise : le protocole n'en impose aucun et il
        # varie selon le firmware. C'est la premiere information utile pour
        # diagnostiquer un terminal qui n'apparait pas dans l'application.
        path = self.scope.get('path', '/')
        logger.info(
            f"WebSocket connected: {client[0]}:{client[1]} (chemin: {path})"
        )
        
        # Démarrer le heartbeat
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        # Événement
        await self._event_bus.emit(
            EventType.DEVICE_CONNECTED,
            {'client': f"{client[0]}:{client[1]}"},
            source='TM20Consumer'
        )
    
    async def disconnect(self, close_code):
        """Déconnexion WebSocket"""
        logger.info(f"WebSocket disconnected: {self.sn or 'unregistered'} (code: {close_code})")
        
        # Arrêter le heartbeat
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Quitter le groupe Channels
        if self.sn:
            await self.channel_layer.group_discard(
                f'terminal_{self.sn}',
                self.channel_name
            )
            logger.info(f"[{self.sn}] Retiré du groupe Channels terminal_{self.sn}")
        
        # Désenregistrer du Device Manager.
        # `consumer=self` : si cette socket a deja ete remplacee par une
        # reconnexion, le desenregistrement est refuse et l'etat de la
        # connexion vivante reste intact.
        if self.sn:
            was_current = await self._device_manager.unregister(
                self.sn, consumer=self
            )

            # NE PAS toucher à `is_active` ici : ce champ est le drapeau
            # d'administration « terminal géré/activé » (contrôlé manuellement),
            # PAS l'état de connexion. L'état live est suivi via Redis
            # (DeviceManager.get_connected_sns_from_redis). Une déconnexion WS
            # (reconnexion, timeout heartbeat, redémarrage terminal) ne doit pas
            # faire disparaître le terminal des pages de gestion. On se contente
            # d'actualiser l'horodatage de dernière activité.
            from .services.registration import RegistrationService
            await RegistrationService().update_last_seen(self.sn)

            # Les commandes restees sans reponse ne seront jamais confirmees.
            # Uniquement si nous etions bien la connexion courante : vider la
            # file d'une socket qui nous a remplaces ferait perdre la
            # correlation des `setusername`/`setuserinfo` deja en vol sur elle.
            if was_current:
                pending_commands.clear(self.sn)
        
        # Mettre à jour les métriques
        self._metrics.update_active_connections(
            len(await self._device_manager.get_connected_sns())
        )
    
    async def receive(self, text_data=None, bytes_data=None):
        """Message reçu du terminal"""
        start_time = time.perf_counter()
        self.last_message_at = datetime.now()
        
        data = text_data or bytes_data
        if not data:
            return
        
        try:
            # Parser le JSON
            message = TM20Parser.parse_json(data)
            
            # Valider le message
            try:
                MessageValidator.validate(message)
            except ValidationError as e:
                # Un terminal qui ne recoit aucune reponse retransmet en
                # boucle : on repond toujours, meme sur message rejete
                # (doc section 1, regle 5).
                logger.warning(f"Invalid message: {e.message}")
                # Seules les COMMANDES du terminal appellent un `ret` : repondre
                # a une reponse (`ret`) ferait diverger l'echange.
                #
                # `isinstance` obligatoire : le message peut avoir ete rejete
                # precisement parce qu'il n'est pas un dict (`[]`, `5`, `"reg"`
                # -- et le routing accepte desormais tout chemin). Un `.get()`
                # sur une liste leverait une AttributeError avalee par le
                # `except Exception` englobant, donc aucun `ret` envoye : la
                # retransmission silencieuse que ce bloc vise a supprimer.
                cmd = (
                    str(message.get('cmd') or '').strip().lower()
                    if isinstance(message, dict) else ''
                )
                if cmd:
                    await self._send_json(
                        ResponseBuilder.generic(ret=cmd, success=False, reason=1)
                    )
                return
            
            # Traiter le message
            await self._dispatch(message)
            
            # Métriques
            elapsed = time.perf_counter() - start_time
            self._metrics.record_message(self.sn or 'unknown', 'received')
            self._metrics.record_latency('message', elapsed)
            
            # Toucher le Device Manager
            if self.sn:
                await self._device_manager.touch(self.sn)
            
        except Exception as e:
            logger.exception(f"Error processing message: {e}")
    
    async def _dispatch(self, message: dict):
        """Dispatch le message vers le bon handler"""
        cmd = str(message.get('cmd') or '').strip().lower()
        ret = str(message.get('ret') or '').strip().lower()
        
        if cmd:
            await self._handle_command(cmd, message)
        elif ret:
            await self._handle_response(ret, message)
        else:
            logger.warning(f"Unknown message type: {message.keys()}")
    
    async def _handle_command(self, cmd: str, message: dict):
        """Traite une commande du terminal"""
        handler = self._handlers.get(cmd)
        
        if not handler:
            # Rester muet pousse le terminal a retransmettre indefiniment :
            # la spec attend toujours un `ret` (doc section 1, regle 5).
            logger.warning(f"No handler for command: {cmd}")
            await self._send_json(
                ResponseBuilder.generic(ret=cmd, success=False, reason=1)
            )
            return
        
        # Exécuter le handler
        result: HandlerResult = await handler.handle(
            message,
            terminal=self.terminal,
            sn=self.sn,
            client_ip=self.client_ip,
        )
        
        # Actions post-handler pour reg
        if cmd == 'reg' and result.success:
            self.sn = result.data.get('sn')
            self.terminal = result.data.get('terminal')
            self.registered = True
            
            # Rejoindre le groupe Channels du terminal
            await self.channel_layer.group_add(
                f'terminal_{self.sn}',
                self.channel_name
            )
            logger.info(f"[{self.sn}] Ajouté au groupe Channels terminal_{self.sn}")
            
            # Enregistrer dans le Device Manager
            await self._device_manager.register(
                self.sn,
                self,
                metadata={
                    'model': self.terminal.model if self.terminal else '',
                    'firmware': self.terminal.firmware if self.terminal else '',
                }
            )
            
            # Mettre à jour les métriques
            self._metrics.update_active_connections(
                len(await self._device_manager.get_connected_sns())
            )
            
            # Envoyer les commandes en attente
            await self._send_pending_commands()
        
        # Envoyer la réponse
        if result.response:
            await self._send_json(result.response)
    
    async def _handle_response(self, ret: str, message: dict):
        """Traite une réponse du terminal"""
        result = await self._response_handler.handle(
            message,
            terminal=self.terminal,
            sn=self.sn,
            pagination_state=self._pagination,
        )
        
        # Les reponses ne se repondent pas, sauf les commandes paginees :
        # le handler renvoie alors la demande de page suivante
        # (`{"cmd": X, "stn": false}`, doc section 1.5).
        if result.response:
            await self._send_json(result.response)
    
    async def _send_pending_commands(self):
        """Envoie les commandes en attente"""
        if not self.terminal:
            return
        
        commands = await self._command_service.get_pending(self.terminal)
        
        for cmd in commands:
            try:
                await self._send_json(cmd.payload)
                await self._command_service.mark_sent(cmd.id)
                logger.info(f"[{self.sn}] Command sent: {cmd.command}")
            except Exception as e:
                logger.error(f"Error sending command {cmd.id}: {e}")
    
    async def _heartbeat_loop(self):
        """Sonde applicative de vivacite.

        Ni le transport ni le protocole ne permettent de distinguer un
        terminal inactif d'un terminal mort :

        - les TM20 ne repondent pas aux frames ping WebSocket, d'ou le
          `--ping-timeout 0` des serveurs ASGI (cf. docker-compose.prod.yml) ;
        - le protocole ne definit aucun keep-alive (doc, « Known issues »
          point 16) et un terminal sans pointage n'emet rien de la nuit.

        Se contenter de fermer sur le silence applicatif deconnectait donc un
        terminal parfaitement sain a chaque CONNECTION_TIMEOUT, d'ou une boucle
        de reconnexion. On interroge desormais le terminal avec `gettime`
        (doc section S26), commande inoffensive a laquelle il DOIT repondre :
        sa reponse rafraichit `last_message_at` via `receive()`. La fermeture
        n'intervient que si le silence persiste malgre les sondes.
        """
        timeout = settings.TM20_SETTINGS.get('CONNECTION_TIMEOUT', 120)
        interval = settings.TM20_SETTINGS.get('HEARTBEAT_INTERVAL', 30)

        while True:
            try:
                await asyncio.sleep(interval)

                elapsed = (datetime.now() - self.last_message_at).total_seconds()

                if elapsed > timeout:
                    logger.warning(
                        f"[{self.sn}] Aucune reponse depuis {elapsed:.0f}s "
                        f"malgre les sondes, fermeture de la connexion"
                    )
                    await self._event_bus.emit(
                        EventType.DEVICE_TIMEOUT,
                        {'sn': self.sn},
                        source='TM20Consumer'
                    )
                    await self.close()
                    break

                # Avant `reg`, aucune commande n'a de sens : le terminal doit
                # s'annoncer de lui-meme, le timeout ci-dessus reste le filet.
                if not self.sn or elapsed < interval:
                    continue

                if not self._should_probe(interval):
                    continue

                if not await self._send_liveness_probe():
                    break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

    def _should_probe(self, interval: float) -> bool:
        """Evite d'empiler les sondes tant que la precedente est recente."""
        if self._last_probe_at is None:
            return True
        return (datetime.now() - self._last_probe_at).total_seconds() >= interval

    async def _send_liveness_probe(self) -> bool:
        """Envoie `gettime` au terminal. Retourne False si la socket est morte."""
        self._last_probe_at = datetime.now()
        try:
            await self._send_json(CommandBuilder.gettime())
            logger.debug(f"[{self.sn}] Sonde de vivacite envoyee (gettime)")
            return True
        except Exception as e:
            # L'envoi echoue : la socket est fermee cote reseau, inutile
            # d'attendre l'expiration du timeout applicatif.
            logger.warning(
                f"[{self.sn}] Sonde de vivacite impossible ({e}), "
                f"connexion consideree morte"
            )
            await self._event_bus.emit(
                EventType.DEVICE_TIMEOUT,
                {'sn': self.sn},
                source='TM20Consumer'
            )
            return False
    
    async def _send_json(self, data: dict):
        """Envoie un message JSON au terminal"""
        message = TM20Parser.serialize(data)
        await self.send(text_data=message)
        
        self._metrics.record_message(self.sn or 'unknown', 'sent')
        logger.debug(f"[{self.sn}] Sent: {message[:200]}")
    
    # === API publique pour envoi de commandes ===
    
    async def send_command(self, event: dict):
        """
        Handler pour les messages Channels Layer.
        Appelé quand un message avec type='send_command' est envoyé au groupe.
        
        Args:
            event: Dict contenant 'command' (la commande à envoyer)
        """
        logger.info(f"[{self.sn}] send_command appelé avec event: {event}")
        
        command = event.get('command')
        if not command:
            logger.warning(f"[{self.sn}] send_command appelé sans commande")
            return
        
        try:
            # Extraire et stocker les métadonnées avant envoi
            # Ces métadonnées seront utilisées lors de la réponse du terminal
            user_ids = command.pop('_user_ids', None)
            terminal_id = command.pop('_terminal_id', None)
            
            # Les reponses TM20 ne portent aucun identifiant de correlation :
            # on empile ce qu'on envoie, le terminal repond dans l'ordre.
            cmd_name = command.get('cmd')
            
            # `is not None` et non un test de verite : l'enrollid 0 est une
            # valeur valide (le validateur ne rejette que les negatifs). Le
            # confondre avec une absence enverrait la commande SANS entree
            # dans la file, et toutes les reponses suivantes depileraient
            # alors les metadonnees du mauvais utilisateur.
            if cmd_name == 'setuserinfo' and command.get('enrollid') is not None:
                pending_commands.push(self.sn, 'setuserinfo', {
                    'enrollid': command['enrollid'],
                    'backupnum': command.get('backupnum'),
                    'terminal_id': terminal_id,
                })
            
            elif cmd_name == 'setusername':
                pending_commands.push(self.sn, 'setusername', {
                    'user_ids': user_ids or [],
                    'terminal_id': terminal_id,
                    'enrollids': [
                        u['enrollid'] for u in command.get('record', [])
                        if u.get('enrollid') is not None
                    ],
                })
                logger.info(
                    f"[{self.sn}] Métadonnées empilées: "
                    f"{len(user_ids or [])} utilisateur(s)"
                )
            
            logger.info(
                f"[{self.sn}] Envoi commande via Channels: "
                f"cmd={command.get('cmd')}, enrollid={command.get('enrollid')}, "
                f"name={command.get('name')}"
            )
            await self._send_json(command)
            logger.info(f"[{self.sn}] Commande envoyée avec succès au terminal")
        except Exception as e:
            logger.error(f"[{self.sn}] Erreur envoi commande via Channels: {e}", exc_info=True)

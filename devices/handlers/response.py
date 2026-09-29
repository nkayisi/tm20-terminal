"""
Handler pour les réponses du terminal aux commandes serveur
"""

import logging
from typing import Any, Dict, Optional

from asgiref.sync import sync_to_async

from ..models import Terminal
from ..protocol import TM20Parser
from ..services.commands import CommandService
from ..core.events import EventBus, EventType
from .base import BaseHandler, HandlerResult

logger = logging.getLogger('devices.handlers')


class ResponseHandler(BaseHandler):
    """
    Gère les réponses du terminal (ret)
    """
    
    def __init__(self):
        self._service = CommandService()
        self._event_bus = EventBus.get_instance()
    
    async def handle(
        self,
        message: Dict[str, Any],
        terminal: Optional[Terminal] = None,
        sn: Optional[str] = None,
        **context: Any
    ) -> HandlerResult:
        """Traite une réponse du terminal"""
        
        # Certains firmwares entourent la valeur de `ret` d'espaces
        # (doc section 6.4) : TM20Parser la rogne deja.
        ret = TM20Parser.get_command_type(message) or ''
        result, reason, data = TM20Parser.parse_response_result(message)
        
        logger.info(f"[{sn or 'unknown'}] Response {ret}: {result}")
        
        response = None
        
        # Traiter les réponses spécifiques
        if ret == 'setuserinfo' and terminal:
            await self._handle_setuserinfo_response(message, terminal, result)
        elif ret == 'setusername' and terminal:
            await self._handle_setusername_response(message, terminal, result)
        elif ret in self.PAGINATED_COMMANDS:
            # L'etat de pagination appartient a la connexion qui l'a lancee :
            # le consumer fournit son propre dict (voir _handle_paginated_response).
            response = await self._handle_paginated_response(
                ret, message, terminal, sn, result,
                context.get('pagination_state'),
            )
        
        # Émettre l'événement
        await self._event_bus.emit(
            EventType.COMMAND_RESPONSE,
            {
                'sn': sn,
                'ret': ret,
                'result': result,
                'reason': reason,
                'data': data,
            },
            source='ResponseHandler'
        )
        
        # Seules les commandes paginees appellent une suite (`stn: false`) ;
        # les autres reponses ne se repondent pas.
        return HandlerResult.ok(
            response=response,
            ret=ret,
            result=result,
            data=data
        )
    
    # Commandes dont la reponse arrive par pages : le serveur doit relancer
    # `{"cmd": X, "stn": false}` jusqu'a epuisement (doc section 1.5).
    PAGINATED_COMMANDS = ('getuserlist', 'getnewlog', 'getalllog')

    # La spec ne definit pas la condition d'arret (doc section 6.2-8). Garde-fou
    # contre un terminal qui renverrait indefiniment la meme page.
    MAX_PAGES = 500

    async def _handle_paginated_response(
        self,
        ret: str,
        message: Dict[str, Any],
        terminal: Optional[Terminal],
        sn: Optional[str],
        result: Any,
        state_store: Optional[dict] = None,
    ) -> Optional[Dict[str, Any]]:
        """Persiste une page puis demande la suivante.

        Retourne la commande `stn: false` a envoyer, ou None quand la
        pagination est terminee.

        `state_store` est le dictionnaire d'etat porte par la connexion
        (`TM20ConsumerV2._pagination`). Cet etat a exactement la duree de vie
        de la connexion qui a lance la pagination : le faire transiter par le
        cache Redis partage l'exposait aux evictions (le garde-fou MAX_PAGES
        repartait alors de zero) et melangeait les connexions successives d'un
        meme SN.
        """
        records = message.get('record') or []
        count = message.get('count', 0)
        page_from = message.get('from', 0)
        page_to = message.get('to', 0)

        if state_store is None:
            state_store = {}

        if not result:
            logger.warning(
                f"[{sn}] {ret}: page en echec (reason={message.get('reason')}), "
                f"pagination interrompue"
            )
            state_store.pop(ret, None)
            return None

        if terminal is None:
            # Continuer a demander des pages sans pouvoir les enregistrer fait
            # deverser au terminal tout son historique dans le vide, avec un
            # « pagination terminee (N enregistrements) » mensonger a la fin.
            logger.error(
                f"[{sn}] {ret}: terminal inconnu pour cette connexion "
                f"(reg absent ou perdu), {len(records)} enregistrement(s) "
                f"non persistables -- pagination interrompue"
            )
            state_store.pop(ret, None)
            return None

        if records:
            await self._persist_page(ret, records, terminal)

        state = state_store.setdefault(
            ret, {'pages': 0, 'records': 0, 'page_size': 0}
        )
        state['pages'] += 1
        state['records'] += len(records)
        # La taille de page est celle annoncee par la premiere page pleine.
        if not state['page_size']:
            state['page_size'] = len(records)

        logger.info(
            f"[{sn}] {ret}: page {state['pages']} "
            f"({len(records)} enreg., from={page_from} to={page_to}, count={count}), "
            f"total cumule {state['records']}"
        )

        if self._pagination_done(records, count, page_to, state):
            logger.info(
                f"[{sn}] {ret}: pagination terminee "
                f"({state['records']} enregistrements sur {state['pages']} page(s))"
            )
            state_store.pop(ret, None)
            return None

        return {"cmd": ret, "stn": False}

    def _pagination_done(
        self,
        records: list,
        count: int,
        page_to: int,
        state: dict,
    ) -> bool:
        """Decide s'il reste des pages a demander.

        La spec est muette sur ce point (doc section 6.2-8) : on combine les
        trois signaux disponibles, le premier qui se declenche arrete la
        boucle.
        """
        # 1. Page vide ou jeu de donnees vide : `count: 0` documente le cas.
        if not records or count == 0:
            return True

        # 2. `count` vaut parfois le TOTAL et non la taille de page
        #    (doc section 6.1-3) : `to` atteint alors la derniere ligne.
        if count > len(records) and page_to + 1 >= count:
            return True

        # 3. Page plus courte que les precedentes : derniere page.
        if state['page_size'] and len(records) < state['page_size']:
            return True

        # 4. Garde-fou.
        if state['pages'] >= self.MAX_PAGES:
            logger.error(
                f"Pagination interrompue apres {self.MAX_PAGES} pages "
                f"(garde-fou) : le terminal ne signale pas la fin"
            )
            return True

        return False

    async def _persist_page(
        self,
        ret: str,
        records: list,
        terminal: Terminal,
    ) -> None:
        """Enregistre les donnees d'une page selon la commande d'origine."""
        if ret == 'getuserlist':
            await self._persist_userlist_page(records, terminal)
        else:
            await self._persist_log_page(records, terminal)

    @staticmethod
    @sync_to_async
    def _persist_userlist_page(records: list, terminal: Terminal) -> None:
        """Cree/complete les utilisateurs listes par le terminal.

        Chaque enregistrement de `getuserlist` decrit UN credential : un
        utilisateur a plusieurs empreintes apparait plusieurs fois
        (doc section S1). On ne recoit pas le gabarit ici, seulement sa
        presence.
        """
        from ..models import BiometricCredential, BiometricUser

        for rec in records:
            enrollid = rec.get('enrollid')
            if enrollid is None:
                continue

            user, _ = BiometricUser.objects.get_or_create(
                terminal=terminal,
                enrollid=enrollid,
                defaults={'admin': rec.get('admin', 0)},
            )

            backupnum = rec.get('backupnum')
            if backupnum is not None:
                BiometricCredential.objects.get_or_create(
                    user=user,
                    backupnum=backupnum,
                    defaults={'record': ''},
                )

    async def _persist_log_page(self, records: list, terminal: Terminal) -> None:
        """Enregistre une page de logs via le service de pointage.

        On reutilise AttendanceService pour beneficier de la deduplication,
        de l'alternance entree/sortie et des evenements temps reel, au lieu
        de dupliquer cette logique.
        """
        from ..protocol import TM20Parser
        from ..services.attendance import AttendanceService

        log_msg = TM20Parser.parse_sendlog({
            'sn': terminal.sn,
            'count': len(records),
            'record': records,
        })
        await AttendanceService().process_logs(terminal, log_msg)

    async def _handle_setuserinfo_response(
        self,
        message: Dict[str, Any],
        terminal: Terminal,
        result: str
    ) -> None:
        """
        Traite la réponse setuserinfo du terminal.
        Marque l'utilisateur comme synchronisé si succès.
        """
        from django.utils import timezone
        from ..models import BiometricUser
        from ..services import pending_commands
        
        # La reponse documentee (doc section S3) est `{"ret":"setuserinfo",
        # "result":true}` : elle ne porte PAS d'enrollid. On depile donc la
        # commande correspondante, le terminal repondant dans l'ordre d'envoi.
        pending = pending_commands.pop(terminal.sn, 'setuserinfo')
        # Tests `is None` explicites : l'enrollid 0 est une valeur valide, un
        # test de verite le confondrait avec une absence de correlation.
        enrollid = message.get('enrollid')
        if enrollid is None:
            enrollid = (pending or {}).get('enrollid')

        if enrollid is None:
            logger.warning(
                f"Réponse setuserinfo sans enrollid et sans commande en "
                f"attente pour {terminal.sn}: {message}"
            )
            return
        
        if result is True or result == 'ok':
            # Marquer l'utilisateur comme synchronisé
            @sync_to_async
            def mark_user_synced():
                try:
                    user = BiometricUser.objects.get(
                        terminal=terminal,
                        enrollid=enrollid
                    )
                    user.sync_status = 'synced_to_terminal'
                    user.last_synced_at = timezone.now()
                    user.save(update_fields=['sync_status', 'last_synced_at', 'updated_at'])
                    logger.info(
                        f"Utilisateur {enrollid} marqué comme synchronisé "
                        f"sur terminal {terminal.sn}"
                    )
                except BiometricUser.DoesNotExist:
                    logger.warning(
                        f"Utilisateur {enrollid} introuvable pour terminal {terminal.sn}"
                    )
            
            await mark_user_synced()
        else:
            # Marquer comme erreur
            @sync_to_async
            def mark_user_error():
                try:
                    user = BiometricUser.objects.get(
                        terminal=terminal,
                        enrollid=enrollid
                    )
                    user.sync_status = 'error'
                    user.save(update_fields=['sync_status', 'updated_at'])
                    logger.error(
                        f"Erreur synchronisation utilisateur {enrollid} "
                        f"sur terminal {terminal.sn}: {result}"
                    )
                except BiometricUser.DoesNotExist:
                    logger.warning(
                        f"Utilisateur {enrollid} introuvable pour terminal {terminal.sn}"
                    )
            
            await mark_user_error()
    
    async def _handle_setusername_response(
        self,
        message: Dict[str, Any],
        terminal: Terminal,
        result: str
    ) -> None:
        """
        Traite la réponse setusername du terminal.
        Marque les utilisateurs comme synchronisés si succès.
        
        Note: Les métadonnées (_user_ids) sont stockées dans le cache Redis
        lors de l'envoi de la commande et récupérées ici.
        """
        from django.utils import timezone
        from ..models import BiometricUser
        from ..services import pending_commands
        
        # Depiler la plus ancienne commande non repondue : plusieurs paquets
        # `setusername` peuvent etre en vol (limite de 50 par paquet, S6).
        pending = pending_commands.pop(terminal.sn, 'setusername')
        
        user_ids = None
        enrollids = None
        
        if pending:
            user_ids = pending.get('user_ids') or []
            enrollids = pending.get('enrollids') or []
            logger.info(
                f"Métadonnées dépilées pour {terminal.sn}: "
                f"{len(user_ids)} utilisateur(s) (IDs: {user_ids})"
            )
        else:
            # Repli : la reponse documentee ne contient pas `record`, mais
            # certains firmwares le renvoient en echo.
            record = message.get('record', [])
            logger.warning(
                f"Réponse setusername sans commande en attente pour "
                f"{terminal.sn}, repli sur record ({len(record)} utilisateurs)"
            )
            enrollids = [u.get('enrollid') for u in record if u.get('enrollid')]
        
        if result is True or result == 'ok':
            # Marquer tous les utilisateurs comme synchronisés
            @sync_to_async
            def mark_users_synced():
                if user_ids:
                    # Marquer par IDs (méthode préférée)
                    count = BiometricUser.objects.filter(
                        id__in=user_ids,
                        terminal=terminal
                    ).update(
                        sync_status='synced_to_terminal',
                        last_synced_at=timezone.now()
                    )
                    logger.info(
                        f"{count} utilisateurs marqués comme synchronisés "
                        f"sur terminal {terminal.sn} (IDs: {user_ids})"
                    )
                elif enrollids:
                    # Fallback: marquer par enrollid
                    count = BiometricUser.objects.filter(
                        terminal=terminal,
                        enrollid__in=enrollids
                    ).update(
                        sync_status='synced_to_terminal',
                        last_synced_at=timezone.now()
                    )
                    logger.info(
                        f"{count} utilisateurs marqués comme synchronisés "
                        f"sur terminal {terminal.sn} (enrollids: {enrollids})"
                    )
            
            await mark_users_synced()
        else:
            # Marquer comme erreur
            @sync_to_async
            def mark_users_error():
                if user_ids:
                    count = BiometricUser.objects.filter(
                        id__in=user_ids,
                        terminal=terminal
                    ).update(sync_status='error')
                    logger.error(
                        f"{count} utilisateurs marqués en erreur "
                        f"sur terminal {terminal.sn}: {result}"
                    )
                elif enrollids:
                    count = BiometricUser.objects.filter(
                        terminal=terminal,
                        enrollid__in=enrollids
                    ).update(sync_status='error')
                    logger.error(
                        f"{count} utilisateurs marqués en erreur "
                        f"sur terminal {terminal.sn}: {result}"
                    )
            
            await mark_users_error()

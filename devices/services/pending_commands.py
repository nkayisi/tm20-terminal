"""
Corrélation des commandes en attente de réponse.

Le protocole TM20 ne porte aucun identifiant de corrélation : la réponse à
`setusername` est un simple `{"ret":"setusername","result":true}` et celle à
`setuserinfo` ne contient même pas l'`enrollid` (doc sections S3 et S6). Pour
savoir quels utilisateurs une réponse valide, le serveur doit mémoriser ce
qu'il a envoyé.

Les terminaux répondent dans l'ordre d'arrivée : une file FIFO par
(terminal, commande) suffit. Une clé unique par terminal ne suffisait pas --
l'envoi de plusieurs paquets `setusername` d'affilée écrasait les
métadonnées du précédent, et seuls les utilisateurs du dernier paquet
étaient marqués comme synchronisés.
"""

import logging
from typing import Any, Dict, List, Optional

from django.core.cache import cache

logger = logging.getLogger('devices.services')

# Duree de vie d'une entree en attente. Au-dela, on considere que le terminal
# ne repondra pas (deconnexion, redemarrage) et l'entree est abandonnee.
TTL_SECONDS = 300

# Garde-fou : un terminal muet ne doit pas faire gonfler la file indefiniment.
MAX_PENDING = 100


def _key(sn: str, command: str) -> str:
    return f'pending_cmd:{sn}:{command}'


def push(sn: str, command: str, metadata: Dict[str, Any]) -> None:
    """Mémorise les métadonnées d'une commande envoyée."""
    if not sn:
        return

    key = _key(sn, command)
    queue: List[dict] = cache.get(key) or []
    queue.append(metadata)

    if len(queue) > MAX_PENDING:
        dropped = len(queue) - MAX_PENDING
        queue = queue[-MAX_PENDING:]
        logger.warning(
            f"[{sn}] File {command} saturée : {dropped} entrée(s) abandonnée(s)"
        )

    cache.set(key, queue, timeout=TTL_SECONDS)


def pop(sn: str, command: str) -> Optional[Dict[str, Any]]:
    """Récupère les métadonnées de la plus ancienne commande non répondue."""
    if not sn:
        return None

    key = _key(sn, command)
    queue: List[dict] = cache.get(key) or []
    if not queue:
        return None

    metadata = queue.pop(0)
    if queue:
        cache.set(key, queue, timeout=TTL_SECONDS)
    else:
        cache.delete(key)
    return metadata


def clear(sn: str, command: str = None) -> None:
    """Vide la file d'un terminal (à sa déconnexion : plus rien n'arrivera)."""
    if not sn:
        return
    commands = [command] if command else ('setusername', 'setuserinfo')
    for cmd in commands:
        cache.delete(_key(sn, cmd))

"""
Gestion du temps « côté terminal ».

Les terminaux TM20 émettent et attendent des horodatages en heure murale
locale (format "%Y-%m-%d %H:%M:%S", sans information de fuseau). Ce module
centralise la conversion entre ces horodatages naïfs et les datetimes
timezone-aware utilisés en base (USE_TZ=True).

Le fuseau appliqué est ``TM20_SETTINGS['TERMINAL_TIMEZONE']`` s'il est défini,
sinon le ``TIME_ZONE`` du projet. Par défaut, le comportement est donc
identique à l'ancien code (interprétation en UTC), mais l'offset devient
corrigible via la variable d'environnement ``TM20_TERMINAL_TIMEZONE``.
"""

import zoneinfo

from django.conf import settings
from django.utils import timezone

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def terminal_timezone() -> zoneinfo.ZoneInfo:
    """Fuseau horaire dans lequel les terminaux expriment l'heure."""
    tz_name = settings.TM20_SETTINGS.get('TERMINAL_TIMEZONE') or settings.TIME_ZONE
    return zoneinfo.ZoneInfo(tz_name)


def terminal_now_str(fmt: str = TIME_FORMAT) -> str:
    """Heure actuelle formatée à envoyer aux terminaux (cloudtime/settime)."""
    return timezone.now().astimezone(terminal_timezone()).strftime(fmt)


def make_terminal_aware(dt):
    """Rend aware un datetime naïf reçu d'un terminal (heure murale locale).

    Retourne ``dt`` inchangé s'il est None ou déjà aware.
    """
    if dt is None or timezone.is_aware(dt):
        return dt
    return dt.replace(tzinfo=terminal_timezone())


def to_terminal_time(dt):
    """Ramène un datetime aware à l'heure murale du terminal.

    Opération inverse de :func:`make_terminal_aware` : la base restitue de
    l'UTC (``USE_TZ=True``), or un destinataire extérieur attend l'heure que
    l'agent a lue sur l'écran du terminal. Le datetime reste aware, l'offset
    voyage donc avec la valeur (``2024-01-15T10:30:00+01:00``) : le récepteur
    peut recalculer l'instant s'il le souhaite, mais n'a rien à deviner s'il se
    contente de lire les chiffres.

    Retourne ``dt`` inchangé s'il est None.
    """
    if dt is None:
        return dt
    return dt.astimezone(terminal_timezone())

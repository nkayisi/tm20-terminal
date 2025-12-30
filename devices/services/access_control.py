"""
Service de contrôle d'accès
"""

import logging
from typing import Tuple

from asgiref.sync import sync_to_async
from django.utils import timezone

from ..models import BiometricUser, Terminal

logger = logging.getLogger('devices.services')


class AccessControlService:
    """
    Service de vérification des droits d'accès
    """
    
    @sync_to_async
    def check_user_access(
        self,
        terminal: Terminal,
        enrollid: int
    ) -> Tuple[bool, str]:
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
                return False, "User disabled"
            
            now = timezone.now()
            
            if user.starttime and now < user.starttime:
                return False, "Access not yet valid"
            
            if user.endtime and now > user.endtime:
                return False, "Access expired"
            
            return True, "Access granted"
            
        except BiometricUser.DoesNotExist:
            # Par défaut, on autorise les utilisateurs inconnus
            return True, "User not found in database"
    
    @sync_to_async
    def check_qrcode_access(
        self,
        terminal: Terminal,
        qrcode: str
    ) -> Tuple[bool, int, str, str]:
        """
        Vérifie l'accès par QR code
        Retourne (access_granted, enrollid, username, message)
        """
        try:
            # Tenter de parser l'enrollid depuis le QR code
            enrollid = int(qrcode)
            
            user = BiometricUser.objects.get(
                terminal=terminal,
                enrollid=enrollid
            )
            
            if not user.is_enabled:
                return False, enrollid, user.name, "User disabled"
            
            now = timezone.now()
            
            if user.starttime and now < user.starttime:
                return False, enrollid, user.name, "Access not yet valid"
            
            if user.endtime and now > user.endtime:
                return False, enrollid, user.name, "Access expired"
            
            return True, enrollid, user.name, "Access granted"
            
        except ValueError:
            return False, 0, "", "Invalid QR code format"
        except BiometricUser.DoesNotExist:
            return False, 0, "", "User not found"


# Instance par défaut
access_control_service = AccessControlService()

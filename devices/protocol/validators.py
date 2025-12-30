"""
Validateurs pour les messages du protocole TM20
"""

import logging
from typing import Any, Dict, List, Optional, Set

from .types import CommandType

logger = logging.getLogger('devices.protocol')


class ValidationError(Exception):
    """Erreur de validation du protocole"""
    def __init__(self, message: str, field: str = None, code: str = None):
        self.message = message
        self.field = field
        self.code = code or 'VALIDATION_ERROR'
        super().__init__(message)


class MessageValidator:
    """
    Validateur de messages TM20
    Vérifie la structure et le contenu des messages
    """
    
    # Commandes valides
    VALID_COMMANDS: Set[str] = {cmd.value for cmd in CommandType}
    
    # Champs requis par commande
    REQUIRED_FIELDS: Dict[str, List[str]] = {
        'reg': ['sn'],
        'sendlog': ['sn', 'count', 'record'],
        'senduser': ['enrollid', 'backupnum'],
        'sendqrcode': ['sn', 'record'],
    }
    
    # Valeurs valides pour certains champs
    VALID_ADMIN_LEVELS = {0, 1, 2}
    VALID_BACKUP_NUMS = set(range(0, 12)) | set(range(20, 28)) | set(range(30, 38)) | {50}
    VALID_MODES = {0, 1, 2, 3, 8, 13}
    VALID_INOUT = {0, 1}
    
    @classmethod
    def validate(cls, message: Dict[str, Any]) -> bool:
        """
        Valide un message complet
        Lève ValidationError si invalide
        """
        if not isinstance(message, dict):
            raise ValidationError("Message must be a dictionary", code='INVALID_TYPE')
        
        # Déterminer le type de message
        cmd = message.get('cmd', '').lower()
        ret = message.get('ret', '').lower()
        
        if not cmd and not ret:
            raise ValidationError(
                "Message must have 'cmd' or 'ret' field",
                code='MISSING_COMMAND'
            )
        
        if cmd:
            return cls._validate_command(cmd, message)
        else:
            return cls._validate_response(ret, message)
    
    @classmethod
    def _validate_command(cls, cmd: str, message: Dict[str, Any]) -> bool:
        """Valide une commande entrante"""
        
        # Vérifier les champs requis
        if cmd in cls.REQUIRED_FIELDS:
            for field in cls.REQUIRED_FIELDS[cmd]:
                if field not in message:
                    raise ValidationError(
                        f"Missing required field: {field}",
                        field=field,
                        code='MISSING_FIELD'
                    )
        
        # Validations spécifiques
        validators = {
            'reg': cls._validate_reg,
            'sendlog': cls._validate_sendlog,
            'senduser': cls._validate_senduser,
            'sendqrcode': cls._validate_sendqrcode,
        }
        
        if cmd in validators:
            validators[cmd](message)
        
        return True
    
    @classmethod
    def _validate_response(cls, ret: str, message: Dict[str, Any]) -> bool:
        """Valide une réponse"""
        # Les réponses doivent avoir 'result'
        if 'result' not in message:
            raise ValidationError(
                "Response must have 'result' field",
                field='result',
                code='MISSING_RESULT'
            )
        return True
    
    @classmethod
    def _validate_reg(cls, message: Dict[str, Any]) -> None:
        """Valide un message reg"""
        sn = message.get('sn', '')
        
        if not sn:
            raise ValidationError(
                "SN cannot be empty",
                field='sn',
                code='EMPTY_SN'
            )
        
        if len(sn) < 5 or len(sn) > 50:
            raise ValidationError(
                f"SN length must be between 5 and 50 characters",
                field='sn',
                code='INVALID_SN_LENGTH'
            )
        
        # Valider devinfo si présent
        devinfo = message.get('devinfo', {})
        if devinfo:
            cls._validate_devinfo(devinfo)
    
    @classmethod
    def _validate_devinfo(cls, devinfo: Dict[str, Any]) -> None:
        """Valide les informations du terminal"""
        # Vérifier les capacités
        for field in ['usersize', 'fpsize', 'cardsize', 'logsize']:
            if field in devinfo:
                value = devinfo[field]
                if not isinstance(value, int) or value < 0:
                    raise ValidationError(
                        f"{field} must be a positive integer",
                        field=f'devinfo.{field}',
                        code='INVALID_CAPACITY'
                    )
    
    @classmethod
    def _validate_sendlog(cls, message: Dict[str, Any]) -> None:
        """Valide un message sendlog"""
        records = message.get('record', [])
        
        if not isinstance(records, list):
            raise ValidationError(
                "record must be a list",
                field='record',
                code='INVALID_RECORD_TYPE'
            )
        
        count = message.get('count', 0)
        if count != len(records):
            logger.warning(f"sendlog count mismatch: {count} vs {len(records)}")
        
        # Valider chaque enregistrement
        for i, rec in enumerate(records):
            cls._validate_log_record(rec, i)
    
    @classmethod
    def _validate_log_record(cls, record: Dict[str, Any], index: int) -> None:
        """Valide un enregistrement de log"""
        if 'enrollid' not in record:
            raise ValidationError(
                f"Log record {index} missing enrollid",
                field=f'record[{index}].enrollid',
                code='MISSING_ENROLLID'
            )
        
        if 'time' not in record:
            raise ValidationError(
                f"Log record {index} missing time",
                field=f'record[{index}].time',
                code='MISSING_TIME'
            )
        
        # Valider le mode
        mode = record.get('mode', 0)
        if mode not in cls.VALID_MODES:
            logger.warning(f"Unknown verify mode: {mode}")
        
        # Valider inout
        inout = record.get('inout', 0)
        if inout not in cls.VALID_INOUT:
            logger.warning(f"Unknown inout value: {inout}")
    
    @classmethod
    def _validate_senduser(cls, message: Dict[str, Any]) -> None:
        """Valide un message senduser"""
        enrollid = message.get('enrollid', 0)
        
        if enrollid < 0:
            raise ValidationError(
                "enrollid must be positive",
                field='enrollid',
                code='INVALID_ENROLLID'
            )
        
        backupnum = message.get('backupnum', 0)
        if backupnum not in cls.VALID_BACKUP_NUMS:
            raise ValidationError(
                f"Invalid backupnum: {backupnum}",
                field='backupnum',
                code='INVALID_BACKUPNUM'
            )
        
        admin = message.get('admin', 0)
        if admin not in cls.VALID_ADMIN_LEVELS:
            raise ValidationError(
                f"Invalid admin level: {admin}",
                field='admin',
                code='INVALID_ADMIN'
            )
    
    @classmethod
    def _validate_sendqrcode(cls, message: Dict[str, Any]) -> None:
        """Valide un message sendqrcode"""
        record = message.get('record', '')
        
        if not record:
            raise ValidationError(
                "QR code record cannot be empty",
                field='record',
                code='EMPTY_QRCODE'
            )
    
    @classmethod
    def is_valid(cls, message: Dict[str, Any]) -> bool:
        """Vérifie si un message est valide (sans lever d'exception)"""
        try:
            return cls.validate(message)
        except ValidationError:
            return False

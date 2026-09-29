"""
Parser pour les messages du protocole TM20 v2.4
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional, Union

import orjson

from .types import (
    DeviceInfo,
    LogRecord,
    RegisterMessage,
    SendLogMessage,
    SendUserMessage,
    QRCodeMessage,
)

logger = logging.getLogger('devices.protocol')


class ParseError(Exception):
    """Erreur de parsing du protocole"""
    pass


class TM20Parser:
    """
    Parser stateless pour les messages TM20
    Toutes les méthodes sont statiques pour faciliter les tests
    """
    
    @staticmethod
    def parse_json(data: Union[bytes, str]) -> Dict[str, Any]:
        """Parse le JSON brut"""
        try:
            if isinstance(data, bytes):
                return orjson.loads(data)
            return orjson.loads(data.encode('utf-8'))
        except orjson.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            raise ParseError(f"Invalid JSON: {e}")
    
    @staticmethod
    def serialize(data: Dict[str, Any]) -> str:
        """Sérialise en JSON"""
        return orjson.dumps(data).decode('utf-8')
    
    @staticmethod
    def get_command_type(message: Dict[str, Any]) -> Optional[str]:
        """Extrait le type de commande (cmd ou ret).

        Les terminaux reels emettent parfois des valeurs entourees d'espaces
        (doc section 6.4, ex: `"ret": " getuserinfo "`) : on les rogne.
        """
        raw = message.get('cmd') or message.get('ret') or ''
        return str(raw).strip().lower() or None
    
    @staticmethod
    def is_response(message: Dict[str, Any]) -> bool:
        """Vérifie si c'est une réponse (ret) ou une commande (cmd)"""
        return 'ret' in message
    
    @staticmethod
    def parse_register(message: Dict[str, Any]) -> RegisterMessage:
        """Parse un message d'enregistrement (reg)"""
        devinfo_data = message.get('devinfo', {})
        
        devinfo = DeviceInfo(
            modelname=devinfo_data.get('modelname', ''),
            usersize=devinfo_data.get('usersize', 3000),
            fpsize=devinfo_data.get('fpsize', 3000),
            cardsize=devinfo_data.get('cardsize', 3000),
            pwdsize=devinfo_data.get('pwdsize', 3000),
            logsize=devinfo_data.get('logsize', 100000),
            useduser=devinfo_data.get('useduser', 0),
            usedfp=devinfo_data.get('usedfp', 0),
            usedcard=devinfo_data.get('usedcard', 0),
            usedpwd=devinfo_data.get('usedpwd', 0),
            usedlog=devinfo_data.get('usedlog', 0),
            usednewlog=devinfo_data.get('usednewlog', 0),
            fpalgo=devinfo_data.get('fpalgo', ''),
            firmware=devinfo_data.get('firmware', ''),
            time=devinfo_data.get('time', ''),
            mac=devinfo_data.get('mac', ''),
        ) if devinfo_data else None
        
        return RegisterMessage(
            sn=message.get('sn', ''),
            cpusn=message.get('cpusn', ''),
            devinfo=devinfo,
        )
    
    @staticmethod
    def parse_sendlog(message: Dict[str, Any]) -> SendLogMessage:
        """Parse un message sendlog"""
        records = []
        
        for rec in message.get('record', []):
            records.append(LogRecord(
                enrollid=rec.get('enrollid', 0),
                time=rec.get('time', ''),
                mode=rec.get('mode', 0),
                inout=rec.get('inout', 0),
                event=rec.get('event', 0),
                temp=rec.get('temp'),
                verifymode=rec.get('verifymode'),
                image=rec.get('image', ''),
            ))
        
        return SendLogMessage(
            sn=message.get('sn', ''),
            count=message.get('count', 0),
            logindex=message.get('logindex', 0),
            records=records,
        )
    
    @staticmethod
    def parse_senduser(message: Dict[str, Any]) -> SendUserMessage:
        """Parse un message senduser"""
        return SendUserMessage(
            enrollid=message.get('enrollid', 0),
            name=message.get('name', ''),
            backupnum=message.get('backupnum', 0),
            admin=message.get('admin', 0),
            record=message.get('record'),
        )
    
    @staticmethod
    def parse_sendqrcode(message: Dict[str, Any]) -> QRCodeMessage:
        """Parse un message sendqrcode"""
        return QRCodeMessage(
            sn=message.get('sn', ''),
            record=message.get('record', ''),
        )
    
    # Formats acceptes, du plus courant au plus permissif. Le second couvre
    # les dates sans zero de tete ("2018-11-1", doc section 6.2-18) et les
    # horodatages sans les secondes, vus sur certains firmwares.
    DATETIME_FORMATS = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    )

    @staticmethod
    def parse_datetime(time_str: str) -> Optional[datetime]:
        """Parse une date/heure du protocole TM20.

        Les valeurs recues peuvent etre entourees d'espaces (doc section 6.4)
        et les dates non paddees ("2018-11-1") : strptime accepte deja les
        composants non paddes, il suffit de rogner la chaine.
        """
        if not time_str:
            return None

        cleaned = str(time_str).strip()
        if not cleaned:
            return None

        for fmt in TM20Parser.DATETIME_FORMATS:
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue

        logger.warning(f"Invalid datetime format: {time_str!r}")
        return None
    
    @staticmethod
    def format_datetime(dt: datetime = None) -> str:
        """Formate une datetime pour le protocole TM20"""
        if dt is None:
            dt = datetime.now()
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    
    @staticmethod
    def parse_response_result(message: Dict[str, Any]) -> tuple:
        """
        Parse le résultat d'une réponse
        Retourne (success: bool, reason: Optional[int], data: dict)
        """
        result = message.get('result', False)
        reason = message.get('reason') if not result else None
        
        # Extraire les données additionnelles
        data = {k: v for k, v in message.items() 
                if k not in ('ret', 'result', 'reason')}
        
        return result, reason, data

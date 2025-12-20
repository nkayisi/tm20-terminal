"""
Protocole WebSocket + JSON v2.4 pour terminaux TM20-WIFI
Parsing, validation et construction des messages
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import orjson

logger = logging.getLogger('devices')


class ProtocolError(Exception):
    """Erreur de protocole TM20"""
    pass


class CommandType(str, Enum):
    """Commandes supportées par le protocole TM20"""
    
    # Terminal -> Serveur
    REG = "reg"
    SENDLOG = "sendlog"
    SENDUSER = "senduser"
    
    # Serveur -> Terminal
    GETUSERLIST = "getuserlist"
    GETUSERINFO = "getuserinfo"
    SETUSERINFO = "setuserinfo"
    DELETEUSER = "deleteuser"
    GETUSERNAME = "getusername"
    SETUSERNAME = "setusername"
    ENABLEUSER = "enableuser"
    GETNEWLOG = "getnewlog"
    GETALLLOG = "getalllog"
    CLEANLOG = "cleanlog"
    CLEANUSER = "cleanuser"
    SETTIME = "settime"
    GETTIME = "gettime"
    OPENDOOR = "opendoor"
    REBOOT = "reboot"
    GETDEVINFO = "getdevinfo"
    GETDEVLOCK = "getdevlock"
    SETDEVLOCK = "setdevlock"
    GETUSERLOCK = "getuserlock"
    SETUSERLOCK = "setuserlock"
    DELETEUSERLOCK = "deleteuserlock"
    CLEANUSERLOCK = "cleanuserlock"
    SENDQRCODE = "sendqrcode"
    GETQUESTIONNAIRE = "getquestionnaire"
    SETQUESTIONNAIRE = "setquestionnaire"
    GETHOLIDAY = "getholiday"
    SETHOLIDAY = "setholiday"


@dataclass
class DeviceInfo:
    """Informations du terminal"""
    modelname: str = ""
    usersize: int = 3000
    fpsize: int = 3000
    cardsize: int = 3000
    pwdsize: int = 3000
    logsize: int = 100000
    useduser: int = 0
    usedfp: int = 0
    usedcard: int = 0
    usedpwd: int = 0
    usedlog: int = 0
    usednewlog: int = 0
    fpalgo: str = ""
    firmware: str = ""
    time: str = ""
    mac: str = ""


@dataclass
class RegisterMessage:
    """Message d'enregistrement du terminal"""
    cmd: str
    sn: str
    cpusn: str = ""
    devinfo: Optional[DeviceInfo] = None


@dataclass
class LogRecord:
    """Enregistrement de log de pointage"""
    enrollid: int
    time: str
    mode: int = 0
    inout: int = 0
    event: int = 0
    temp: Optional[float] = None
    verifymode: Optional[int] = None
    image: str = ""


@dataclass
class SendLogMessage:
    """Message d'envoi de logs"""
    cmd: str
    sn: str
    count: int
    logindex: int = 0
    record: list = field(default_factory=list)


@dataclass
class UserRecord:
    """Enregistrement utilisateur"""
    enrollid: int
    name: str = ""
    backupnum: int = 0
    admin: int = 0
    record: Any = None


@dataclass
class SendUserMessage:
    """Message d'envoi utilisateur depuis terminal"""
    cmd: str
    enrollid: int
    name: str = ""
    backupnum: int = 0
    admin: int = 0
    record: Any = None


class TM20Protocol:
    """Gestionnaire du protocole TM20 WebSocket + JSON"""
    
    VALID_COMMANDS = {cmd.value for cmd in CommandType}
    
    @staticmethod
    def parse_message(data: bytes | str) -> dict:
        """Parse un message JSON du terminal"""
        try:
            if isinstance(data, bytes):
                return orjson.loads(data)
            return orjson.loads(data.encode())
        except orjson.JSONDecodeError as e:
            logger.error(f"Erreur parsing JSON: {e}")
            raise ProtocolError(f"JSON invalide: {e}")
    
    @staticmethod
    def serialize_message(data: dict) -> str:
        """Sérialise un message pour envoi au terminal"""
        return orjson.dumps(data).decode()
    
    @staticmethod
    def validate_message(message: dict) -> bool:
        """Valide la structure d'un message"""
        if not isinstance(message, dict):
            return False
        
        # Message entrant (terminal -> serveur)
        if 'cmd' in message:
            cmd = message.get('cmd', '').lower()
            if cmd == 'reg':
                return 'sn' in message
            elif cmd == 'sendlog':
                return all(k in message for k in ['sn', 'count', 'record'])
            elif cmd == 'senduser':
                return all(k in message for k in ['enrollid', 'backupnum'])
            return True
        
        # Message de réponse (ret)
        if 'ret' in message:
            return True
        
        return False
    
    @staticmethod
    def get_command_type(message: dict) -> Optional[str]:
        """Extrait le type de commande d'un message"""
        return message.get('cmd') or message.get('ret')
    
    @staticmethod
    def parse_register(message: dict) -> RegisterMessage:
        """Parse un message d'enregistrement"""
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
        )
        
        return RegisterMessage(
            cmd=message.get('cmd', 'reg'),
            sn=message.get('sn', ''),
            cpusn=message.get('cpusn', ''),
            devinfo=devinfo,
        )
    
    @staticmethod
    def parse_sendlog(message: dict) -> SendLogMessage:
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
            cmd=message.get('cmd', 'sendlog'),
            sn=message.get('sn', ''),
            count=message.get('count', 0),
            logindex=message.get('logindex', 0),
            record=records,
        )
    
    @staticmethod
    def parse_senduser(message: dict) -> SendUserMessage:
        """Parse un message senduser"""
        return SendUserMessage(
            cmd=message.get('cmd', 'senduser'),
            enrollid=message.get('enrollid', 0),
            name=message.get('name', ''),
            backupnum=message.get('backupnum', 0),
            admin=message.get('admin', 0),
            record=message.get('record'),
        )
    
    @staticmethod
    def build_reg_response(
        success: bool,
        cloudtime: Optional[str] = None,
        nosenduser: bool = True,
        reason: str = ""
    ) -> dict:
        """Construit la réponse à un message reg"""
        if success:
            return {
                "ret": "reg",
                "result": True,
                "cloudtime": cloudtime or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "nosenduser": nosenduser,
            }
        return {
            "ret": "reg",
            "result": False,
            "reason": reason,
        }
    
    @staticmethod
    def build_sendlog_response(
        success: bool,
        count: int = 0,
        logindex: int = 0,
        access: int = 1,
        message: str = ""
    ) -> dict:
        """Construit la réponse à un message sendlog"""
        if success:
            resp = {
                "ret": "sendlog",
                "result": True,
                "count": count,
                "logindex": logindex,
                "cloudtime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "access": access,
            }
            if message:
                resp["message"] = message
            return resp
        return {
            "ret": "sendlog",
            "result": False,
            "reason": 1,
        }
    
    @staticmethod
    def build_senduser_response(success: bool) -> dict:
        """Construit la réponse à un message senduser"""
        if success:
            return {
                "ret": "senduser",
                "result": True,
                "cloudtime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        return {
            "ret": "senduser",
            "result": False,
            "reason": 1,
        }
    
    @staticmethod
    def build_getuserlist_command(stn: bool = True) -> dict:
        """Construit la commande getuserlist"""
        return {
            "cmd": "getuserlist",
            "stn": stn,
        }
    
    @staticmethod
    def build_setuserinfo_command(
        enrollid: int,
        name: str,
        backupnum: int,
        admin: int,
        record: Any
    ) -> dict:
        """Construit la commande setuserinfo"""
        return {
            "cmd": "setuserinfo",
            "enrollid": enrollid,
            "name": name,
            "backupnum": backupnum,
            "admin": admin,
            "record": record,
        }
    
    @staticmethod
    def build_deleteuser_command(enrollid: int, backupnum: int = 13) -> dict:
        """
        Construit la commande deleteuser
        backupnum: 0-9=fp, 10=pwd, 11=card, 12=all fp, 13=all
        """
        return {
            "cmd": "deleteuser",
            "enrollid": enrollid,
            "backupnum": backupnum,
        }
    
    @staticmethod
    def build_enableuser_command(enrollid: int, enable: bool = True) -> dict:
        """Construit la commande enableuser"""
        return {
            "cmd": "enableuser",
            "enrollid": enrollid,
            "enflag": 1 if enable else 0,
        }
    
    @staticmethod
    def build_opendoor_command(door: int = 1, delay: int = 5) -> dict:
        """Construit la commande opendoor"""
        return {
            "cmd": "opendoor",
            "door": door,
            "delay": delay,
        }
    
    @staticmethod
    def build_settime_command(time_str: Optional[str] = None) -> dict:
        """Construit la commande settime"""
        if time_str is None:
            time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return {
            "cmd": "settime",
            "cloudtime": time_str,
        }
    
    @staticmethod
    def build_gettime_command() -> dict:
        """Construit la commande gettime"""
        return {"cmd": "gettime"}
    
    @staticmethod
    def build_getnewlog_command(stn: bool = True) -> dict:
        """Construit la commande getnewlog"""
        return {
            "cmd": "getnewlog",
            "stn": stn,
        }
    
    @staticmethod
    def build_reboot_command() -> dict:
        """Construit la commande reboot"""
        return {"cmd": "reboot"}
    
    @staticmethod
    def build_getdevinfo_command() -> dict:
        """Construit la commande getdevinfo"""
        return {"cmd": "getdevinfo"}
    
    @staticmethod
    def build_cleanlog_command() -> dict:
        """Construit la commande cleanlog"""
        return {"cmd": "cleanlog"}
    
    @staticmethod
    def build_cleanuser_command() -> dict:
        """Construit la commande cleanuser"""
        return {"cmd": "cleanuser"}
    
    @staticmethod
    def build_generic_response(ret: str, success: bool, reason: int = 1) -> dict:
        """Construit une réponse générique"""
        if success:
            return {"ret": ret, "result": True}
        return {"ret": ret, "result": False, "reason": reason}
    
    @staticmethod
    def build_sendqrcode_response(
        success: bool,
        access: int = 1,
        enrollid: int = 0,
        username: str = "",
        message: str = ""
    ) -> dict:
        """Construit la réponse à sendqrcode"""
        if success:
            return {
                "ret": "sendqrcode",
                "result": True,
                "access": access,
                "enrollid": enrollid,
                "username": username,
                "message": message,
            }
        return {
            "ret": "sendqrcode",
            "result": False,
            "reason": 1,
        }
    
    @staticmethod
    def parse_datetime(time_str: str) -> Optional[datetime]:
        """Parse une date/heure du protocole TM20"""
        if not time_str:
            return None
        try:
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.warning(f"Format date invalide: {time_str}")
            return None

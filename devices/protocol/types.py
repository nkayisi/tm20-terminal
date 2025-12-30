"""
Types de données du protocole TM20 v2.4
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional


class CommandType(str, Enum):
    """Commandes supportées par le protocole TM20"""
    
    # Terminal -> Serveur
    REG = "reg"
    SENDLOG = "sendlog"
    SENDUSER = "senduser"
    SENDQRCODE = "sendqrcode"
    
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
    GETQUESTIONNAIRE = "getquestionnaire"
    SETQUESTIONNAIRE = "setquestionnaire"
    GETHOLIDAY = "getholiday"
    SETHOLIDAY = "setholiday"


class BackupType(int, Enum):
    """Types de credentials biométriques"""
    FINGERPRINT_1 = 0
    FINGERPRINT_2 = 1
    FINGERPRINT_3 = 2
    FINGERPRINT_4 = 3
    FINGERPRINT_5 = 4
    FINGERPRINT_6 = 5
    FINGERPRINT_7 = 6
    FINGERPRINT_8 = 7
    FINGERPRINT_9 = 8
    FINGERPRINT_10 = 9
    PASSWORD = 10
    RFID_CARD = 11
    ALL_FINGERPRINTS = 12
    ALL_CREDENTIALS = 13
    FACE_1 = 20
    FACE_2 = 21
    FACE_3 = 22
    FACE_4 = 23
    FACE_5 = 24
    FACE_6 = 25
    FACE_7 = 26
    FACE_8 = 27
    PALM_1 = 30
    PALM_2 = 31
    PALM_3 = 32
    PALM_4 = 33
    PALM_5 = 34
    PALM_6 = 35
    PALM_7 = 36
    PALM_8 = 37
    PHOTO = 50


class VerifyMode(int, Enum):
    """Modes de vérification"""
    FINGERPRINT = 0
    CARD = 1
    PASSWORD = 2
    CARD_ALT = 3
    FACE = 8
    QRCODE = 13


class InOutType(int, Enum):
    """Type entrée/sortie"""
    IN = 0
    OUT = 1


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
    
    def to_dict(self) -> dict:
        return {
            'modelname': self.modelname,
            'usersize': self.usersize,
            'fpsize': self.fpsize,
            'firmware': self.firmware,
            'mac': self.mac,
        }


@dataclass
class RegisterMessage:
    """Message d'enregistrement du terminal"""
    sn: str
    cpusn: str = ""
    devinfo: Optional[DeviceInfo] = None
    
    @property
    def model(self) -> str:
        return self.devinfo.modelname if self.devinfo else ""
    
    @property
    def firmware(self) -> str:
        return self.devinfo.firmware if self.devinfo else ""


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
    
    def to_dict(self) -> dict:
        return {
            'enrollid': self.enrollid,
            'time': self.time,
            'mode': self.mode,
            'inout': self.inout,
            'event': self.event,
            'temp': self.temp,
            'verifymode': self.verifymode,
        }


@dataclass
class SendLogMessage:
    """Message d'envoi de logs"""
    sn: str
    count: int
    logindex: int = 0
    records: List[LogRecord] = field(default_factory=list)


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
    enrollid: int
    name: str = ""
    backupnum: int = 0
    admin: int = 0
    record: Any = None
    
    @property
    def is_fingerprint(self) -> bool:
        return 0 <= self.backupnum <= 9
    
    @property
    def is_face(self) -> bool:
        return 20 <= self.backupnum <= 27
    
    @property
    def is_card(self) -> bool:
        return self.backupnum == 11
    
    @property
    def is_password(self) -> bool:
        return self.backupnum == 10


@dataclass
class QRCodeMessage:
    """Message de vérification QR code"""
    sn: str
    record: str  # QR code content

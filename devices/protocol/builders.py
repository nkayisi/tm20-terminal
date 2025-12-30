"""
Builders pour construire les messages du protocole TM20
"""

from datetime import datetime
from typing import Any, Dict, List, Optional


class ResponseBuilder:
    """
    Constructeur de réponses serveur vers terminal
    """
    
    @staticmethod
    def _now() -> str:
        """Timestamp actuel formaté"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    @classmethod
    def reg(
        cls,
        success: bool,
        cloudtime: str = None,
        nosenduser: bool = True,
        reason: str = ""
    ) -> dict:
        """Réponse à reg"""
        if success:
            return {
                "ret": "reg",
                "result": True,
                "cloudtime": cloudtime or cls._now(),
                "nosenduser": nosenduser,
            }
        return {
            "ret": "reg",
            "result": False,
            "reason": reason,
        }
    
    @classmethod
    def sendlog(
        cls,
        success: bool,
        count: int = 0,
        logindex: int = 0,
        access: int = 1,
        message: str = ""
    ) -> dict:
        """Réponse à sendlog"""
        if success:
            resp = {
                "ret": "sendlog",
                "result": True,
                "count": count,
                "logindex": logindex,
                "cloudtime": cls._now(),
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
    
    @classmethod
    def senduser(cls, success: bool, reason: int = 1) -> dict:
        """Réponse à senduser"""
        if success:
            return {
                "ret": "senduser",
                "result": True,
                "cloudtime": cls._now(),
            }
        return {
            "ret": "senduser",
            "result": False,
            "reason": reason,
        }
    
    @classmethod
    def sendqrcode(
        cls,
        success: bool,
        access: int = 1,
        enrollid: int = 0,
        username: str = "",
        message: str = ""
    ) -> dict:
        """Réponse à sendqrcode"""
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
    
    @classmethod
    def generic(cls, ret: str, success: bool, reason: int = 1, **kwargs) -> dict:
        """Réponse générique"""
        if success:
            return {"ret": ret, "result": True, **kwargs}
        return {"ret": ret, "result": False, "reason": reason}


class CommandBuilder:
    """
    Constructeur de commandes serveur vers terminal
    """
    
    @staticmethod
    def _now() -> str:
        """Timestamp actuel formaté"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    @classmethod
    def getuserlist(cls, stn: bool = True) -> dict:
        """Récupérer la liste des utilisateurs"""
        return {
            "cmd": "getuserlist",
            "stn": stn,
        }
    
    @classmethod
    def getuserinfo(cls, enrollid: int, backupnum: int) -> dict:
        """Récupérer les infos d'un utilisateur"""
        return {
            "cmd": "getuserinfo",
            "enrollid": enrollid,
            "backupnum": backupnum,
        }
    
    @classmethod
    def setuserinfo(
        cls,
        enrollid: int,
        name: str,
        backupnum: int,
        admin: int = 0,
        record: Any = None
    ) -> dict:
        """Définir un utilisateur"""
        return {
            "cmd": "setuserinfo",
            "enrollid": enrollid,
            "name": name,
            "backupnum": backupnum,
            "admin": admin,
            "record": record,
        }
    
    @classmethod
    def deleteuser(cls, enrollid: int, backupnum: int = 13) -> dict:
        """
        Supprimer un utilisateur
        backupnum: 0-9=fp, 10=pwd, 11=card, 12=all fp, 13=all
        """
        return {
            "cmd": "deleteuser",
            "enrollid": enrollid,
            "backupnum": backupnum,
        }
    
    @classmethod
    def enableuser(cls, enrollid: int, enable: bool = True) -> dict:
        """Activer/désactiver un utilisateur"""
        return {
            "cmd": "enableuser",
            "enrollid": enrollid,
            "enflag": 1 if enable else 0,
        }
    
    @classmethod
    def setusername(cls, users: List[Dict[str, Any]]) -> dict:
        """
        Définir les noms d'utilisateurs (batch)
        users: [{"enrollid": 1, "name": "John"}, ...]
        """
        return {
            "cmd": "setusername",
            "count": len(users),
            "record": users,
        }
    
    @classmethod
    def opendoor(cls, door: int = 1, delay: int = 5) -> dict:
        """Ouvrir la porte"""
        return {
            "cmd": "opendoor",
            "door": door,
            "delay": delay,
        }
    
    @classmethod
    def settime(cls, cloudtime: str = None) -> dict:
        """Synchroniser l'heure"""
        return {
            "cmd": "settime",
            "cloudtime": cloudtime or cls._now(),
        }
    
    @classmethod
    def gettime(cls) -> dict:
        """Récupérer l'heure du terminal"""
        return {"cmd": "gettime"}
    
    @classmethod
    def getnewlog(cls, stn: bool = True) -> dict:
        """Récupérer les nouveaux logs"""
        return {
            "cmd": "getnewlog",
            "stn": stn,
        }
    
    @classmethod
    def getalllog(cls, stn: bool = True) -> dict:
        """Récupérer tous les logs"""
        return {
            "cmd": "getalllog",
            "stn": stn,
        }
    
    @classmethod
    def cleanlog(cls) -> dict:
        """Nettoyer les logs"""
        return {"cmd": "cleanlog"}
    
    @classmethod
    def cleanuser(cls) -> dict:
        """Supprimer tous les utilisateurs"""
        return {"cmd": "cleanuser"}
    
    @classmethod
    def reboot(cls) -> dict:
        """Redémarrer le terminal"""
        return {"cmd": "reboot"}
    
    @classmethod
    def getdevinfo(cls) -> dict:
        """Récupérer les infos du terminal"""
        return {"cmd": "getdevinfo"}
    
    @classmethod
    def getdevlock(cls) -> dict:
        """Récupérer les paramètres de contrôle d'accès"""
        return {"cmd": "getdevlock"}
    
    @classmethod
    def setuserlock(
        cls,
        users: List[Dict[str, Any]]
    ) -> dict:
        """
        Définir les paramètres d'accès utilisateurs (batch)
        users: [{
            "enrollid": 1,
            "weekzone": 1,
            "group": 1,
            "starttime": "2024-01-01 00:00:00",
            "endtime": "2099-12-31 23:59:00"
        }, ...]
        """
        return {
            "cmd": "setuserlock",
            "count": len(users),
            "record": users,
        }

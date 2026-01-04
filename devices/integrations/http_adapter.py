"""
HTTP Adapter - Adapter générique pour les APIs REST

Implémente l'interface ThirdPartyAdapter pour les services tiers
accessibles via HTTP/REST.
"""

import httpx
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from .base import (
    ThirdPartyAdapter,
    AdapterResponse,
    AdapterError,
    ConnectionError,
    AuthenticationError,
    RateLimitError,
    UserData,
    AttendanceData,
)

logger = logging.getLogger(__name__)


class HTTPAdapter(ThirdPartyAdapter):
    """
    Adapter HTTP générique pour les APIs REST.
    
    Supporte:
    - Authentification Bearer, API Key, Basic
    - Headers personnalisés
    - Timeout configurable
    - Retry automatique
    """
    
    def __init__(self, config: 'ThirdPartyConfig'):
        super().__init__(config)
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Retourne ou crée un client HTTP async"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout_seconds),
                headers=self.get_headers(),
            )
        return self._client
    
    async def close(self):
        """Ferme le client HTTP"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    async def _request(
        self,
        method: str,
        url: str,
        json: dict = None,
        params: dict = None,
    ) -> httpx.Response:
        """
        Effectue une requête HTTP avec gestion des erreurs.
        
        Raises:
            ConnectionError: Si la connexion échoue
            AuthenticationError: Si l'authentification échoue (401/403)
            RateLimitError: Si le rate limit est atteint (429)
            AdapterError: Pour les autres erreurs
        """
        client = await self._get_client()
        
        try:
            response = await client.request(
                method=method,
                url=url,
                json=json,
                params=params,
            )
            
            if response.status_code == 401:
                raise AuthenticationError(
                    "Authentification échouée - token invalide ou expiré",
                    {'status_code': 401}
                )
            
            if response.status_code == 403:
                raise AuthenticationError(
                    "Accès refusé - permissions insuffisantes",
                    {'status_code': 403}
                )
            
            if response.status_code == 429:
                retry_after = response.headers.get('Retry-After')
                raise RateLimitError(
                    "Rate limit atteint",
                    retry_after=int(retry_after) if retry_after else 60
                )
            
            if response.status_code >= 500:
                raise AdapterError(
                    f"Erreur serveur: {response.status_code}",
                    'SERVER_ERROR',
                    {'status_code': response.status_code, 'body': response.text[:500]}
                )
            
            return response
            
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"Impossible de se connecter à {url}",
                {'original_error': str(e)}
            )
        except httpx.TimeoutException as e:
            raise ConnectionError(
                f"Timeout lors de la connexion à {url}",
                {'original_error': str(e)}
            )
        except (AuthenticationError, RateLimitError, AdapterError):
            raise
        except Exception as e:
            raise AdapterError(
                f"Erreur inattendue: {str(e)}",
                'UNEXPECTED_ERROR',
                {'original_error': str(e)}
            )
    
    async def test_connection(self) -> AdapterResponse:
        """Teste la connexion au service tiers"""
        try:
            url = self.build_url(self.config.users_endpoint or '/')
            response = await self._request('HEAD', url)
            
            return AdapterResponse.ok(
                message="Connexion réussie",
                metadata={'status_code': response.status_code}
            )
        except AdapterError as e:
            return AdapterResponse.error(
                message=e.message,
                metadata=e.details
            )
    
    async def fetch_users(self, **kwargs) -> AdapterResponse:
        """
        Récupère les utilisateurs depuis le service tiers.
        
        Le format de réponse attendu est flexible:
        - {"users": [...]} ou {"data": [...]} ou [...]
        
        Chaque utilisateur doit avoir au minimum:
        - Un identifiant (id, external_id, user_id, employee_id)
        - Un nom (name, fullname, full_name, display_name)
        """
        if not self.config.users_endpoint:
            return AdapterResponse.error("Endpoint utilisateurs non configuré")
        
        try:
            url = self.build_url(self.config.users_endpoint)
            response = await self._request('GET', url, params=kwargs)
            
            if response.status_code != 200:
                return AdapterResponse.error(
                    f"Erreur HTTP {response.status_code}",
                    metadata={'status_code': response.status_code}
                )
            
            data = response.json()
            users = self._parse_users_response(data)
            
            self.logger.info(f"Récupéré {len(users)} utilisateurs depuis {self.config.name}")
            
            return AdapterResponse.ok(
                data=users,
                message=f"{len(users)} utilisateurs récupérés",
                metadata={
                    'count': len(users),
                    'source': self.config.name,
                    'timestamp': datetime.utcnow().isoformat(),
                }
            )
            
        except AdapterError as e:
            self.logger.error(f"Erreur fetch_users: {e.message}")
            return AdapterResponse.error(e.message, metadata=e.details)
    
    def _parse_users_response(self, data: Any) -> List[UserData]:
        """
        Parse la réponse du service tiers en liste de UserData.
        
        Gère différents formats de réponse courants.
        """
        users = []
        
        if isinstance(data, dict):
            raw_users = data.get('users') or data.get('data') or data.get('employees') or data.get('items') or []
        elif isinstance(data, list):
            raw_users = data
        else:
            self.logger.warning(f"Format de réponse inattendu: {type(data)}")
            return []
        
        for raw in raw_users:
            if not isinstance(raw, dict):
                continue
            
            external_id = str(
                raw.get('id') or 
                raw.get('external_id') or 
                raw.get('user_id') or 
                raw.get('employee_id') or
                raw.get('enrollid') or
                ''
            )
            
            if not external_id:
                self.logger.warning(f"Utilisateur sans ID ignoré: {raw}")
                continue
            
            fullname = (
                raw.get('fullname') or
                raw.get('full_name') or
                raw.get('name') or
                raw.get('display_name') or
                f"User {external_id}"
            )
            
            user = UserData(
                external_id=external_id,
                fullname=fullname,
                is_enabled=raw.get('is_enabled', raw.get('active', raw.get('enabled', True))),
                admin_level=raw.get('admin', raw.get('admin_level', 0)),
                group=raw.get('group', raw.get('department_id', 0)),
                weekzone=raw.get('weekzone', 1),
                start_date=raw.get('start_date', raw.get('starttime')),
                end_date=raw.get('end_date', raw.get('endtime')),
                metadata={k: v for k, v in raw.items() if k not in [
                    'id', 'external_id', 'user_id', 'employee_id', 'enrollid',
                    'fullname', 'full_name', 'name', 'display_name',
                    'is_enabled', 'active', 'enabled', 'admin', 'admin_level',
                    'group', 'department_id', 'weekzone', 'start_date', 'end_date',
                    'starttime', 'endtime'
                ]}
            )
            users.append(user)
        
        return users
    
    async def send_attendance(self, attendance_list: List[AttendanceData]) -> AdapterResponse:
        """
        Envoie les pointages vers le service tiers.
        
        Args:
            attendance_list: Liste de pointages à envoyer
            
        Returns:
            AdapterResponse avec les résultats de l'envoi
        """
        if not self.config.attendance_endpoint:
            return AdapterResponse.error("Endpoint pointages non configuré")
        
        if not attendance_list:
            return AdapterResponse.ok(
                data={'sent': 0, 'failed': 0},
                message="Aucun pointage à envoyer"
            )
        
        try:
            url = self.build_url(self.config.attendance_endpoint)
            
            payload = {
                'attendance': [att.to_dict() for att in attendance_list],
                'source': 'tm20_biometric',
                'timestamp': datetime.utcnow().isoformat(),
                'count': len(attendance_list),
            }
            
            response = await self._request('POST', url, json=payload)
            
            if response.status_code in (200, 201, 202):
                result = response.json() if response.text else {}
                
                return AdapterResponse.ok(
                    data={
                        'sent': len(attendance_list),
                        'failed': 0,
                        'response': result,
                    },
                    message=f"{len(attendance_list)} pointages envoyés avec succès",
                    metadata={
                        'status_code': response.status_code,
                        'log_ids': [att.log_id for att in attendance_list],
                    }
                )
            else:
                return AdapterResponse.error(
                    f"Erreur HTTP {response.status_code}",
                    metadata={
                        'status_code': response.status_code,
                        'body': response.text[:500],
                    }
                )
                
        except AdapterError as e:
            self.logger.error(f"Erreur send_attendance: {e.message}")
            return AdapterResponse.error(
                e.message,
                errors=[e.message],
                metadata=e.details
            )
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

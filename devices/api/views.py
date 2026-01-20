"""
API Views - Vues REST pour la gestion des terminaux et synchronisations

Architecture claire avec séparation:
- Controllers (ces vues)
- Services métier (services/)
- Adapters (integrations/)
"""

import json
import logging
from typing import Dict, Any

from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404
from asgiref.sync import async_to_sync

from ..models import (
    Terminal,
    BiometricUser,
    AttendanceLog,
    ThirdPartyConfig,
    TerminalThirdPartyMapping,
    TerminalSchedule,
)
from ..services.user_sync_service import UserSyncManager, UserSyncService
from ..services.attendance_sync_service import AttendanceSyncManager
from ..jobs import sync_users_from_third_party, sync_pending_attendance

logger = logging.getLogger(__name__)


class BaseAPIView(View):
    """Vue de base avec helpers communs"""
    
    def json_response(self, data: Dict[str, Any], status: int = 200) -> JsonResponse:
        return JsonResponse(data, status=status)
    
    def error_response(self, message: str, status: int = 400, details: dict = None) -> JsonResponse:
        return JsonResponse({
            'success': False,
            'error': message,
            'details': details or {}
        }, status=status)
    
    def success_response(self, data: Any = None, message: str = '') -> JsonResponse:
        return JsonResponse({
            'success': True,
            'message': message,
            'data': data
        })
    
    def parse_json_body(self, request) -> Dict[str, Any]:
        try:
            return json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return {}


@method_decorator(csrf_exempt, name='dispatch')
class ThirdPartyConfigListView(BaseAPIView):
    """Liste et création des configurations de services tiers"""
    
    def get(self, request):
        """Liste toutes les configurations"""
        configs = ThirdPartyConfig.objects.all().order_by('name')
        
        data = [
            {
                'id': c.id,
                'name': c.name,
                'description': c.description,
                'base_url': c.base_url,
                'users_endpoint': c.users_endpoint,
                'attendance_endpoint': c.attendance_endpoint,
                'auth_type': c.auth_type,
                'sync_interval_minutes': c.sync_interval_minutes,
                'is_active': c.is_active,
                'created_at': c.created_at.isoformat(),
            }
            for c in configs
        ]
        
        return self.json_response({'configs': data, 'count': len(data)})
    
    def post(self, request):
        """Crée une nouvelle configuration"""
        data = self.parse_json_body(request)
        
        required_fields = ['name', 'base_url']
        for field in required_fields:
            if not data.get(field):
                return self.error_response(f"Le champ '{field}' est requis")
        
        try:
            config = ThirdPartyConfig.objects.create(
                name=data['name'],
                description=data.get('description', ''),
                base_url=data['base_url'],
                users_endpoint=data.get('users_endpoint', ''),
                attendance_endpoint=data.get('attendance_endpoint', ''),
                auth_type=data.get('auth_type', 'bearer'),
                auth_token=data.get('auth_token', ''),
                auth_header_name=data.get('auth_header_name', 'Authorization'),
                extra_headers=data.get('extra_headers', {}),
                sync_interval_minutes=data.get('sync_interval_minutes', 15),
                timeout_seconds=data.get('timeout_seconds', 30),
                retry_attempts=data.get('retry_attempts', 3),
                is_active=data.get('is_active', True),
            )
            
            return self.success_response(
                {'id': config.id, 'name': config.name},
                message="Configuration créée avec succès"
            )
            
        except Exception as e:
            logger.exception(f"Erreur création config: {e}")
            return self.error_response(str(e), status=500)


@method_decorator(csrf_exempt, name='dispatch')
class ThirdPartyConfigDetailView(BaseAPIView):
    """Détail, modification et suppression d'une configuration"""
    
    def get(self, request, config_id):
        """Récupère les détails d'une configuration"""
        config = get_object_or_404(ThirdPartyConfig, id=config_id)
        
        mappings = TerminalThirdPartyMapping.objects.filter(
            config=config
        ).select_related('terminal')
        
        return self.json_response({
            'id': config.id,
            'name': config.name,
            'description': config.description,
            'base_url': config.base_url,
            'users_endpoint': config.users_endpoint,
            'attendance_endpoint': config.attendance_endpoint,
            'auth_type': config.auth_type,
            'auth_header_name': config.auth_header_name,
            'extra_headers': config.extra_headers,
            'sync_interval_minutes': config.sync_interval_minutes,
            'timeout_seconds': config.timeout_seconds,
            'retry_attempts': config.retry_attempts,
            'is_active': config.is_active,
            'created_at': config.created_at.isoformat(),
            'updated_at': config.updated_at.isoformat(),
            'terminals': [
                {
                    'id': m.terminal.id,
                    'sn': m.terminal.sn,
                    'sync_users': m.sync_users,
                    'sync_attendance': m.sync_attendance,
                    'last_user_sync': m.last_user_sync.isoformat() if m.last_user_sync else None,
                    'last_attendance_sync': m.last_attendance_sync.isoformat() if m.last_attendance_sync else None,
                }
                for m in mappings
            ]
        })
    
    def put(self, request, config_id):
        """Met à jour une configuration"""
        config = get_object_or_404(ThirdPartyConfig, id=config_id)
        data = self.parse_json_body(request)
        
        updatable_fields = [
            'name', 'description', 'base_url', 'users_endpoint', 
            'attendance_endpoint', 'auth_type', 'auth_token', 
            'auth_header_name', 'extra_headers', 'sync_interval_minutes',
            'timeout_seconds', 'retry_attempts', 'is_active'
        ]
        
        for field in updatable_fields:
            if field in data:
                setattr(config, field, data[field])
        
        config.save()
        
        return self.success_response(
            {'id': config.id},
            message="Configuration mise à jour"
        )
    
    def delete(self, request, config_id):
        """Supprime une configuration"""
        config = get_object_or_404(ThirdPartyConfig, id=config_id)
        config.delete()
        
        return self.success_response(message="Configuration supprimée")


@method_decorator(csrf_exempt, name='dispatch')
class TerminalMappingView(BaseAPIView):
    """Gestion des mappings terminal <-> configuration"""
    
    def get(self, request, terminal_id):
        """Liste les mappings d'un terminal"""
        terminal = get_object_or_404(Terminal, id=terminal_id)
        
        mappings = TerminalThirdPartyMapping.objects.filter(
            terminal=terminal
        ).select_related('config')
        
        return self.json_response({
            'terminal_sn': terminal.sn,
            'mappings': [
                {
                    'id': m.id,
                    'config_id': m.config.id,
                    'config_name': m.config.name,
                    'is_active': m.is_active,
                    'sync_users': m.sync_users,
                    'sync_attendance': m.sync_attendance,
                    'last_user_sync': m.last_user_sync.isoformat() if m.last_user_sync else None,
                    'last_attendance_sync': m.last_attendance_sync.isoformat() if m.last_attendance_sync else None,
                }
                for m in mappings
            ]
        })
    
    def post(self, request, terminal_id):
        """Crée un mapping terminal <-> configuration"""
        terminal = get_object_or_404(Terminal, id=terminal_id)
        data = self.parse_json_body(request)
        
        config_id = data.get('config_id')
        if not config_id:
            return self.error_response("config_id est requis")
        
        config = get_object_or_404(ThirdPartyConfig, id=config_id)
        
        mapping, created = TerminalThirdPartyMapping.objects.update_or_create(
            terminal=terminal,
            config=config,
            defaults={
                'is_active': data.get('is_active', True),
                'sync_users': data.get('sync_users', True),
                'sync_attendance': data.get('sync_attendance', True),
            }
        )
        
        return self.success_response(
            {'id': mapping.id, 'created': created},
            message="Mapping créé" if created else "Mapping mis à jour"
        )


@method_decorator(csrf_exempt, name='dispatch')
class UserSyncView(BaseAPIView):
    """Synchronisation des utilisateurs depuis un service tiers"""
    
    def post(self, request, terminal_id):
        """
        Déclenche la synchronisation des utilisateurs.
        
        Body:
            config_id: ID de la configuration du service tiers
            async: Si true, exécute en tâche de fond (défaut: false)
            ecole: (optionnel) code d'école à transmettre en paramètre GET au service tiers
        """
        terminal = get_object_or_404(Terminal, id=terminal_id)
        data = self.parse_json_body(request)
        
        config_id = data.get('config_id')
        if not config_id:
            mapping = TerminalThirdPartyMapping.objects.filter(
                terminal=terminal,
                is_active=True,
                sync_users=True
            ).first()
            
            if not mapping:
                return self.error_response(
                    "Aucune configuration trouvée pour ce terminal"
                )
            config_id = mapping.config.id
        
        config = get_object_or_404(ThirdPartyConfig, id=config_id)
        
        # Paramètres supplémentaires pour le service tiers (ex: ?ecole=XXXX)
        fetch_params = {}
        ecole = data.get('ecole')
        if ecole:
            fetch_params['ecole'] = ecole
        
        if data.get('async', False):
            task = sync_users_from_third_party.delay(
                terminal_id=terminal.id,
                config_id=config.id,
                **fetch_params,
            )
            return self.success_response(
                {'task_id': task.id},
                message="Synchronisation lancée en arrière-plan"
            )
        
        try:
            result = async_to_sync(UserSyncManager.sync_terminal_users)(
                terminal_id=terminal.id,
                config_id=config.id,
                **fetch_params,
            )
            
            return self.json_response({
                'success': result.success,
                'created': result.created,
                'updated': result.updated,
                'skipped': result.skipped,
                'errors': result.errors,
                'message': f"{result.created} utilisateurs créés, {result.updated} mis à jour"
            })
            
        except Exception as e:
            logger.exception(f"Erreur sync utilisateurs: {e}")
            return self.error_response(str(e), status=500)


@method_decorator(csrf_exempt, name='dispatch')
class UserSyncStatusView(BaseAPIView):
    """Statut de synchronisation des utilisateurs d'un terminal"""
    
    def get(self, request, terminal_id):
        """Récupère le statut de synchronisation des utilisateurs"""
        terminal = get_object_or_404(Terminal, id=terminal_id)
        
        try:
            status = async_to_sync(UserSyncManager.get_sync_status)(terminal.id)
            return self.json_response(status)
        except Exception as e:
            return self.error_response(str(e), status=500)


@method_decorator(csrf_exempt, name='dispatch')
class AttendanceSyncView(BaseAPIView):
    """Synchronisation des pointages vers un service tiers"""
    
    def post(self, request):
        """
        Déclenche la synchronisation des pointages.
        
        Body:
            config_id: ID de la configuration (optionnel, sinon toutes)
            terminal_id: ID du terminal (optionnel)
            async: Si true, exécute en tâche de fond (défaut: true)
        """
        data = self.parse_json_body(request)
        
        config_id = data.get('config_id')
        terminal_id = data.get('terminal_id')
        run_async = data.get('async', True)
        
        if run_async:
            if config_id:
                task = sync_pending_attendance.delay(
                    config_id=config_id,
                    terminal_id=terminal_id
                )
            else:
                from ..jobs import sync_all_configs_attendance
                task = sync_all_configs_attendance.delay()
            
            return self.success_response(
                {'task_id': task.id},
                message="Synchronisation lancée en arrière-plan"
            )
        
        try:
            if config_id:
                result = async_to_sync(AttendanceSyncManager.sync_config_attendance)(
                    config_id=config_id,
                    terminal_id=terminal_id
                )
                return self.json_response(result.to_dict())
            else:
                results = async_to_sync(AttendanceSyncManager.sync_all_pending)()
                return self.json_response({
                    name: r.to_dict() for name, r in results.items()
                })
                
        except Exception as e:
            logger.exception(f"Erreur sync pointages: {e}")
            return self.error_response(str(e), status=500)


class AttendanceSyncStatusView(BaseAPIView):
    """Statut de synchronisation des pointages"""
    
    def get(self, request):
        """Récupère les statistiques de synchronisation"""
        terminal_id = request.GET.get('terminal_id')
        config_id = request.GET.get('config_id')
        
        try:
            stats = async_to_sync(AttendanceSyncManager.get_sync_statistics)(
                terminal_id=int(terminal_id) if terminal_id else None,
                config_id=int(config_id) if config_id else None
            )
            return self.json_response(stats)
        except Exception as e:
            return self.error_response(str(e), status=500)


class DeadLetterView(BaseAPIView):
    """Gestion des pointages en échec permanent"""
    
    def get(self, request):
        """Liste les pointages en dead-letter"""
        limit = int(request.GET.get('limit', 100))
        
        try:
            logs = async_to_sync(AttendanceSyncManager.get_dead_letter_logs)(limit)
            return self.json_response({
                'logs': logs,
                'count': len(logs)
            })
        except Exception as e:
            return self.error_response(str(e), status=500)
    
    def post(self, request):
        """Réinitialise des pointages échoués pour retry"""
        data = self.parse_json_body(request)
        
        log_ids = data.get('log_ids')
        all_failed = data.get('all', False)
        
        try:
            count = async_to_sync(AttendanceSyncManager.reset_failed_logs)(
                log_ids=log_ids,
                all_failed=all_failed
            )
            return self.success_response(
                {'reset_count': count},
                message=f"{count} pointages réinitialisés"
            )
        except Exception as e:
            return self.error_response(str(e), status=500)


@method_decorator(csrf_exempt, name='dispatch')
class TerminalScheduleListView(BaseAPIView):
    """Liste et création des horaires d'un terminal"""
    
    def get(self, request, terminal_id):
        """Liste les horaires d'un terminal"""
        terminal = get_object_or_404(Terminal, id=terminal_id)
        
        schedules = TerminalSchedule.objects.filter(
            terminal=terminal
        ).order_by('weekday', 'check_in_time')
        
        weekday_names = dict(TerminalSchedule.WEEKDAY_CHOICES)
        
        return self.json_response({
            'terminal_sn': terminal.sn,
            'schedules': [
                {
                    'id': s.id,
                    'name': s.name,
                    'weekday': s.weekday,
                    'weekday_name': weekday_names.get(s.weekday),
                    'check_in_time': s.check_in_time.strftime('%H:%M'),
                    'break_start_time': s.break_start_time.strftime('%H:%M') if s.break_start_time else None,
                    'break_end_time': s.break_end_time.strftime('%H:%M') if s.break_end_time else None,
                    'check_out_time': s.check_out_time.strftime('%H:%M'),
                    'tolerance_minutes': s.tolerance_minutes,
                    'is_active': s.is_active,
                    'effective_from': s.effective_from.isoformat() if s.effective_from else None,
                    'effective_until': s.effective_until.isoformat() if s.effective_until else None,
                }
                for s in schedules
            ]
        })
    
    def post(self, request, terminal_id):
        """Crée un nouvel horaire"""
        from datetime import datetime
        
        terminal = get_object_or_404(Terminal, id=terminal_id)
        data = self.parse_json_body(request)
        
        required_fields = ['weekday', 'check_in_time', 'check_out_time']
        for field in required_fields:
            if field not in data:
                return self.error_response(f"Le champ '{field}' est requis")
        
        try:
            schedule = TerminalSchedule.objects.create(
                terminal=terminal,
                name=data.get('name', f"Horaire {terminal.sn}"),
                weekday=data['weekday'],
                check_in_time=datetime.strptime(data['check_in_time'], '%H:%M').time(),
                check_out_time=datetime.strptime(data['check_out_time'], '%H:%M').time(),
                break_start_time=datetime.strptime(data['break_start_time'], '%H:%M').time() if data.get('break_start_time') else None,
                break_end_time=datetime.strptime(data['break_end_time'], '%H:%M').time() if data.get('break_end_time') else None,
                tolerance_minutes=data.get('tolerance_minutes', 15),
                is_active=data.get('is_active', True),
            )
            
            return self.success_response(
                {'id': schedule.id},
                message="Horaire créé avec succès"
            )
            
        except Exception as e:
            logger.exception(f"Erreur création horaire: {e}")
            return self.error_response(str(e), status=500)


@method_decorator(csrf_exempt, name='dispatch')
class TerminalScheduleDetailView(BaseAPIView):
    """Détail, modification et suppression d'un horaire"""
    
    def put(self, request, terminal_id, schedule_id):
        """Met à jour un horaire"""
        from datetime import datetime
        
        schedule = get_object_or_404(
            TerminalSchedule, 
            id=schedule_id, 
            terminal_id=terminal_id
        )
        data = self.parse_json_body(request)
        
        if 'name' in data:
            schedule.name = data['name']
        if 'weekday' in data:
            schedule.weekday = data['weekday']
        if 'check_in_time' in data:
            schedule.check_in_time = datetime.strptime(data['check_in_time'], '%H:%M').time()
        if 'check_out_time' in data:
            schedule.check_out_time = datetime.strptime(data['check_out_time'], '%H:%M').time()
        if 'break_start_time' in data:
            schedule.break_start_time = datetime.strptime(data['break_start_time'], '%H:%M').time() if data['break_start_time'] else None
        if 'break_end_time' in data:
            schedule.break_end_time = datetime.strptime(data['break_end_time'], '%H:%M').time() if data['break_end_time'] else None
        if 'tolerance_minutes' in data:
            schedule.tolerance_minutes = data['tolerance_minutes']
        if 'is_active' in data:
            schedule.is_active = data['is_active']
        
        schedule.save()
        
        return self.success_response(message="Horaire mis à jour")
    
    def delete(self, request, terminal_id, schedule_id):
        """Supprime un horaire"""
        schedule = get_object_or_404(
            TerminalSchedule,
            id=schedule_id,
            terminal_id=terminal_id
        )
        schedule.delete()
        
        return self.success_response(message="Horaire supprimé")


class TerminalUsersView(BaseAPIView):
    """Liste des utilisateurs d'un terminal"""
    
    def get(self, request, terminal_id):
        """Liste les utilisateurs biométriques d'un terminal"""
        terminal = get_object_or_404(Terminal, id=terminal_id)
        
        sync_status = request.GET.get('sync_status')
        
        users = BiometricUser.objects.filter(terminal=terminal)
        
        if sync_status:
            users = users.filter(sync_status=sync_status)
        
        users = users.order_by('enrollid')[:500]
        
        return self.json_response({
            'terminal_sn': terminal.sn,
            'users': [
                {
                    'id': u.id,
                    'enrollid': u.enrollid,
                    'external_id': u.external_id,
                    'name': u.name,
                    'is_enabled': u.is_enabled,
                    'admin': u.admin,
                    'sync_status': u.sync_status,
                    'last_synced_at': u.last_synced_at.isoformat() if u.last_synced_at else None,
                    'source_config': u.source_config.name if u.source_config else None,
                }
                for u in users
            ],
            'count': users.count()
        })

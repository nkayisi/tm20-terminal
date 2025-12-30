"""
API REST pour gestion des configurations tiers, horaires et synchronisation
"""

import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from asgiref.sync import async_to_sync
import json

from .models import (
    Terminal,
    ThirdPartyConfig,
    TerminalThirdPartyMapping,
    TerminalSchedule,
    AttendanceLog,
)
from .tasks import (
    sync_users_from_third_party_task,
    sync_users_to_terminal_device_task,
    sync_schedule_to_terminal_task,
)
from .services.schedule_manager import ScheduleManager
from .services.third_party_sync import AttendanceSyncService

logger = logging.getLogger('devices.api')


@csrf_exempt
@require_http_methods(["GET", "POST"])
def third_party_configs_api(request):
    """API pour gérer les configurations de services tiers"""
    
    if request.method == "GET":
        configs = ThirdPartyConfig.objects.all().order_by('-created_at')
        
        data = [{
            'id': config.id,
            'name': config.name,
            'description': config.description,
            'base_url': config.base_url,
            'users_endpoint': config.users_endpoint,
            'attendance_endpoint': config.attendance_endpoint,
            'auth_type': config.auth_type,
            'sync_interval_minutes': config.sync_interval_minutes,
            'is_active': config.is_active,
            'created_at': config.created_at.isoformat(),
        } for config in configs]
        
        return JsonResponse({'success': True, 'configs': data})
    
    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            
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
            
            return JsonResponse({
                'success': True,
                'message': 'Configuration créée avec succès',
                'config_id': config.id
            })
            
        except Exception as e:
            logger.exception(f"Erreur création config: {e}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def third_party_config_detail_api(request, config_id):
    """API pour gérer une configuration spécifique"""
    
    try:
        config = ThirdPartyConfig.objects.get(id=config_id)
    except ThirdPartyConfig.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Configuration introuvable'
        }, status=404)
    
    if request.method == "GET":
        return JsonResponse({
            'success': True,
            'config': {
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
            }
        })
    
    elif request.method == "PUT":
        try:
            data = json.loads(request.body)
            
            for key, value in data.items():
                if hasattr(config, key) and key not in ['id', 'created_at', 'updated_at']:
                    setattr(config, key, value)
            
            config.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Configuration mise à jour'
            })
            
        except Exception as e:
            logger.exception(f"Erreur mise à jour config: {e}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
    elif request.method == "DELETE":
        config.delete()
        return JsonResponse({
            'success': True,
            'message': 'Configuration supprimée'
        })


@csrf_exempt
@require_http_methods(["POST"])
def sync_users_from_third_party_api(request):
    """API pour déclencher la synchronisation des utilisateurs depuis service tiers"""
    
    try:
        data = json.loads(request.body)
        terminal_id = data.get('terminal_id')
        config_id = data.get('config_id')
        
        if not terminal_id or not config_id:
            return JsonResponse({
                'success': False,
                'error': 'terminal_id et config_id requis'
            }, status=400)
        
        terminal = Terminal.objects.get(id=terminal_id)
        config = ThirdPartyConfig.objects.get(id=config_id)
        
        mapping, created = TerminalThirdPartyMapping.objects.get_or_create(
            terminal=terminal,
            config=config,
            defaults={'is_active': True, 'sync_users': True}
        )
        
        task = sync_users_from_third_party_task.delay(terminal_id, config_id)
        
        return JsonResponse({
            'success': True,
            'message': 'Synchronisation lancée',
            'task_id': task.id,
            'terminal_sn': terminal.sn,
            'config_name': config.name
        })
        
    except Terminal.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Terminal introuvable'
        }, status=404)
    except ThirdPartyConfig.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Configuration introuvable'
        }, status=404)
    except Exception as e:
        logger.exception(f"Erreur sync users: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def load_users_to_terminal_api(request):
    """API pour charger les utilisateurs sur un terminal physique"""
    
    try:
        data = json.loads(request.body)
        terminal_id = data.get('terminal_id')
        user_ids = data.get('user_ids')
        
        if not terminal_id:
            return JsonResponse({
                'success': False,
                'error': 'terminal_id requis'
            }, status=400)
        
        terminal = Terminal.objects.get(id=terminal_id)
        
        task = sync_users_to_terminal_device_task.delay(terminal_id, user_ids)
        
        return JsonResponse({
            'success': True,
            'message': 'Chargement des utilisateurs lancé',
            'task_id': task.id,
            'terminal_sn': terminal.sn
        })
        
    except Terminal.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Terminal introuvable'
        }, status=404)
    except Exception as e:
        logger.exception(f"Erreur load users: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def terminal_schedules_api(request, terminal_id):
    """API pour gérer les horaires d'un terminal"""
    
    try:
        terminal = Terminal.objects.get(id=terminal_id)
    except Terminal.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Terminal introuvable'
        }, status=404)
    
    if request.method == "GET":
        schedules = TerminalSchedule.objects.filter(
            terminal=terminal
        ).order_by('weekday', 'check_in_time')
        
        data = [{
            'id': schedule.id,
            'name': schedule.name,
            'weekday': schedule.weekday,
            'weekday_display': schedule.get_weekday_display(),
            'check_in_time': schedule.check_in_time.strftime('%H:%M'),
            'check_out_time': schedule.check_out_time.strftime('%H:%M'),
            'break_start_time': schedule.break_start_time.strftime('%H:%M') if schedule.break_start_time else None,
            'break_end_time': schedule.break_end_time.strftime('%H:%M') if schedule.break_end_time else None,
            'tolerance_minutes': schedule.tolerance_minutes,
            'is_active': schedule.is_active,
            'effective_from': schedule.effective_from.isoformat() if schedule.effective_from else None,
            'effective_until': schedule.effective_until.isoformat() if schedule.effective_until else None,
        } for schedule in schedules]
        
        summary = async_to_sync(ScheduleManager.get_schedule_summary)(terminal)
        
        return JsonResponse({
            'success': True,
            'schedules': data,
            'summary': summary
        })
    
    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            
            from datetime import time as dt_time
            
            check_in_time = dt_time.fromisoformat(data['check_in_time'])
            check_out_time = dt_time.fromisoformat(data['check_out_time'])
            
            break_start_time = None
            break_end_time = None
            if data.get('break_start_time'):
                break_start_time = dt_time.fromisoformat(data['break_start_time'])
            if data.get('break_end_time'):
                break_end_time = dt_time.fromisoformat(data['break_end_time'])
            
            schedule = async_to_sync(ScheduleManager.create_schedule)(
                terminal=terminal,
                weekday=data['weekday'],
                check_in_time=check_in_time,
                check_out_time=check_out_time,
                break_start_time=break_start_time,
                break_end_time=break_end_time,
                tolerance_minutes=data.get('tolerance_minutes', 15),
                name=data.get('name', ''),
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Horaire créé avec succès',
                'schedule_id': schedule.id
            })
            
        except Exception as e:
            logger.exception(f"Erreur création horaire: {e}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)


@csrf_exempt
@require_http_methods(["PUT", "DELETE"])
def terminal_schedule_detail_api(request, terminal_id, schedule_id):
    """API pour gérer un horaire spécifique"""
    
    try:
        schedule = TerminalSchedule.objects.get(id=schedule_id, terminal_id=terminal_id)
    except TerminalSchedule.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Horaire introuvable'
        }, status=404)
    
    if request.method == "PUT":
        try:
            data = json.loads(request.body)
            
            from datetime import time as dt_time
            
            update_data = {}
            
            if 'check_in_time' in data:
                update_data['check_in_time'] = dt_time.fromisoformat(data['check_in_time'])
            if 'check_out_time' in data:
                update_data['check_out_time'] = dt_time.fromisoformat(data['check_out_time'])
            if 'break_start_time' in data:
                update_data['break_start_time'] = dt_time.fromisoformat(data['break_start_time']) if data['break_start_time'] else None
            if 'break_end_time' in data:
                update_data['break_end_time'] = dt_time.fromisoformat(data['break_end_time']) if data['break_end_time'] else None
            
            for key in ['name', 'weekday', 'tolerance_minutes', 'is_active']:
                if key in data:
                    update_data[key] = data[key]
            
            updated_schedule = async_to_sync(ScheduleManager.update_schedule)(
                schedule.id,
                **update_data
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Horaire mis à jour'
            })
            
        except Exception as e:
            logger.exception(f"Erreur mise à jour horaire: {e}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
    elif request.method == "DELETE":
        success = async_to_sync(ScheduleManager.delete_schedule)(schedule.id)
        
        if success:
            return JsonResponse({
                'success': True,
                'message': 'Horaire supprimé'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Erreur lors de la suppression'
            }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def sync_schedule_to_terminal_api(request, terminal_id):
    """API pour synchroniser les horaires vers le terminal physique"""
    
    try:
        data = json.loads(request.body)
        schedule_id = data.get('schedule_id')
        
        terminal = Terminal.objects.get(id=terminal_id)
        
        task = sync_schedule_to_terminal_task.delay(terminal_id, schedule_id)
        
        return JsonResponse({
            'success': True,
            'message': 'Synchronisation des horaires lancée',
            'task_id': task.id,
            'terminal_sn': terminal.sn
        })
        
    except Terminal.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Terminal introuvable'
        }, status=404)
    except Exception as e:
        logger.exception(f"Erreur sync schedule: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def attendance_sync_status_api(request):
    """API pour obtenir le statut de synchronisation des pointages"""
    
    terminal_id = request.GET.get('terminal_id')
    status = request.GET.get('status', 'pending')
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 50))
    
    query = AttendanceLog.objects.filter(sync_status=status)
    
    if terminal_id:
        query = query.filter(terminal_id=terminal_id)
    
    query = query.select_related('terminal', 'user').order_by('-time')
    
    paginator = Paginator(query, per_page)
    page_obj = paginator.get_page(page)
    
    data = [{
        'id': log.id,
        'terminal_sn': log.terminal.sn,
        'enrollid': log.enrollid,
        'user_name': log.user.name if log.user else '',
        'time': log.time.isoformat(),
        'mode': log.get_mode_display(),
        'inout': log.get_inout_display(),
        'sync_status': log.sync_status,
        'sync_attempts': log.sync_attempts,
        'synced_at': log.synced_at.isoformat() if log.synced_at else None,
        'sync_error': log.sync_error,
    } for log in page_obj]
    
    stats = {
        'pending': AttendanceLog.objects.filter(sync_status='pending').count(),
        'sent': AttendanceLog.objects.filter(sync_status='sent').count(),
        'failed': AttendanceLog.objects.filter(sync_status='failed').count(),
    }
    
    return JsonResponse({
        'success': True,
        'logs': data,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': paginator.count,
            'pages': paginator.num_pages,
        },
        'stats': stats
    })


@csrf_exempt
@require_http_methods(["POST"])
def manual_sync_attendance_api(request):
    """API pour déclencher manuellement la synchronisation des pointages"""
    
    try:
        data = json.loads(request.body)
        config_id = data.get('config_id')
        terminal_id = data.get('terminal_id')
        
        if not config_id:
            return JsonResponse({
                'success': False,
                'error': 'config_id requis'
            }, status=400)
        
        config = ThirdPartyConfig.objects.get(id=config_id)
        terminal = None
        
        if terminal_id:
            terminal = Terminal.objects.get(id=terminal_id)
        
        sent, failed, error = async_to_sync(
            AttendanceSyncService.sync_pending_attendance
        )(config, terminal, batch_size=100)
        
        if error and sent == 0:
            return JsonResponse({
                'success': False,
                'error': error,
                'sent': sent,
                'failed': failed
            }, status=500)
        
        return JsonResponse({
            'success': True,
            'message': 'Synchronisation terminée',
            'sent': sent,
            'failed': failed,
            'error': error
        })
        
    except ThirdPartyConfig.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Configuration introuvable'
        }, status=404)
    except Terminal.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Terminal introuvable'
        }, status=404)
    except Exception as e:
        logger.exception(f"Erreur sync attendance: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def terminal_mappings_api(request, terminal_id):
    """API pour obtenir les mappings d'un terminal avec les services tiers"""
    
    try:
        terminal = Terminal.objects.get(id=terminal_id)
    except Terminal.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Terminal introuvable'
        }, status=404)
    
    mappings = TerminalThirdPartyMapping.objects.filter(
        terminal=terminal
    ).select_related('config')
    
    data = [{
        'id': mapping.id,
        'config_id': mapping.config.id,
        'config_name': mapping.config.name,
        'is_active': mapping.is_active,
        'sync_users': mapping.sync_users,
        'sync_attendance': mapping.sync_attendance,
        'last_user_sync': mapping.last_user_sync.isoformat() if mapping.last_user_sync else None,
        'last_attendance_sync': mapping.last_attendance_sync.isoformat() if mapping.last_attendance_sync else None,
    } for mapping in mappings]
    
    return JsonResponse({
        'success': True,
        'terminal_sn': terminal.sn,
        'mappings': data
    })

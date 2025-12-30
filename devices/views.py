"""
Vues API REST pour la gestion des terminaux TM20
"""

import asyncio
import json
from datetime import datetime, timedelta

from django.http import JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .core.device_manager import DeviceManager
from .models import AttendanceLog, BiometricUser, CommandQueue, Terminal
from .protocol import CommandBuilder


@method_decorator(csrf_exempt, name='dispatch')
class TerminalListView(View):
    """Liste des terminaux"""
    
    def get(self, request):
        terminals = Terminal.objects.all()
        data = [
            {
                'sn': t.sn,
                'model': t.model,
                'firmware': t.firmware,
                'last_seen': t.last_seen.isoformat() if t.last_seen else None,
                'is_active': t.is_active,
                'is_whitelisted': t.is_whitelisted,
                'used_users': t.used_users,
                'user_capacity': t.user_capacity,
            }
            for t in terminals
        ]
        return JsonResponse({'terminals': data})


@method_decorator(csrf_exempt, name='dispatch')
class TerminalDetailView(View):
    """Détail d'un terminal"""
    
    def get(self, request, sn):
        try:
            t = Terminal.objects.get(sn=sn)
            data = {
                'sn': t.sn,
                'cpusn': t.cpusn,
                'model': t.model,
                'firmware': t.firmware,
                'mac_address': t.mac_address,
                'fp_algo': t.fp_algo,
                'user_capacity': t.user_capacity,
                'fp_capacity': t.fp_capacity,
                'card_capacity': t.card_capacity,
                'log_capacity': t.log_capacity,
                'used_users': t.used_users,
                'used_fp': t.used_fp,
                'used_cards': t.used_cards,
                'used_logs': t.used_logs,
                'last_seen': t.last_seen.isoformat() if t.last_seen else None,
                'is_active': t.is_active,
                'is_whitelisted': t.is_whitelisted,
                'created_at': t.created_at.isoformat(),
            }
            return JsonResponse(data)
        except Terminal.DoesNotExist:
            return JsonResponse({'error': 'Terminal non trouvé'}, status=404)
    
    def patch(self, request, sn):
        try:
            terminal = Terminal.objects.get(sn=sn)
            data = json.loads(request.body)
            
            if 'is_whitelisted' in data:
                terminal.is_whitelisted = data['is_whitelisted']
            if 'is_active' in data:
                terminal.is_active = data['is_active']
            
            terminal.save()
            return JsonResponse({'success': True})
        except Terminal.DoesNotExist:
            return JsonResponse({'error': 'Terminal non trouvé'}, status=404)


@method_decorator(csrf_exempt, name='dispatch')
class SendCommandView(View):
    """Envoie une commande à un terminal"""
    
    def post(self, request, sn):
        try:
            terminal = Terminal.objects.get(sn=sn)
            data = json.loads(request.body)
            
            command = data.get('command', '')
            params = data.get('params', {})
            
            # Construire le payload selon la commande
            payload = self._build_command_payload(command, params)
            if not payload:
                return JsonResponse({'error': 'Commande invalide'}, status=400)
            
            # Ajouter à la file d'attente
            cmd = CommandQueue.objects.create(
                terminal=terminal,
                command=command,
                payload=payload,
                status='pending'
            )
            
            # Essayer d'envoyer immédiatement si le terminal est connecté
            sent = asyncio.run(self._try_send_now(sn, payload))
            
            if sent:
                cmd.status = 'sent'
                cmd.sent_at = timezone.now()
                cmd.save()
            
            return JsonResponse({
                'success': True,
                'command_id': cmd.id,
                'sent_immediately': sent
            })
            
        except Terminal.DoesNotExist:
            return JsonResponse({'error': 'Terminal non trouvé'}, status=404)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON invalide'}, status=400)
    
    def _build_command_payload(self, command: str, params: dict) -> dict:
        """Construit le payload de la commande"""
        builders = {
            'opendoor': lambda p: CommandBuilder.opendoor(
                p.get('door', 1), p.get('delay', 5)
            ),
            'settime': lambda p: CommandBuilder.settime(
                p.get('time')
            ),
            'gettime': lambda p: CommandBuilder.gettime(),
            'getuserlist': lambda p: CommandBuilder.getuserlist(
                p.get('stn', True)
            ),
            'getnewlog': lambda p: CommandBuilder.getnewlog(
                p.get('stn', True)
            ),
            'deleteuser': lambda p: CommandBuilder.deleteuser(
                p.get('enrollid'), p.get('backupnum', 13)
            ),
            'enableuser': lambda p: CommandBuilder.enableuser(
                p.get('enrollid'), p.get('enable', True)
            ),
            'reboot': lambda p: CommandBuilder.reboot(),
            'cleanlog': lambda p: CommandBuilder.cleanlog(),
            'cleanuser': lambda p: CommandBuilder.cleanuser(),
            'getdevinfo': lambda p: CommandBuilder.getdevinfo(),
        }
        
        if command in builders:
            return builders[command](params)
        return None
    
    async def _try_send_now(self, sn: str, payload: dict) -> bool:
        """Tente d'envoyer immédiatement au terminal"""
        device_manager = DeviceManager.get_instance()
        return await device_manager.send_to_device(sn, payload)


@method_decorator(csrf_exempt, name='dispatch')
class TerminalUsersView(View):
    """Utilisateurs d'un terminal"""
    
    def get(self, request, sn):
        try:
            terminal = Terminal.objects.get(sn=sn)
            users = BiometricUser.objects.filter(terminal=terminal)
            
            data = [
                {
                    'enrollid': u.enrollid,
                    'name': u.name,
                    'admin': u.admin,
                    'is_enabled': u.is_enabled,
                    'credentials_count': u.credentials.count(),
                    'created_at': u.created_at.isoformat(),
                }
                for u in users
            ]
            return JsonResponse({'users': data, 'count': len(data)})
        except Terminal.DoesNotExist:
            return JsonResponse({'error': 'Terminal non trouvé'}, status=404)


@method_decorator(csrf_exempt, name='dispatch')
class TerminalLogsView(View):
    """Logs de pointage d'un terminal"""
    
    def get(self, request, sn):
        try:
            terminal = Terminal.objects.get(sn=sn)
            
            # Filtres optionnels
            limit = int(request.GET.get('limit', 100))
            offset = int(request.GET.get('offset', 0))
            date_from = request.GET.get('from')
            date_to = request.GET.get('to')
            
            logs = AttendanceLog.objects.filter(terminal=terminal)
            
            if date_from:
                logs = logs.filter(time__gte=date_from)
            if date_to:
                logs = logs.filter(time__lte=date_to)
            
            total = logs.count()
            logs = logs.order_by('-time')[offset:offset + limit]
            
            data = [
                {
                    'id': log.id,
                    'enrollid': log.enrollid,
                    'user_name': log.user.name if log.user else None,
                    'time': log.time.isoformat(),
                    'mode': log.get_mode_display(),
                    'inout': log.get_inout_display(),
                    'event': log.event,
                    'temperature': float(log.temperature) if log.temperature else None,
                    'access_granted': log.access_granted,
                }
                for log in logs
            ]
            
            return JsonResponse({
                'logs': data,
                'count': len(data),
                'total': total,
                'offset': offset,
                'limit': limit,
            })
        except Terminal.DoesNotExist:
            return JsonResponse({'error': 'Terminal non trouvé'}, status=404)


@method_decorator(csrf_exempt, name='dispatch')
class ConnectedTerminalsView(View):
    """Liste des terminaux actuellement connectés"""
    
    def get(self, request):
        device_manager = DeviceManager.get_instance()
        connected = asyncio.run(device_manager.get_connected_sns())
        return JsonResponse({
            'connected': connected,
            'count': len(connected)
        })

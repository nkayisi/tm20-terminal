"""
Vues du dashboard temps réel
"""

import asyncio
import json
from datetime import datetime, timedelta

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from ..models import Terminal, AttendanceLog, CommandQueue
from ..core.device_manager import DeviceManager
from ..core.metrics import MetricsCollector
from ..core.events import EventBus


class DashboardView(View):
    """Vue principale du dashboard"""
    
    def get(self, request):
        return render(request, 'devices/dashboard/index.html')


class DashboardAPIView(View):
    """API pour le dashboard temps réel"""
    
    def get(self, request):
        """Récupère l'état global du système"""
        device_manager = DeviceManager.get_instance()
        metrics = MetricsCollector.get_instance()
        
        # Stats des terminaux
        terminals = Terminal.objects.all()
        total_terminals = terminals.count()
        active_terminals = terminals.filter(is_active=True).count()
        
        # Nombre de terminaux connectés (depuis Redis - partage inter-processus)
        connected_count = DeviceManager.get_connected_count_from_redis()
        
        # Stats des logs (aujourd'hui)
        today = timezone.now().date()
        logs_today = AttendanceLog.objects.filter(
            time__date=today
        ).count()
        
        # Commandes en attente
        pending_commands = CommandQueue.objects.filter(
            status='pending'
        ).count()
        
        # Métriques temps réel (depuis Redis pour partage inter-processus)
        realtime_metrics = MetricsCollector.get_stats_from_redis()
        
        # Mettre à jour le nombre de connexions actives dans les métriques
        realtime_metrics['connections']['active'] = connected_count
        
        return JsonResponse({
            'timestamp': datetime.now().isoformat(),
            'terminals': {
                'total': total_terminals,
                'active': active_terminals,
                'connected': connected_count,
            },
            'logs': {
                'today': logs_today,
                'rate_per_second': realtime_metrics['logs']['rate_per_second'],
            },
            'commands': {
                'pending': pending_commands,
            },
            'metrics': realtime_metrics,
        })


class TerminalsAPIView(View):
    """API pour la liste des terminaux"""
    
    def get(self, request):
        """Liste des terminaux avec statut temps réel"""
        device_manager = DeviceManager.get_instance()
        
        # Récupérer les terminaux connectés (depuis Redis)
        connected_sns = DeviceManager.get_connected_sns_from_redis()
        
        terminals = Terminal.objects.all().order_by('-last_seen')
        
        data = []
        for t in terminals:
            is_connected = t.sn in connected_sns
            
            # Calculer le statut
            if is_connected:
                status = 'online'
                status_class = 'success'
            elif t.is_active and t.last_seen:
                age = (timezone.now() - t.last_seen).total_seconds()
                if age < 300:  # 5 minutes
                    status = 'idle'
                    status_class = 'warning'
                else:
                    status = 'offline'
                    status_class = 'danger'
            else:
                status = 'offline'
                status_class = 'secondary'
            
            data.append({
                'sn': t.sn,
                'model': t.model or 'TM20',
                'firmware': t.firmware,
                'status': status,
                'status_class': status_class,
                'is_connected': is_connected,
                'last_seen': t.last_seen.isoformat() if t.last_seen else None,
                'last_seen_human': self._humanize_time(t.last_seen) if t.last_seen else 'Never',
                'used_users': t.used_users,
                'user_capacity': t.user_capacity,
            })
        
        return JsonResponse({'terminals': data})
    
    def _humanize_time(self, dt):
        """Convertit un datetime en temps relatif"""
        if not dt:
            return 'Never'
        
        now = timezone.now()
        diff = now - dt
        
        if diff.total_seconds() < 60:
            return 'Just now'
        elif diff.total_seconds() < 3600:
            mins = int(diff.total_seconds() / 60)
            return f'{mins}m ago'
        elif diff.total_seconds() < 86400:
            hours = int(diff.total_seconds() / 3600)
            return f'{hours}h ago'
        else:
            days = int(diff.total_seconds() / 86400)
            return f'{days}d ago'


class LogsAPIView(View):
    """API pour les logs récents"""
    
    def get(self, request):
        """Récupère les logs récents"""
        limit = int(request.GET.get('limit', 50))
        sn = request.GET.get('sn')
        
        queryset = AttendanceLog.objects.select_related(
            'terminal', 'user'
        ).order_by('-time')
        
        if sn:
            queryset = queryset.filter(terminal__sn=sn)
        
        logs = queryset[:limit]
        
        data = [
            {
                'id': log.id,
                'sn': log.terminal.sn,
                'enrollid': log.enrollid,
                'user_name': log.user.name if log.user else f'User #{log.enrollid}',
                'time': log.time.isoformat(),
                'time_human': log.time.strftime('%H:%M:%S'),
                'mode': log.get_mode_display(),
                'inout': log.get_inout_display(),
                'inout_class': 'success' if log.inout == 0 else 'info',
            }
            for log in logs
        ]
        
        return JsonResponse({'logs': data})


class EventsAPIView(View):
    """API pour les événements récents"""
    
    def get(self, request):
        """Récupère les événements récents"""
        event_bus = EventBus.get_instance()
        
        limit = int(request.GET.get('limit', 50))
        events = event_bus.get_recent_events(limit=limit)
        
        data = [event.to_dict() for event in events]
        
        return JsonResponse({'events': data})


@method_decorator(csrf_exempt, name='dispatch')
class CommandAPIView(View):
    """API pour envoyer des commandes"""
    
    def post(self, request, sn):
        """Envoie une commande à un terminal"""
        try:
            data = json.loads(request.body)
            command = data.get('command')
            params = data.get('params', {})
            
            if not command:
                return JsonResponse(
                    {'error': 'Command required'},
                    status=400
                )
            
            # Vérifier que le terminal existe
            try:
                terminal = Terminal.objects.get(sn=sn)
            except Terminal.DoesNotExist:
                return JsonResponse(
                    {'error': 'Terminal not found'},
                    status=404
                )
            
            # Construire le payload
            from ..protocol import CommandBuilder
            
            builder_methods = {
                'opendoor': lambda p: CommandBuilder.opendoor(
                    p.get('door', 1), p.get('delay', 5)
                ),
                'settime': lambda p: CommandBuilder.settime(p.get('time')),
                'gettime': lambda p: CommandBuilder.gettime(),
                'reboot': lambda p: CommandBuilder.reboot(),
                'getuserlist': lambda p: CommandBuilder.getuserlist(),
                'getnewlog': lambda p: CommandBuilder.getnewlog(),
                'getdevinfo': lambda p: CommandBuilder.getdevinfo(),
            }
            
            if command not in builder_methods:
                return JsonResponse(
                    {'error': f'Unknown command: {command}'},
                    status=400
                )
            
            payload = builder_methods[command](params)
            
            # Essayer d'envoyer directement si connecté
            device_manager = DeviceManager.get_instance()
            sent = asyncio.run(device_manager.send_to_device(sn, payload))
            
            if not sent:
                # Ajouter à la file d'attente
                CommandQueue.objects.create(
                    terminal=terminal,
                    command=command,
                    payload=payload,
                    status='pending'
                )
            
            return JsonResponse({
                'success': True,
                'sent_immediately': sent,
                'command': command,
            })
            
        except json.JSONDecodeError:
            return JsonResponse(
                {'error': 'Invalid JSON'},
                status=400
            )
        except Exception as e:
            return JsonResponse(
                {'error': str(e)},
                status=500
            )

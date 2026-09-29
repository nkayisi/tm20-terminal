"""
Vues API REST pour la gestion des terminaux TM20
"""

import json
from datetime import datetime, timedelta

from django.http import JsonResponse
from django.utils import timezone
from django.views import View

from .core.device_manager import DeviceManager
from .models import AttendanceLog, BiometricUser, CommandQueue, Terminal
from .protocol import CommandBuilder
from .services.commands import CommandService


class AuthenticatedView(View):
    """Vue de base exigeant une session authentifiée.

    Ces endpoints exposent le referentiel des terminaux ET l'envoi de
    commandes destructrices (`reboot`, `cleanuser`, `cleanlog`, `opendoor`) :
    ils ne doivent jamais etre accessibles anonymement. Meme contrat que
    `devices.api.views.BaseAPIView` -- 401 JSON plutot qu'une redirection HTML
    vers le login, les appelants etant des clients JSON.

    Ces vues ne sont PAS `csrf_exempt` : l'authentification se faisant par
    cookie de session, une exemption laisserait n'importe quel site tiers
    declencher `opendoor`/`reboot`/`cleanuser` depuis le navigateur d'un
    exploitant connecte. Les appelants navigateur envoient deja le jeton via
    le helper `apiCall()` du dashboard.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {'success': False, 'error': 'Authentification requise'},
                status=401,
            )
        return super().dispatch(request, *args, **kwargs)


class TerminalListView(AuthenticatedView):
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


class TerminalDetailView(AuthenticatedView):
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


class SendCommandView(AuthenticatedView):
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
            sent = CommandService.dispatch(sn, payload)
            
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
            # `door` est l'ancien nom du parametre accepte par cet endpoint :
            # on le conserve en alias pour ne pas transformer une demande
            # d'ouverture d'UNE porte en ouverture de toutes les portes sur un
            # controleur 4 portes. Omis, la spec ouvre toutes les portes
            # (doc section S19), ce dont les terminaux mono-porte ont besoin.
            # `delay` n'existe pas dans `opendoor` : le temps de relais est
            # `opendelay` de `setdevlock` (doc section S20).
            'opendoor': lambda p: CommandBuilder.opendoor(
                p.get('doornum', p.get('door'))
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
    


class TerminalUsersView(AuthenticatedView):
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


class TerminalLogsView(AuthenticatedView):
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


class ConnectedTerminalsView(AuthenticatedView):
    """Liste des terminaux actuellement connectés"""
    
    def get(self, request):
        # Le pool en memoire du DeviceManager n'existe que dans le process
        # ASGI qui porte les WebSockets : depuis une vue HTTP, Redis est la
        # seule source de verite.
        connected = DeviceManager.get_connected_sns_from_redis()
        return JsonResponse({
            'connected': connected,
            'count': len(connected)
        })

"""
Vues du dashboard temps réel
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin

from django.db.models import Count, IntegerField, OuterRef, Subquery
from django.db.models.functions import Coalesce

from ..models import Terminal, AttendanceLog, BiometricUser, CommandQueue
from ..core.device_manager import DeviceManager
from ..core.metrics import MetricsCollector
from ..core.events import EventBus


def _count_for_terminal(model, field: str = 'terminal'):
    """Compte les lignes de `model` rattachees a chaque terminal.

    Sous-requete agregee plutot qu'un `Count()` annote : plusieurs Count()
    sur des relations inverses distinctes dans une meme requete produisent un
    produit cartesien entre ces relations, que `distinct=True` ne fait que
    dedupliquer APRES coup.
    """
    return Coalesce(
        Subquery(
            model.objects
            .filter(**{field: OuterRef('pk')})
            .order_by()
            .values(field)
            .annotate(n=Count('pk'))
            .values('n'),
            output_field=IntegerField(),
        ),
        0,
    )


class DashboardView(LoginRequiredMixin, View):
    """Vue principale du dashboard"""
    
    def get(self, request):
        return render(request, 'devices/dashboard/index.html')


class StyleguideView(LoginRequiredMixin, View):
    """Référence visuelle du design system.

    Rend chaque composant dans chaque ton et chaque état, sur une seule page.
    Vérifier les deux thèmes revient alors à basculer un bouton, au lieu de
    parcourir toutes les pages de l'application. C'est aussi le seul endroit où
    un tracé d'icône erroné se voit : il s'affiche vide.

    Réservée au diagnostic : superutilisateurs, ou n'importe qui en DEBUG.
    """

    TONES = ['brand', 'success', 'warning', 'danger', 'info', 'neutral']
    SURFACES = ['page', 'card', 'sunken', 'raised']
    ALERT_TONES = ['success', 'danger', 'warning', 'info']

    def get(self, request):
        if not (settings.DEBUG or request.user.is_superuser):
            raise Http404()
        return render(request, 'devices/dashboard/styleguide.html', {
            'tones': self.TONES,
            'surfaces': self.SURFACES,
            'alert_tones': self.ALERT_TONES,
            'icons': self._sprite_symbols(),
            'page_title': 'Référence visuelle',
        })

    @staticmethod
    def _sprite_symbols():
        """Noms lus dans le sprite : la page suit le fichier sans entretien."""
        sprite = Path(settings.BASE_DIR) / 'static' / 'icons' / 'sprite.svg'
        try:
            return sorted(re.findall(r'<symbol id="i-([^"]+)"', sprite.read_text()))
        except OSError:
            return []


class DashboardAPIView(LoginRequiredMixin, View):
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
        
        # Stats des logs (aujourd'hui). localdate() et non now().date() : la
        # journee est celle du site, pas celle d'UTC.
        today = timezone.localdate()
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
            'timestamp': timezone.now().isoformat(),
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


class TerminalsAPIView(LoginRequiredMixin, View):
    """API pour la liste des terminaux"""
    
    # Un terminal vu il y a moins de 5 min mais sans connexion live est
    # considere « au repos » plutot qu'injoignable (reconnexion en cours).
    IDLE_WINDOW_SECONDS = 300

    def get(self, request):
        """Liste des terminaux avec statut temps réel"""
        # Presence live : le pool du DeviceManager n'existe que dans le
        # process ASGI, Redis est la seule source lisible ici.
        connected_sns = DeviceManager.get_connected_sns_from_redis()
        live = DeviceManager.get_connected_details_from_redis()
        
        # Deux sous-requetes plutot que deux Count() dans la meme requete :
        # agreger d'un coup sur `users` ET `logs` joint les deux relations
        # entre elles, donc materialise utilisateurs x pointages avant de
        # dedupliquer (500 users x 200 000 logs = 100 M de lignes pour UN
        # terminal). Cet endpoint est interroge en boucle par le dashboard.
        terminals = (
            Terminal.objects.all()
            .annotate(
                users_count=_count_for_terminal(BiometricUser),
                logs_count=_count_for_terminal(AttendanceLog),
            )
            .order_by('-last_seen')
        )
        
        now = timezone.now()
        data = []
        for t in terminals:
            is_connected = t.sn in connected_sns
            status, status_class = self._compute_status(t, is_connected, now)
            session = live.get(t.sn) or {}
            
            data.append({
                # `id` sert de cle stable au rendu ; `sn` reste l'identite
                # protocolaire du terminal.
                'id': t.id,
                'sn': t.sn,
                'name': t.name,
                'display_name': t.display_name,
                'short_label': t.short_label,
                'location': t.location,
                'model': t.model or 'TM20',
                'firmware': t.firmware,
                'mac_address': t.mac_address,
                'ip_address': t.ip_address,
                'status': status,
                'status_class': status_class,
                'status_label': self.STATUS_LABELS[status],
                'is_connected': is_connected,
                'is_active': t.is_active,
                'connected_since': session.get('connected_at'),
                'connected_since_human': self._humanize_uptime(session.get('connected_at')),
                'last_message_at': session.get('last_message_at'),
                'last_seen': t.last_seen.isoformat() if t.last_seen else None,
                'last_seen_human': self._humanize_time(t.last_seen) if t.last_seen else 'Jamais',
                # Compteurs applicatifs (ce que l'application connait) et
                # compteurs terminal (ce que l'appareil a declare au `reg`).
                'users_count': t.users_count,
                'logs_count': t.logs_count,
                'used_users': t.used_users,
                'user_capacity': t.user_capacity,
                'used_logs': t.used_logs,
                'log_capacity': t.log_capacity,
            })
        
        return JsonResponse({
            'terminals': data,
            'connected_count': len(connected_sns),
            'total': len(data),
        })

    STATUS_LABELS = {
        'online': 'En ligne',
        'idle': 'Au repos',
        'offline': 'Hors ligne',
        'disabled': 'Désactivé',
    }

    def _compute_status(self, terminal, is_connected, now):
        """Statut d'affichage d'un terminal."""
        if is_connected:
            return 'online', 'success'
        if not terminal.is_active:
            return 'disabled', 'secondary'
        if terminal.last_seen:
            age = (now - terminal.last_seen).total_seconds()
            if age < self.IDLE_WINDOW_SECONDS:
                return 'idle', 'warning'
        return 'offline', 'danger'

    def _humanize_uptime(self, connected_at_iso):
        """Durée de connexion lisible, ex: « depuis 2h14 »."""
        if not connected_at_iso:
            return None
        try:
            started = datetime.fromisoformat(connected_at_iso)
        except (TypeError, ValueError):
            return None
        
        # `connected_at` est un datetime naif (horloge du process ASGI) :
        # on compare a la meme horloge.
        seconds = max(0, int((datetime.now() - started).total_seconds()))
        if seconds < 60:
            return f"{seconds}s"
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}h{minutes:02d}"
        return f"{minutes}min"
    
    def _humanize_time(self, dt):
        """Convertit un datetime en temps relatif"""
        if not dt:
            return 'Never'
        
        now = timezone.now()
        diff = now - dt
        
        if diff.total_seconds() < 60:
            return "à l'instant"
        elif diff.total_seconds() < 3600:
            mins = int(diff.total_seconds() / 60)
            return f'il y a {mins} min'
        elif diff.total_seconds() < 86400:
            hours = int(diff.total_seconds() / 3600)
            return f'il y a {hours} h'
        else:
            days = int(diff.total_seconds() / 86400)
            return f'il y a {days} j'


class LogsAPIView(LoginRequiredMixin, View):
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

        # `time_human` est une heure nue, sans offset : elle doit etre deja
        # dans le fuseau du site, sinon elle ne correspond plus a ce que le
        # terminal affichait et rien dans la chaine ne permet de le rattraper.
        # La base restitue de l'UTC, la conversion est donc explicite.
        data = []
        for log in logs:
            local_time = timezone.localtime(log.time)
            data.append({
                'id': log.id,
                'sn': log.terminal.sn,
                'enrollid': log.enrollid,
                'user_name': log.user.name if log.user else f'User #{log.enrollid}',
                'time': local_time.isoformat(),
                'time_human': local_time.strftime('%H:%M:%S'),
                'mode': log.get_mode_display(),
                'inout': log.get_inout_display(),
                'inout_class': 'success' if log.inout == 0 else 'info',
            })
        
        return JsonResponse({'logs': data})


class EventsAPIView(LoginRequiredMixin, View):
    """API pour les événements récents"""
    
    def get(self, request):
        """Récupère les événements récents"""
        event_bus = EventBus.get_instance()
        
        limit = int(request.GET.get('limit', 50))
        events = event_bus.get_recent_events(limit=limit)
        
        data = [event.to_dict() for event in events]
        
        return JsonResponse({'events': data})


class CommandAPIView(LoginRequiredMixin, View):
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
                # `door` : alias historique conserve, sans quoi une demande
                # d'ouverture d'UNE porte ouvrirait toutes les portes d'un
                # controleur 4 portes. Omis, la spec ouvre tout
                # (doc section S19), comportement attendu en mono-porte.
                'opendoor': lambda p: CommandBuilder.opendoor(
                    p.get('doornum', p.get('door'))
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
            
            # Envoi via la couche Channels (le DeviceManager en memoire
            # n'est pas accessible depuis un process HTTP).
            from ..services.commands import CommandService
            sent = CommandService.dispatch(sn, payload)
            
            if not sent:
                # Terminal hors ligne : la commande sera rejouee au prochain
                # `reg` (voir TM20ConsumerV2._send_pending_commands).
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

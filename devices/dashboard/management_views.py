"""
Vues de gestion pour le dashboard
Configurations tiers, horaires, synchronisation
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib import messages

from ..models import (
    Terminal,
    ThirdPartyConfig,
    TerminalThirdPartyMapping,
    TerminalSchedule,
    AttendanceLog,
)
from .forms import ThirdPartyConfigForm, TerminalScheduleForm, UserSyncForm
from ..services.user_sync_service import UserSyncService


class ThirdPartyConfigsView(View):
    """Vue de gestion des configurations services tiers"""
    
    def get(self, request):
        configs = ThirdPartyConfig.objects.all().order_by('-created_at')
        terminals = Terminal.objects.filter(is_active=True).order_by('sn')
        form = ThirdPartyConfigForm()
        
        return render(request, 'devices/dashboard/third_party_configs.html', {
            'configs': configs,
            'terminals': terminals,
            'form': form,
        })
    
    def post(self, request):
        form = ThirdPartyConfigForm(request.POST)
        if form.is_valid():
            config = form.save()
            messages.success(request, f'Configuration "{config.name}" créée avec succès.')
            return redirect('devices:dashboard:third_party_configs')
        else:
            configs = ThirdPartyConfig.objects.all().order_by('-created_at')
            terminals = Terminal.objects.filter(is_active=True).order_by('sn')
            messages.error(request, 'Erreur lors de la création de la configuration.')
            return render(request, 'devices/dashboard/third_party_configs.html', {
                'configs': configs,
                'terminals': terminals,
                'form': form,
            })


class TerminalSchedulesView(View):
    """Vue de gestion des horaires de terminaux"""
    
    def get(self, request, terminal_id=None):
        terminals = Terminal.objects.filter(is_active=True).order_by('sn')
        
        if terminal_id:
            terminal = get_object_or_404(Terminal, id=terminal_id)
            schedules = TerminalSchedule.objects.filter(
                terminal=terminal
            ).order_by('weekday', 'check_in_time')
            form = TerminalScheduleForm()
        else:
            terminal = None
            schedules = []
            form = None
        
        return render(request, 'devices/dashboard/terminal_schedules.html', {
            'terminals': terminals,
            'selected_terminal': terminal,
            'schedules': schedules,
            'form': form,
            'weekdays': [
                {'value': 0, 'label': 'Lundi'},
                {'value': 1, 'label': 'Mardi'},
                {'value': 2, 'label': 'Mercredi'},
                {'value': 3, 'label': 'Jeudi'},
                {'value': 4, 'label': 'Vendredi'},
                {'value': 5, 'label': 'Samedi'},
                {'value': 6, 'label': 'Dimanche'},
            ]
        })
    
    def post(self, request, terminal_id):
        terminal = get_object_or_404(Terminal, id=terminal_id)
        
        if 'delete_schedule' in request.POST:
            schedule_id = request.POST.get('schedule_id')
            schedule = get_object_or_404(TerminalSchedule, id=schedule_id, terminal=terminal)
            schedule.delete()
            messages.success(request, 'Horaire supprimé avec succès.')
        else:
            form = TerminalScheduleForm(request.POST)
            if form.is_valid():
                schedule = form.save(commit=False)
                schedule.terminal = terminal
                schedule.save()
                messages.success(request, 'Horaire créé avec succès.')
            else:
                messages.error(request, 'Erreur lors de la création de l\'horaire.')
        
        return redirect('devices:dashboard:schedules_terminal', terminal_id=terminal_id)


class UserSyncView(View):
    """Vue de synchronisation des utilisateurs"""
    
    def get(self, request):
        terminals = Terminal.objects.filter(is_active=True).order_by('sn')
        configs = ThirdPartyConfig.objects.filter(is_active=True).order_by('name')
        
        mappings = TerminalThirdPartyMapping.objects.select_related(
            'terminal', 'config'
        ).filter(is_active=True).order_by('terminal__sn')
        
        form = UserSyncForm(terminals=terminals, configs=configs)
        
        return render(request, 'devices/dashboard/user_sync.html', {
            'terminals': terminals,
            'configs': configs,
            'mappings': mappings,
            'form': form,
        })
    
    def post(self, request):
        terminals = Terminal.objects.filter(is_active=True).order_by('sn')
        configs = ThirdPartyConfig.objects.filter(is_active=True).order_by('name')
        form = UserSyncForm(request.POST, terminals=terminals, configs=configs)
        
        if form.is_valid():
            terminal_id = form.cleaned_data['terminal_id']
            config_id = form.cleaned_data.get('config_id')
            
            terminal = get_object_or_404(Terminal, id=terminal_id)
            config = None
            if config_id:
                config = get_object_or_404(ThirdPartyConfig, id=config_id)
            
            try:
                # Le UserSyncService nécessite terminal et config dans le constructeur
                sync_service = UserSyncService(terminal=terminal, config=config)
                
                # Appel asynchrone - on utilise async_to_sync pour l'exécuter
                from asgiref.sync import async_to_sync
                result = async_to_sync(sync_service.fetch_and_sync_users)()
                
                if result.success:
                    messages.success(
                        request,
                        f'Synchronisation réussie: {result.created} créés, '
                        f'{result.updated} mis à jour, {result.skipped} ignorés.'
                    )
                else:
                    error_msg = ', '.join(result.errors) if result.errors else 'Erreur inconnue'
                    messages.error(request, f'Erreur lors de la synchronisation: {error_msg}')
            except Exception as e:
                messages.error(request, f'Erreur lors de la synchronisation: {str(e)}')
        else:
            messages.error(request, 'Veuillez sélectionner un terminal.')
        
        return redirect('devices:dashboard:user_sync')


class AttendanceSyncView(View):
    """Vue de synchronisation des pointages"""
    
    def get(self, request):
        configs = ThirdPartyConfig.objects.filter(is_active=True).order_by('name')
        terminals = Terminal.objects.filter(is_active=True).order_by('sn')
        
        stats = {
            'pending': AttendanceLog.objects.filter(sync_status='pending').count(),
            'sent': AttendanceLog.objects.filter(sync_status='sent').count(),
            'failed': AttendanceLog.objects.filter(sync_status='failed').count(),
        }
        
        recent_logs = AttendanceLog.objects.select_related(
            'terminal', 'user'
        ).order_by('-time')[:100]
        
        return render(request, 'devices/dashboard/attendance_sync.html', {
            'configs': configs,
            'terminals': terminals,
            'stats': stats,
            'recent_logs': recent_logs,
        })
    
    def post(self, request):
        action = request.POST.get('action')
        
        if action == 'sync_all':
            messages.info(request, 'Synchronisation lancée en arrière-plan.')
        elif action == 'reset_failed':
            failed_count = AttendanceLog.objects.filter(sync_status='failed').update(
                sync_status='pending',
                retry_count=0
            )
            messages.success(request, f'{failed_count} pointages réinitialisés pour retry.')
        
        return redirect('devices:dashboard:attendance_sync')


class ManagementDashboardView(View):
    """Vue principale du dashboard de gestion"""
    
    def get(self, request):
        terminals_count = Terminal.objects.filter(is_active=True).count()
        configs_count = ThirdPartyConfig.objects.filter(is_active=True).count()
        schedules_count = TerminalSchedule.objects.filter(is_active=True).count()
        
        pending_attendance = AttendanceLog.objects.filter(sync_status='pending').count()
        failed_attendance = AttendanceLog.objects.filter(sync_status='failed').count()
        
        recent_mappings = TerminalThirdPartyMapping.objects.select_related(
            'terminal', 'config'
        ).filter(is_active=True).order_by('-updated_at')[:5]
        
        return render(request, 'devices/dashboard/management.html', {
            'terminals_count': terminals_count,
            'configs_count': configs_count,
            'schedules_count': schedules_count,
            'pending_attendance': pending_attendance,
            'failed_attendance': failed_attendance,
            'recent_mappings': recent_mappings,
        })

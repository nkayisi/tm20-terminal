"""
Vues de gestion pour le dashboard
Configurations tiers, horaires, synchronisation
"""

from django.shortcuts import render, get_object_or_404
from django.views import View
from django.http import JsonResponse
from asgiref.sync import async_to_sync

from ..models import (
    Terminal,
    ThirdPartyConfig,
    TerminalThirdPartyMapping,
    TerminalSchedule,
    AttendanceLog,
)
from ..services.schedule_manager import ScheduleManager


class ThirdPartyConfigsView(View):
    """Vue de gestion des configurations services tiers"""
    
    def get(self, request):
        configs = ThirdPartyConfig.objects.all().order_by('-created_at')
        terminals = Terminal.objects.filter(is_active=True).order_by('sn')
        
        return render(request, 'devices/dashboard/third_party_configs.html', {
            'configs': configs,
            'terminals': terminals,
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
            
            summary = async_to_sync(ScheduleManager.get_schedule_summary)(terminal)
        else:
            terminal = None
            schedules = []
            summary = None
        
        return render(request, 'devices/dashboard/terminal_schedules.html', {
            'terminals': terminals,
            'selected_terminal': terminal,
            'schedules': schedules,
            'summary': summary,
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


class UserSyncView(View):
    """Vue de synchronisation des utilisateurs"""
    
    def get(self, request):
        terminals = Terminal.objects.filter(is_active=True).order_by('sn')
        configs = ThirdPartyConfig.objects.filter(is_active=True).order_by('name')
        
        mappings = TerminalThirdPartyMapping.objects.select_related(
            'terminal', 'config'
        ).filter(is_active=True).order_by('terminal__sn')
        
        return render(request, 'devices/dashboard/user_sync.html', {
            'terminals': terminals,
            'configs': configs,
            'mappings': mappings,
        })


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

"""
Admin Django pour les modèles TM20
"""

from django.contrib import admin

from .models import (
    AttendanceLog,
    BiometricCredential,
    BiometricUser,
    CommandQueue,
    Terminal,
    ThirdPartyConfig,
    TerminalSchedule,
    TerminalThirdPartyMapping,
)


@admin.register(Terminal)
class TerminalAdmin(admin.ModelAdmin):
    list_display = [
        'sn', 'model', 'firmware', 'is_active', 'is_whitelisted',
        'used_users', 'user_capacity', 'last_seen'
    ]
    list_filter = ['is_active', 'is_whitelisted', 'model']
    search_fields = ['sn', 'cpusn', 'mac_address']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Identification', {
            'fields': ('sn', 'cpusn', 'model', 'firmware', 'mac_address', 'fp_algo')
        }),
        ('Capacités', {
            'fields': (
                ('user_capacity', 'used_users'),
                ('fp_capacity', 'used_fp'),
                ('card_capacity', 'used_cards'),
                ('log_capacity', 'used_logs'),
            )
        }),
        ('Statut', {
            'fields': ('is_active', 'is_whitelisted', 'last_seen')
        }),
        ('Métadonnées', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(BiometricUser)
class BiometricUserAdmin(admin.ModelAdmin):
    list_display = ['enrollid', 'name', 'terminal', 'admin', 'is_enabled', 'sync_status', 'created_at']
    list_filter = ['terminal', 'admin', 'is_enabled', 'sync_status']
    search_fields = ['enrollid', 'name', 'terminal__sn']
    raw_id_fields = ['terminal']
    
    fieldsets = (
        ('Identification', {
            'fields': ('terminal', 'enrollid', 'name', 'admin')
        }),
        ('Accès', {
            'fields': ('is_enabled', 'group', 'weekzone', 'weekzone2', 'weekzone3', 'weekzone4')
        }),
        ('Validité', {
            'fields': ('starttime', 'endtime')
        }),
    )


@admin.register(BiometricCredential)
class BiometricCredentialAdmin(admin.ModelAdmin):
    list_display = ['user', 'backupnum', 'get_type', 'created_at']
    list_filter = ['backupnum']
    search_fields = ['user__enrollid', 'user__name']
    raw_id_fields = ['user']
    
    def get_type(self, obj):
        return obj.get_backupnum_display()
    get_type.short_description = 'Type'


@admin.register(AttendanceLog)
class AttendanceLogAdmin(admin.ModelAdmin):
    list_display = [
        'terminal', 'enrollid', 'get_user_name', 'time',
        'mode', 'get_inout_status', 'access_granted', 'sync_status'
    ]
    list_filter = ['terminal', 'mode', 'inout', 'access_granted', 'sync_status', 'time']
    search_fields = ['enrollid', 'user__name', 'terminal__sn']
    raw_id_fields = ['terminal', 'user']
    date_hierarchy = 'time'
    readonly_fields = ['created_at', 'synced_at']
    
    def get_user_name(self, obj):
        return obj.user.name if obj.user else '-'
    get_user_name.short_description = 'Utilisateur'
    
    def get_inout_status(self, obj):
        """Affiche le statut entrée/sortie avec icône et couleur"""
        if obj.is_entry:
            return "🟢 Entrée"
        return "🔴 Sortie"
    get_inout_status.short_description = 'Entrée/Sortie'


@admin.register(CommandQueue)
class CommandQueueAdmin(admin.ModelAdmin):
    list_display = ['terminal', 'command', 'status', 'created_at', 'sent_at', 'completed_at']
    list_filter = ['status', 'command', 'terminal']
    search_fields = ['terminal__sn', 'command']
    raw_id_fields = ['terminal']
    readonly_fields = ['created_at', 'sent_at', 'completed_at']


@admin.register(ThirdPartyConfig)
class ThirdPartyConfigAdmin(admin.ModelAdmin):
    list_display = ['name', 'base_url', 'auth_type', 'is_active', 'sync_interval_minutes', 'created_at']
    list_filter = ['is_active', 'auth_type']
    search_fields = ['name', 'base_url']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Informations générales', {
            'fields': ('name', 'description', 'is_active')
        }),
        ('Configuration API', {
            'fields': ('base_url', 'users_endpoint', 'attendance_endpoint')
        }),
        ('Authentification', {
            'fields': ('auth_type', 'auth_token', 'auth_header_name', 'extra_headers')
        }),
        ('Paramètres de synchronisation', {
            'fields': ('sync_interval_minutes', 'timeout_seconds', 'retry_attempts')
        }),
        ('Métadonnées', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TerminalSchedule)
class TerminalScheduleAdmin(admin.ModelAdmin):
    list_display = ['terminal', 'name', 'weekday', 'check_in_time', 'check_out_time', 'is_active']
    list_filter = ['terminal', 'weekday', 'is_active']
    search_fields = ['terminal__sn', 'name']
    raw_id_fields = ['terminal']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Terminal', {
            'fields': ('terminal', 'name')
        }),
        ('Horaires', {
            'fields': (
                'weekday',
                'check_in_time',
                'check_out_time',
                'break_start_time',
                'break_end_time',
                'tolerance_minutes',
            )
        }),
        ('Validité', {
            'fields': ('is_active', 'effective_from', 'effective_until')
        }),
    )


@admin.register(TerminalThirdPartyMapping)
class TerminalThirdPartyMappingAdmin(admin.ModelAdmin):
    list_display = ['terminal', 'config', 'is_active', 'sync_users', 'sync_attendance', 'last_user_sync', 'last_attendance_sync']
    list_filter = ['is_active', 'sync_users', 'sync_attendance', 'config']
    search_fields = ['terminal__sn', 'config__name']
    raw_id_fields = ['terminal', 'config']
    readonly_fields = ['last_user_sync', 'last_attendance_sync', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Mapping', {
            'fields': ('terminal', 'config', 'is_active')
        }),
        ('Options de synchronisation', {
            'fields': ('sync_users', 'sync_attendance')
        }),
        ('Dernières synchronisations', {
            'fields': ('last_user_sync', 'last_attendance_sync'),
            'classes': ('collapse',)
        }),
    )

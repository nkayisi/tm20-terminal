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
    list_display = ['enrollid', 'name', 'terminal', 'admin', 'is_enabled', 'created_at']
    list_filter = ['terminal', 'admin', 'is_enabled']
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
        'mode', 'inout', 'access_granted'
    ]
    list_filter = ['terminal', 'mode', 'inout', 'access_granted', 'time']
    search_fields = ['enrollid', 'user__name', 'terminal__sn']
    raw_id_fields = ['terminal', 'user']
    date_hierarchy = 'time'
    
    def get_user_name(self, obj):
        return obj.user.name if obj.user else '-'
    get_user_name.short_description = 'Utilisateur'


@admin.register(CommandQueue)
class CommandQueueAdmin(admin.ModelAdmin):
    list_display = ['terminal', 'command', 'status', 'created_at', 'sent_at', 'completed_at']
    list_filter = ['status', 'command', 'terminal']
    search_fields = ['terminal__sn', 'command']
    raw_id_fields = ['terminal']
    readonly_fields = ['created_at', 'sent_at', 'completed_at']

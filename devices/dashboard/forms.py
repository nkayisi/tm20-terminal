"""
Formulaires Django pour le dashboard de gestion
"""

from django import forms
from ..models import ThirdPartyConfig, TerminalSchedule, TerminalThirdPartyMapping


class ThirdPartyConfigForm(forms.ModelForm):
    """Formulaire de création/édition d'une configuration service tiers"""
    
    class Meta:
        model = ThirdPartyConfig
        fields = [
            'name', 'base_url', 'description', 'auth_type', 'auth_token',
            'users_endpoint', 'attendance_endpoint', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent',
                'placeholder': 'Ex: API RH'
            }),
            'base_url': forms.URLInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent',
                'placeholder': 'https://api.example.com'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent',
                'rows': 2,
                'placeholder': 'Description optionnelle'
            }),
            'auth_type': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent'
            }),
            'auth_token': forms.PasswordInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent',
                'placeholder': 'Votre token'
            }),
            'users_endpoint': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent',
                'placeholder': '/api/users'
            }),
            'attendance_endpoint': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent',
                'placeholder': '/api/attendance'
            }),
            'sync_interval_minutes': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent',
                'min': 1
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            }),
        }


class TerminalScheduleForm(forms.ModelForm):
    """Formulaire de création/édition d'un horaire de terminal"""
    
    class Meta:
        model = TerminalSchedule
        fields = [
            'name', 'weekday', 'check_in_time', 'check_out_time',
            'break_start_time', 'break_end_time', 'tolerance_minutes', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent',
                'placeholder': 'Ex: Horaire standard'
            }),
            'weekday': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent'
            }),
            'check_in_time': forms.TimeInput(attrs={
                'type': 'time',
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent'
            }),
            'check_out_time': forms.TimeInput(attrs={
                'type': 'time',
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent'
            }),
            'break_start_time': forms.TimeInput(attrs={
                'type': 'time',
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent'
            }),
            'break_end_time': forms.TimeInput(attrs={
                'type': 'time',
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent'
            }),
            'tolerance_minutes': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent',
                'min': 0,
                'value': 15
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            }),
        }


class UserSyncForm(forms.Form):
    """Formulaire de synchronisation des utilisateurs"""
    
    terminal_id = forms.IntegerField(
        widget=forms.Select(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent'
        })
    )
    config_id = forms.IntegerField(
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent'
        })
    )
    
    def __init__(self, *args, **kwargs):
        terminals = kwargs.pop('terminals', [])
        configs = kwargs.pop('configs', [])
        super().__init__(*args, **kwargs)
        
        self.fields['terminal_id'].widget.choices = [('', 'Sélectionnez un terminal')] + [
            (t.id, f"{t.sn} - {t.model or 'TM20'}") for t in terminals
        ]
        self.fields['config_id'].widget.choices = [('', 'Auto-détection')] + [
            (c.id, c.name) for c in configs
        ]

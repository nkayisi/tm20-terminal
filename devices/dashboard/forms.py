"""
Formulaires Django pour le dashboard de gestion
"""

from django import forms
from ..models import (
    Terminal,
    ThirdPartyConfig,
    TerminalSchedule,
    TerminalThirdPartyMapping,
)


class ThirdPartyConfigForm(forms.ModelForm):
    """Formulaire de création/édition d'une configuration service tiers"""
    
    class Meta:
        model = ThirdPartyConfig
        fields = [
            'name', 'base_url', 'description', 'auth_type', 'auth_token',
            'auth_header_name', 'extra_headers',
            'users_endpoint', 'attendance_endpoint',
            'sync_interval_minutes', 'timeout_seconds', 'retry_attempts',
            'is_active',
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
            'auth_header_name': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent',
                'placeholder': 'Ex: X-API-Key'
            }),
            'extra_headers': forms.Textarea(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent',
                'rows': 2,
                'placeholder': '{"X-Tenant": "acme"}'
            }),
            'timeout_seconds': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent', 'min': 1}),
            'retry_attempts': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent', 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            }),
        }

    def clean_auth_header_name(self):
        """Champ facultatif, avec repli sur le défaut du modèle.

        `auth_header_name` porte un `default` mais pas `blank=True` : l'exposer
        tel quel le rendait obligatoire, y compris pour `auth_type='none'` où
        il n'a aucun sens. Vide = on garde la valeur par défaut.
        """
        name = (self.cleaned_data.get('auth_header_name') or '').strip()
        if name:
            return name
        return self.Meta.model._meta.get_field('auth_header_name').default

    def clean_extra_headers(self):
        """Un en-tete supplementaire doit etre un objet JSON.

        Sans cette garde, une liste ou une chaine passe la validation du
        JSONField et fait exploser l'adaptateur HTTP au moment de la synchro,
        loin du formulaire qui a introduit l'erreur.
        """
        headers = self.cleaned_data.get('extra_headers')
        if headers in (None, '', {}):
            return {}
        if not isinstance(headers, dict):
            raise forms.ValidationError(
                "Les en-tetes doivent etre un objet JSON, par exemple "
                '{"X-Tenant": "acme"}.'
            )
        return headers

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['auth_header_name'].required = False

        # Le token n'est jamais renvoyé au navigateur (PasswordInput) : en
        # édition, un champ laissé vide signifie « conserver le token actuel ».
        if self.instance.pk:
            self.fields['auth_token'].widget.attrs['placeholder'] = (
                'Laisser vide pour conserver le token actuel'
            )

    def clean_auth_token(self):
        token = self.cleaned_data.get('auth_token')
        if not token and self.instance.pk:
            return self.instance.auth_token
        return token


class TerminalScheduleForm(forms.ModelForm):
    """Formulaire de création/édition d'un horaire de terminal"""
    
    class Meta:
        model = TerminalSchedule
        fields = [
            'name', 'weekday', 'check_in_time', 'check_out_time',
            'break_start_time', 'break_end_time', 'tolerance_minutes',
            'effective_from', 'effective_until', 'is_active',
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
            'effective_from': forms.DateInput(attrs={'type': 'date', 'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent'}),
            'effective_until': forms.DateInput(attrs={'type': 'date', 'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent'}),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            }),
        }


class TerminalMappingForm(forms.ModelForm):
    """Association d'un terminal a un service tiers.

    Sans mapping, `UserSyncView` echoue sur « Aucune configuration trouvee pour
    ce terminal » et la synchronisation automatique des pointages ne fait rien.
    C'etait jusqu'ici la seule operation vraiment bloquante qui imposait un
    passage par l'admin Django.
    """

    class Meta:
        model = TerminalThirdPartyMapping
        fields = ['terminal', 'config', 'sync_users', 'sync_attendance', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Libelles des listes : `short_label` est le vocabulaire unique de
        # l'application pour nommer un terminal.
        self.fields['terminal'].queryset = Terminal.objects.order_by('sn')
        self.fields['terminal'].label_from_instance = lambda t: t.short_label
        self.fields['config'].queryset = ThirdPartyConfig.objects.order_by('name')
        self.fields['config'].label_from_instance = (
            lambda c: c.name if c.is_active else f'{c.name} (inactif)'
        )
        self.fields['terminal'].empty_label = 'Choisir un terminal'
        self.fields['config'].empty_label = 'Choisir un service'

    def clean(self):
        """Traduit la contrainte d'unicite en message utile.

        `unique_together` produit sinon un message generique qui ne dit pas
        quoi faire. Ici, le mapping existe deja : il faut le modifier, pas le
        recreer.
        """
        cleaned = super().clean()
        terminal, config = cleaned.get('terminal'), cleaned.get('config')
        if terminal and config:
            existing = TerminalThirdPartyMapping.objects.filter(
                terminal=terminal, config=config
            ).exclude(pk=self.instance.pk).first()
            if existing:
                raise forms.ValidationError(
                    f"{terminal.short_label} est déjà associé à « {config.name} ». "
                    "Modifiez l'association existante plutôt que d'en créer une seconde."
                )
        return cleaned


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

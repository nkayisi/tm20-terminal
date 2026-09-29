"""
Vues de gestion pour le dashboard
Configurations tiers, horaires, synchronisation
"""

from django.db.models import Count
from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin

from ..models import (
    Terminal,
    ThirdPartyConfig,
    TerminalThirdPartyMapping,
    TerminalSchedule,
    AttendanceLog,
)
from .forms import (
    ThirdPartyConfigForm,
    TerminalScheduleForm,
    TerminalMappingForm,
    UserSyncForm,
)
from ..services.user_sync_service import UserSyncService
from ..core.device_manager import DeviceManager


def _terminals_with_status():
    """Terminaux gérés (is_active=True) annotés d'un statut de connexion live.

    `is_active` est le drapeau d'administration (« terminal géré »). L'état
    en ligne/hors-ligne, lui, est lu depuis Redis (DeviceManager) : source
    fiable et partagée entre les processus HTTP et WebSocket. Chaque terminal
    reçoit un attribut booléen `is_online`.
    """
    connected = set(DeviceManager.get_connected_sns_from_redis())
    # `schedules_count` est annote ici : le template l'affiche dans une
    # boucle, et un `terminal.schedules.count` y declenchait un COUNT par
    # terminal a chaque rendu.
    terminals = list(
        Terminal.objects.filter(is_active=True)
        .annotate(schedules_count=Count('schedules'))
        .order_by('sn')
    )
    for t in terminals:
        t.is_online = t.sn in connected
    return terminals


def _config_form_prefix(config_id):
    """Préfixe unique par configuration.

    Plusieurs formulaires d'édition coexistent sur la page (une modale par
    service) : le préfixe évite la collision des `name`/`id` des champs.
    """
    return f'config-{config_id}'


def _render_third_party_configs(request, create_form=None, edit_form=None, open_modal=None):
    """Rend la page des services tiers.

    Chaque configuration porte son propre `edit_form` pré-rempli, utilisé par
    la modale d'édition. `open_modal` (id DOM) permet de rouvrir automatiquement
    la modale concernée lorsqu'une soumission a échoué, afin que les erreurs de
    validation restent visibles.
    """
    configs = list(ThirdPartyConfig.objects.all().order_by('-created_at'))
    for config in configs:
        if edit_form is not None and edit_form.instance.pk == config.pk:
            config.edit_form = edit_form
        else:
            config.edit_form = ThirdPartyConfigForm(
                instance=config,
                prefix=_config_form_prefix(config.pk),
            )

    return render(request, 'devices/dashboard/third_party_configs.html', {
        'configs': configs,
        'terminals': _terminals_with_status(),
        'form': create_form if create_form is not None else ThirdPartyConfigForm(),
        'open_modal': open_modal,
    })


class ThirdPartyConfigsView(LoginRequiredMixin, View):
    """Vue de gestion des configurations services tiers"""

    def get(self, request):
        return _render_third_party_configs(request)

    def post(self, request):
        form = ThirdPartyConfigForm(request.POST)
        if form.is_valid():
            config = form.save()
            messages.success(request, f'Configuration "{config.name}" créée avec succès.')
            return redirect('dashboard:third_party_configs')

        messages.error(request, 'Erreur lors de la création de la configuration.')
        return _render_third_party_configs(
            request, create_form=form, open_modal='addConfigModal'
        )


class ThirdPartyConfigEditView(LoginRequiredMixin, View):
    """Édition d'une configuration service tiers depuis la liste"""

    def post(self, request, config_id):
        config = get_object_or_404(ThirdPartyConfig, id=config_id)
        form = ThirdPartyConfigForm(
            request.POST,
            instance=config,
            prefix=_config_form_prefix(config_id),
        )
        if form.is_valid():
            config = form.save()
            messages.success(request, f'Configuration "{config.name}" mise à jour.')
            return redirect('dashboard:third_party_configs')

        messages.error(request, 'Erreur lors de la mise à jour de la configuration.')
        return _render_third_party_configs(
            request, edit_form=form, open_modal=f'editConfigModal-{config_id}'
        )


class TerminalSchedulesView(LoginRequiredMixin, View):
    """Vue de gestion des horaires de terminaux"""
    
    def get(self, request, terminal_id=None):
        terminals = _terminals_with_status()
        
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
        
        return redirect('dashboard:schedules_terminal', terminal_id=terminal_id)


class UserSyncView(LoginRequiredMixin, View):
    """Vue de synchronisation des utilisateurs"""
    
    def get(self, request, mapping_form=None, open_mapping_modal=False):
        terminals = _terminals_with_status()
        configs = ThirdPartyConfig.objects.filter(is_active=True).order_by('name')

        # Tous les mappings, pas seulement les actifs : un mapping desactive
        # doit rester visible pour pouvoir etre reactive ou supprime, sinon il
        # devient invisible et seul l'admin Django permet d'y revenir.
        mappings = TerminalThirdPartyMapping.objects.select_related(
            'terminal', 'config'
        ).order_by('-is_active', 'terminal__sn')

        form = UserSyncForm(terminals=terminals, configs=configs)

        return render(request, 'devices/dashboard/user_sync.html', {
            'terminals': terminals,
            'configs': configs,
            'mappings': mappings,
            'active_mappings_count': sum(1 for m in mappings if m.is_active),
            'form': form,
            'mapping_form': mapping_form or TerminalMappingForm(),
            'open_mapping_modal': open_mapping_modal,
            'mapping_form_id': request.POST.get('mapping_id', ''),
            'connected_count': sum(1 for t in terminals if t.is_online),
        })
    
    def post(self, request):
        from asgiref.sync import async_to_sync
        from ..services.user_sync_service import UserSyncService, UserSyncManager
        
        terminals = _terminals_with_status()
        configs = ThirdPartyConfig.objects.filter(is_active=True).order_by('name')
        
        action = request.POST.get('action', 'sync_from_service')

        if action == 'save_mapping':
            return self._save_mapping(request)

        if action == 'delete_mapping':
            return self._delete_mapping(request)

        if action == 'push_to_terminal':
            terminal_id = request.POST.get('terminal_id')
            
            if terminal_id:
                try:
                    result = async_to_sync(UserSyncManager.push_terminal_users)(int(terminal_id))
                    
                    if result.success:
                        messages.success(
                            request,
                            f'Envoi réussi: {result.created} utilisateurs envoyés vers le terminal.'
                        )
                    else:
                        error_msg = ', '.join(result.errors) if result.errors else 'Erreur inconnue'
                        messages.error(request, f'Erreur lors de l\'envoi: {error_msg}')
                except Exception as e:
                    messages.error(request, f'Erreur lors de l\'envoi vers le terminal: {str(e)}')
            else:
                messages.error(request, 'Veuillez sélectionner un terminal.')
        
        elif action == 'push_all_to_terminals':
            try:
                results = async_to_sync(UserSyncManager.push_all_users_to_terminals)()
                
                total_sent = sum(r.created for r in results.values())
                total_failed = sum(r.skipped for r in results.values())
                
                if total_sent > 0:
                    messages.success(
                        request,
                        f'Synchronisation complète: {total_sent} utilisateurs envoyés vers {len(results)} terminaux. '
                        f'{total_failed} échecs.'
                    )
                else:
                    messages.info(request, 'Aucun utilisateur en attente de synchronisation.')
            except Exception as e:
                messages.error(request, f'Erreur lors de la synchronisation globale: {str(e)}')
        
        else:
            form = UserSyncForm(request.POST, terminals=terminals, configs=configs)
            
            if form.is_valid():
                terminal_id = form.cleaned_data['terminal_id']
                config_id = form.cleaned_data.get('config_id')
                
                terminal = get_object_or_404(Terminal, id=terminal_id)
                config = None
                if config_id:
                    config = get_object_or_404(ThirdPartyConfig, id=config_id)
                
                try:
                    sync_service = UserSyncService(terminal=terminal, config=config)
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

        return redirect('dashboard:user_sync')

    # -- Associations terminal <-> service tiers ------------------------------
    #
    # Un mapping est le prerequis de toute synchronisation : sans lui,
    # `UserSyncService` ne trouve aucune configuration pour le terminal. Le
    # creer imposait jusqu'ici de passer par l'admin Django.

    def _save_mapping(self, request):
        """Cree ou met a jour une association. L'id vide vaut creation."""
        mapping_id = request.POST.get('mapping_id') or None
        instance = None
        if mapping_id:
            instance = get_object_or_404(TerminalThirdPartyMapping, pk=mapping_id)

        form = TerminalMappingForm(request.POST, instance=instance)
        if not form.is_valid():
            # Re-rendu plutot que redirection : une redirection perdrait la
            # saisie et le motif du refus. L'erreur n'est affichee QUE dans la
            # modale -- la pousser aussi dans `messages` la ferait apparaitre
            # deux fois sur la meme page.
            return self.get(request, mapping_form=form, open_mapping_modal=True)

        mapping = form.save()
        messages.success(
            request,
            f'Association enregistrée : {mapping.terminal.short_label} ↔ {mapping.config.name}.'
        )
        return redirect('dashboard:user_sync')

    def _delete_mapping(self, request):
        mapping = get_object_or_404(
            TerminalThirdPartyMapping, pk=request.POST.get('mapping_id')
        )
        label = f'{mapping.terminal.short_label} ↔ {mapping.config.name}'
        mapping.delete()
        messages.success(request, f'Association supprimée : {label}.')
        return redirect('dashboard:user_sync')


class AttendanceSyncView(LoginRequiredMixin, View):
    """Vue de synchronisation des pointages"""
    
    def get(self, request):
        configs = ThirdPartyConfig.objects.filter(is_active=True).order_by('name')
        terminals = _terminals_with_status()
        
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
            # Déclencher la synchronisation de tous les pointages en attente
            from asgiref.sync import async_to_sync
            from ..services.attendance_sync_service import AttendanceSyncManager
            
            try:
                results = async_to_sync(AttendanceSyncManager.sync_all_pending)()
                
                total_sent = sum(r.sent for r in results.values())
                total_failed = sum(r.failed for r in results.values())
                
                if total_failed == 0:
                    messages.success(
                        request,
                        f'Synchronisation réussie : {total_sent} pointages envoyés.'
                    )
                else:
                    messages.warning(
                        request,
                        f'Synchronisation partielle : {total_sent} envoyés, {total_failed} échoués.'
                    )
            except Exception as e:
                messages.error(request, f'Erreur lors de la synchronisation : {str(e)}')
        
        elif action == 'sync_config':
            # Synchroniser les pointages pour une configuration spécifique
            from asgiref.sync import async_to_sync
            from ..services.attendance_sync_service import AttendanceSyncManager
            
            config_id = request.POST.get('config_id')
            if not config_id:
                messages.error(request, 'Configuration non spécifiée.')
                return redirect('dashboard:attendance_sync')
            
            try:
                result = async_to_sync(AttendanceSyncManager.sync_config_attendance)(
                    config_id=int(config_id)
                )
                
                if result.failed == 0:
                    messages.success(
                        request,
                        f'Synchronisation réussie : {result.sent} pointages envoyés.'
                    )
                else:
                    messages.warning(
                        request,
                        f'Synchronisation partielle : {result.sent} envoyés, {result.failed} échoués.'
                    )
            except Exception as e:
                messages.error(request, f'Erreur lors de la synchronisation : {str(e)}')
        
        elif action == 'reset_failed':
            from asgiref.sync import async_to_sync
            from ..services.attendance_sync_service import AttendanceSyncManager
            
            try:
                count = async_to_sync(AttendanceSyncManager.reset_failed_logs)(all_failed=True)
                messages.success(request, f'{count} pointages réinitialisés pour retry.')
            except Exception as e:
                messages.error(request, f'Erreur lors de la réinitialisation : {str(e)}')
        
        return redirect('dashboard:attendance_sync')

"""
Gestion des associations terminal <-> service tiers depuis le dashboard.

Un mapping est le prérequis de toute synchronisation : sans lui,
`UserSyncService` ne trouve aucune configuration pour le terminal et la
synchronisation automatique des pointages ne fait rien. C'était la seule
opération vraiment bloquante qui imposait un passage par l'admin Django.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from devices.models import Terminal, ThirdPartyConfig, TerminalThirdPartyMapping


class MappingCrudTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('op', password='x')
        self.client.force_login(self.user)
        self.terminal = Terminal.objects.create(sn='ZYTJ20128568', model='TH900')
        self.config = ThirdPartyConfig.objects.create(
            name='API RH', base_url='https://rh.example.com', auth_type='none',
        )
        self.url = reverse('dashboard:user_sync')

    def _payload(self, **overrides):
        data = {
            'action': 'save_mapping',
            'mapping_id': '',
            'terminal': self.terminal.pk,
            'config': self.config.pk,
            'sync_users': 'on',
            'sync_attendance': 'on',
            'is_active': 'on',
        }
        data.update(overrides)
        return {k: v for k, v in data.items() if v is not None}

    def test_create(self):
        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, 302)
        mapping = TerminalThirdPartyMapping.objects.get()
        self.assertEqual(mapping.terminal, self.terminal)
        self.assertEqual(mapping.config, self.config)
        self.assertTrue(mapping.sync_users)
        self.assertTrue(mapping.sync_attendance)

    def test_create_unblocks_synchronisation(self):
        """Le vrai critère : le service trouve désormais une configuration."""
        self.assertIsNone(
            TerminalThirdPartyMapping.objects.filter(
                terminal=self.terminal, is_active=True).first()
        )
        self.client.post(self.url, self._payload())
        self.assertIsNotNone(
            TerminalThirdPartyMapping.objects.filter(
                terminal=self.terminal, is_active=True).first()
        )

    def test_update_keeps_a_single_row(self):
        self.client.post(self.url, self._payload())
        mapping = TerminalThirdPartyMapping.objects.get()

        # Case absente = decochee : on coupe le sens « pointages ».
        self.client.post(self.url, self._payload(
            mapping_id=mapping.pk, sync_attendance=None))

        mapping.refresh_from_db()
        self.assertTrue(mapping.sync_users)
        self.assertFalse(mapping.sync_attendance)
        self.assertEqual(TerminalThirdPartyMapping.objects.count(), 1)

    def test_duplicate_is_refused_with_actionable_message(self):
        self.client.post(self.url, self._payload())
        response = self.client.post(self.url, self._payload(), follow=True)

        self.assertEqual(TerminalThirdPartyMapping.objects.count(), 1)
        self.assertContains(response, 'est déjà associé à')

    def test_success_message_appears_once(self):
        """base.html rend les messages ; une page qui les rendait aussi les
        affichait en double, avec deux styles differents."""
        self.client.post(self.url, self._payload())
        html = self.client.get(self.url).content.decode()
        self.assertEqual(html.count('Association enregistrée'), 1)

    def test_duplicate_shows_a_single_explanation(self):
        """Django ajoutait son propre message d'unicite par-dessus le notre,
        et le formulaire poussait le sien dans `messages` : trois alertes pour
        un seul probleme."""
        self.client.post(self.url, self._payload())
        html = self.client.post(self.url, self._payload()).content.decode()

        self.assertEqual(html.count('est déjà associé à'), 1)
        self.assertNotIn('existe déjà', html)

    def test_invalid_form_reopens_the_modal_with_the_input(self):
        """Sinon l'erreur s'affiche sur une modale fermee, saisie perdue."""
        self.client.post(self.url, self._payload())
        response = self.client.post(self.url, self._payload())

        self.assertTrue(response.context['open_mapping_modal'])
        self.assertEqual(
            response.context['mapping_form']['terminal'].value(),
            str(self.terminal.pk),
        )

    def test_delete(self):
        self.client.post(self.url, self._payload())
        mapping = TerminalThirdPartyMapping.objects.get()

        self.client.post(self.url, {'action': 'delete_mapping', 'mapping_id': mapping.pk})
        self.assertEqual(TerminalThirdPartyMapping.objects.count(), 0)

    def test_deactivated_mapping_stays_listed(self):
        """Sinon il disparaît de l'écran et seul l'admin permet d'y revenir."""
        self.client.post(self.url, self._payload(is_active=None))
        mapping = TerminalThirdPartyMapping.objects.get()
        self.assertFalse(mapping.is_active)

        response = self.client.get(self.url)
        self.assertIn(mapping, response.context['mappings'])

    def test_anonymous_cannot_create(self):
        self.client.logout()
        self.client.post(self.url, self._payload())
        self.assertEqual(TerminalThirdPartyMapping.objects.count(), 0)

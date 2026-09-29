"""
Tests des formulaires du dashboard.

Ces formulaires sont la seule alternative à l'admin Django pour un exploitant.
Un champ présent dans `Meta.fields` mais absent du gabarit ne provoque aucune
erreur : il est simplement soumis vide. Pour une case à cocher, Django lit
cette absence comme « décochée » et écrase le défaut du modèle. C'est
silencieux, et c'est ce que verrouillent les tests ci-dessous.
"""

from django import forms
from django.test import TestCase

from devices.dashboard.forms import ThirdPartyConfigForm, TerminalScheduleForm
from devices.models import ThirdPartyConfig


SCHEDULE_POST = {
    'name': 'Horaire standard',
    'weekday': '0',
    'check_in_time': '08:00',
    'check_out_time': '17:00',
    'tolerance_minutes': '15',
}


class TerminalScheduleFormTests(TestCase):
    def test_new_schedule_is_active_by_default(self):
        """La case doit être cochée à l'ouverture, comme le défaut du modèle."""
        self.assertIs(TerminalScheduleForm()['is_active'].value(), True)

    def test_checked_box_keeps_schedule_active(self):
        form = TerminalScheduleForm({**SCHEDULE_POST, 'is_active': 'on'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.save(commit=False).is_active)

    def test_unchecked_box_deactivates_schedule(self):
        """Décocher doit désactiver : c'est le seul moyen de le faire depuis le web."""
        form = TerminalScheduleForm(SCHEDULE_POST)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.save(commit=False).is_active)

    def test_validity_dates_are_editable(self):
        """`is_currently_effective()` en dépend ; sans eux, l'admin restait obligatoire."""
        form = TerminalScheduleForm({
            **SCHEDULE_POST,
            'is_active': 'on',
            'effective_from': '2026-01-01',
            'effective_until': '2026-12-31',
        })
        self.assertTrue(form.is_valid(), form.errors)
        schedule = form.save(commit=False)
        self.assertEqual(str(schedule.effective_from), '2026-01-01')
        self.assertEqual(str(schedule.effective_until), '2026-12-31')


class ThirdPartyConfigFormTests(TestCase):
    """Les 5 champs qui n'étaient réglables que dans l'admin Django."""

    def test_advanced_fields_are_exposed(self):
        expected = {
            'auth_header_name', 'extra_headers',
            'sync_interval_minutes', 'timeout_seconds', 'retry_attempts',
        }
        self.assertTrue(expected.issubset(set(ThirdPartyConfigForm().fields)))

    def test_extra_headers_must_be_a_json_object(self):
        """Une liste passe la validation du JSONField et casse l'adaptateur HTTP."""
        form = ThirdPartyConfigForm({
            'name': 'API RH', 'base_url': 'https://api.example.com',
            'auth_type': 'none', 'users_endpoint': '/u',
            'attendance_endpoint': '/a', 'sync_interval_minutes': '15',
            'timeout_seconds': '30', 'retry_attempts': '3',
            'extra_headers': '["pas", "un", "objet"]',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('extra_headers', form.errors)

    def test_empty_extra_headers_becomes_empty_dict(self):
        form = ThirdPartyConfigForm({
            'name': 'API RH', 'base_url': 'https://api.example.com',
            'auth_type': 'none', 'users_endpoint': '/u',
            'attendance_endpoint': '/a', 'sync_interval_minutes': '15',
            'timeout_seconds': '30', 'retry_attempts': '3',
            'extra_headers': '',
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['extra_headers'], {})

    def test_blank_token_keeps_the_stored_one(self):
        """Le token n'est jamais renvoyé au navigateur : vide = inchangé."""
        config = ThirdPartyConfig.objects.create(
            name='API RH', base_url='https://api.example.com',
            auth_type='bearer', auth_token='secret-existant',
        )
        form = ThirdPartyConfigForm({
            'name': 'API RH', 'base_url': 'https://api.example.com',
            'auth_type': 'bearer', 'auth_token': '',
            'users_endpoint': '/u', 'attendance_endpoint': '/a',
            'sync_interval_minutes': '15', 'timeout_seconds': '30',
            'retry_attempts': '3', 'extra_headers': '',
        }, instance=config)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().auth_token, 'secret-existant')

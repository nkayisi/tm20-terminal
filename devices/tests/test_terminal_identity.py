"""
Tests de l'identité affichable d'un terminal.

Le protocole n'identifie un terminal que par son `sn`, illisible pour un
exploitant : l'application doit pouvoir le nommer sans jamais perdre le n° de
série, qui reste la seule identité reconnue par l'appareil.
"""

from django.test import TestCase

from devices.models import Terminal


class TerminalIdentityTests(TestCase):
    def test_fallback_on_serial_when_unnamed(self):
        t = Terminal.objects.create(sn='ZYTJ20128568', model='TM20')
        self.assertEqual(t.short_label, 'ZYTJ20128568')
        self.assertEqual(t.display_name, 'TM20 - ZYTJ20128568')
        self.assertEqual(str(t), 'TM20 - ZYTJ20128568')

    def test_named_terminal_keeps_serial_visible(self):
        t = Terminal.objects.create(
            sn='ZYTJ20128568', model='TM20', name='Entrée principale'
        )
        self.assertEqual(t.short_label, 'Entrée principale')
        self.assertEqual(t.display_name, 'Entrée principale (ZYTJ20128568)')

    def test_display_name_without_model(self):
        t = Terminal.objects.create(sn='SN12345')
        self.assertEqual(t.display_name, 'TM20 - SN12345')

    def test_ip_and_location_are_optional(self):
        t = Terminal.objects.create(sn='SN12345')
        self.assertIsNone(t.ip_address)
        self.assertEqual(t.location, '')

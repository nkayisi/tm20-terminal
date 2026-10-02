"""
Allers-retours entre l'heure murale du terminal et l'heure stockée.

Un terminal TM20 émet une heure murale nue, sans fuseau : `2026-01-05
08:05:00`. Avec `USE_TZ=True`, Postgres normalise en UTC, donc la valeur
stockée porte l'offset du site en moins. C'est correct — c'est le même instant
— mais tout ce qui ressort doit repasser par le fuseau du site, sinon
l'exploitant et l'application tierce lisent une heure qui n'a jamais été
affichée sur l'écran du terminal.

Ces tests épinglent ce contrat de bout en bout, parce que le symptôme (« tout
est décalé d'une heure ») est indiscernable d'un terminal mal réglé et coûte
cher à diagnostiquer une deuxième fois.
"""

from datetime import datetime

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from devices.models import AttendanceLog, Terminal, ThirdPartyConfig
from devices.protocol import (
    TM20Parser,
    make_terminal_aware,
    to_terminal_time,
)
from devices.services.attendance import AttendanceService
from devices.services.attendance_sync_service import AttendanceSyncService


def _kinshasa():
    """TM20_SETTINGS avec un fuseau terminal à UTC+1, offset fixe."""
    from django.conf import settings

    return {**settings.TM20_SETTINGS, 'TERMINAL_TIMEZONE': 'Africa/Kinshasa'}


class ToTerminalTimeTests(SimpleTestCase):
    def test_none_passes_through(self):
        self.assertIsNone(to_terminal_time(None))

    def test_utc_value_comes_back_at_site_wall_time(self):
        stored = datetime(2026, 1, 5, 7, 5, 0, tzinfo=timezone.utc)

        with override_settings(TM20_SETTINGS=_kinshasa()):
            local = to_terminal_time(stored)

        self.assertEqual(local.hour, 8)
        self.assertEqual(local.utcoffset().total_seconds(), 3600)
        self.assertEqual(local.isoformat(), '2026-01-05T08:05:00+01:00')

    def test_inverse_of_make_terminal_aware(self):
        """Ce que le terminal a envoyé est ce qui doit ressortir."""
        emitted = '2026-01-05 08:05:00'

        with override_settings(TM20_SETTINGS=_kinshasa()):
            stored = make_terminal_aware(TM20Parser.parse_datetime(emitted))
            # Le passage par UTC simule le stockage en base.
            returned = to_terminal_time(stored.astimezone(timezone.utc))

        self.assertEqual(returned.strftime('%Y-%m-%d %H:%M:%S'), emitted)


@override_settings(TIME_ZONE='Africa/Kinshasa')
class StoredPointageKeepsWallTimeTests(TestCase):
    """Du `sendlog` reçu jusqu'au corps envoyé au service tiers."""

    def setUp(self):
        self.terminal = Terminal.objects.create(sn='TESTSNTZ01', model='TM20')
        self.config = ThirdPartyConfig.objects.create(
            name='API RH',
            base_url='https://rh.example.com',
            attendance_endpoint='/api/v1/attendance',
            auth_type='none',
        )

    def _receive(self, emitted):
        message = TM20Parser.parse_sendlog({
            'cmd': 'sendlog',
            'sn': self.terminal.sn,
            'count': 1,
            'logindex': 0,
            'record': [{'enrollid': 7, 'time': emitted, 'mode': 1, 'inout': 0}],
        })
        async_to_sync(AttendanceService().process_logs)(self.terminal, message)
        return AttendanceLog.objects.get()

    def test_stored_instant_matches_the_wall_time_emitted(self):
        with override_settings(TM20_SETTINGS=_kinshasa()):
            log = self._receive('2026-01-05 08:05:00')

        # 08:05 à Kinshasa (UTC+1) == 07:05 UTC. L'heure en base est en retard
        # d'un offset, et c'est normal : c'est le même instant.
        self.assertEqual(log.time.astimezone(timezone.utc).hour, 7)
        self.assertEqual(timezone.localtime(log.time).hour, 8)

    def test_payload_carries_the_wall_time_with_its_offset(self):
        with override_settings(TM20_SETTINGS=_kinshasa()):
            log = self._receive('2026-01-05 08:05:00')
            service = AttendanceSyncService(self.config, self.terminal)
            data = service._log_to_attendance_data(log)

        self.assertEqual(data.timestamp, '2026-01-05T08:05:00+01:00')

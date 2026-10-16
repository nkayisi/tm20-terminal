"""Pointages sans matricule : ecartes, pas emis, pas perdus.

Le recepteur apparie sur `external_user_id` -- le matricule de l'agent dans le
systeme tiers. Sans lui il n'a rien a quoi rattacher la ligne : `enrollid` est
un compteur interne au terminal, il se recycle, et deux terminaux donnent le
meme a deux personnes differentes.

Emis quand meme, ces pointages recevaient un `200` sans que rien ne soit
enregistre, et passaient `sent` : synchronises d'un cote, inexistants de
l'autre. Ils sont desormais ecartes avant l'envoi et restent `pending`, de
sorte que renseigner l'`external_id` suffise a les faire partir a la passe
suivante -- sans reprise manuelle.

Le test qui compte vraiment ici est `test_a_fully_unmatchable_queue_terminates`
: la boucle d'envoi tourne jusqu'a ce que la file soit vide, et des lignes
laissees `pending` sont exactement ce qui la ferait tourner sans fin.
"""

from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.test import TestCase

from devices.integrations.base import AdapterResponse
from devices.integrations.http_adapter import HTTPAdapter
from devices.models import (
    AttendanceLog,
    BiometricUser,
    Terminal,
    ThirdPartyConfig,
)
from devices.protocol import TM20Parser
from devices.services.attendance import AttendanceService
from devices.services.attendance_sync_service import AttendanceSyncService


class UnmatchableAttendanceIsSkippedTests(TestCase):
    def setUp(self):
        self.terminal = Terminal.objects.create(sn='TESTSNUM01', model='TM20')
        self.config = ThirdPartyConfig.objects.create(
            name='API RH',
            base_url='https://rh.example.com',
            attendance_endpoint='/api/v1/attendance',
            auth_type='none',
        )

    # -- helpers ----------------------------------------------------------

    def _agent(self, enrollid, name, external_id=''):
        return BiometricUser.objects.create(
            terminal=self.terminal, enrollid=enrollid,
            name=name, external_id=external_id,
        )

    def _punch(self, enrollid, when):
        message = TM20Parser.parse_sendlog({
            'cmd': 'sendlog', 'sn': self.terminal.sn,
            'count': 1, 'logindex': 0,
            'record': [{'enrollid': enrollid, 'time': when,
                        'mode': 1, 'inout': 0}],
        })
        async_to_sync(AttendanceService().process_logs)(self.terminal, message)

    def _sync(self):
        """Lance une passe complete et retourne (resultat, corps envoyes)."""
        service = AttendanceSyncService(self.config, self.terminal)
        sent = AsyncMock(return_value=AdapterResponse.ok(message='ok'))

        with patch.object(HTTPAdapter, 'send_attendance', new=sent):
            result = async_to_sync(service.sync_pending_attendance)()

        emis = [
            [d.enrollid for d in call.args[0]]
            for call in sent.await_args_list
        ]
        return result, emis

    # -- tests ------------------------------------------------------------

    def test_an_agent_without_external_id_is_not_sent(self):
        self._agent(12, 'MUKENDI Grace')          # external_id == ''
        self._punch(12, '2026-09-29 08:00:00')

        result, emis = self._sync()

        self.assertEqual(emis, [], "aucun envoi ne devait partir")
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.sent, 0)

    def test_a_skipped_punch_stays_pending(self):
        """Ecarte n'est pas perdu : il attend son matricule."""
        self._agent(12, 'MUKENDI Grace')
        self._punch(12, '2026-09-29 08:00:00')

        self._sync()

        log = AttendanceLog.objects.get()
        self.assertEqual(log.sync_status, 'pending')
        self.assertEqual(log.sync_attempts, 0, "ce n'est pas un echec d'envoi")

    def test_filling_the_external_id_releases_it_on_the_next_run(self):
        """Le rattrapage se fait tout seul, sans reprise manuelle."""
        agent = self._agent(12, 'MUKENDI Grace')
        self._punch(12, '2026-09-29 08:00:00')
        self._sync()

        agent.external_id = 'EMP-00210'
        agent.save(update_fields=['external_id'])
        result, emis = self._sync()

        self.assertEqual(emis, [[12]])
        self.assertEqual(result.sent, 1)
        self.assertEqual(AttendanceLog.objects.get().sync_status, 'sent')

    def test_an_unknown_enrollid_is_skipped_too(self):
        """Aucun agent n'existe pour cet enrolement : rien a rattacher."""
        self._punch(31, '2026-09-29 08:00:00')

        result, emis = self._sync()

        self.assertEqual(emis, [])
        self.assertEqual(result.skipped, 1)

    def test_a_matchable_punch_in_the_same_batch_still_goes(self):
        """Un agent sans matricule ne doit pas retenir les autres."""
        self._agent(7, 'KAYISIRIRYA Nelson', external_id='EMP-00142')
        self._agent(12, 'MUKENDI Grace')
        self._punch(7, '2026-09-29 08:00:00')
        self._punch(12, '2026-09-29 08:01:00')

        result, emis = self._sync()

        self.assertEqual(emis, [[7]])
        self.assertEqual((result.sent, result.skipped), (1, 1))

    def test_door_events_are_never_held_back(self):
        """`enrollid == 0` : aucun agent en cause, aucun matricule a attendre.

        Les retenir les laisserait `pending` pour toujours, puisque rien ne
        viendra jamais les rattacher a quelqu'un.
        """
        self._punch(0, '2026-09-29 08:00:00')

        result, emis = self._sync()

        self.assertEqual(emis, [[0]])
        self.assertEqual((result.sent, result.skipped), (1, 0))

    def test_a_fully_unmatchable_queue_terminates(self):
        """La boucle d'envoi doit s'arreter, pas relire la meme file.

        `sync_pending_attendance` tourne jusqu'a ce qu'un lot revienne vide.
        Des pointages laisses `pending` reapparaitraient a chaque tour : sans
        la memoire des lignes ecartees, ce test ne finirait jamais.
        """
        self._agent(12, 'MUKENDI Grace')
        for minute in range(5):
            self._punch(12, f'2026-09-29 08:0{minute}:00')

        service = AttendanceSyncService(self.config, self.terminal)
        sent = AsyncMock(return_value=AdapterResponse.ok(message='ok'))

        with patch.object(HTTPAdapter, 'send_attendance', new=sent), \
                patch.object(AttendanceSyncService, 'DEFAULT_BATCH_SIZE', 2):
            result = async_to_sync(service.sync_pending_attendance)()

        self.assertEqual(result.skipped, 5)
        self.assertEqual(result.sent, 0)
        sent.assert_not_awaited()
        self.assertEqual(
            AttendanceLog.objects.filter(sync_status='pending').count(), 5
        )

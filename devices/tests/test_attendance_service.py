"""
Tests du traitement des pointages reçus par `sendlog`.

Couvre les garanties attendues du protocole (docs/websocket_json_protocol.md) :
déduplication des retransmissions, alternance entrée/sortie à l'intérieur d'un
même lot, et report de `logindex`.
"""

from asgiref.sync import async_to_sync
from django.test import TestCase

from devices.models import AttendanceLog, BiometricUser, Terminal
from devices.protocol import TM20Parser
from devices.services.attendance import AttendanceService


def sendlog(sn, records, logindex=0):
    return TM20Parser.parse_sendlog({
        'cmd': 'sendlog',
        'sn': sn,
        'count': len(records),
        'logindex': logindex,
        'record': records,
    })


class ProcessLogsTests(TestCase):
    def setUp(self):
        self.terminal = Terminal.objects.create(sn='TESTSN0001', model='TM20')
        self.service = AttendanceService()

    def process(self, records, logindex=0):
        return async_to_sync(self.service.process_logs)(
            self.terminal, sendlog(self.terminal.sn, records, logindex)
        )

    def test_batch_alternates_inout_for_same_user(self):
        """Trois pointages du même utilisateur dans un seul lot alternent.

        Régression : l'ancienne implémentation interrogeait la base avant le
        bulk_create, donc les trois lignes recevaient le même sens.
        """
        processed, _ = self.process([
            {'enrollid': 7, 'time': '2026-01-05 08:00:00', 'mode': 1, 'inout': 0},
            {'enrollid': 7, 'time': '2026-01-05 12:00:00', 'mode': 1, 'inout': 0},
            {'enrollid': 7, 'time': '2026-01-05 13:00:00', 'mode': 1, 'inout': 0},
        ])

        self.assertEqual(processed, 3)
        self.assertEqual(
            list(AttendanceLog.objects.order_by('time').values_list('inout', flat=True)),
            [0, 1, 0],
        )

    def test_alternation_continues_across_batches(self):
        self.process([{'enrollid': 7, 'time': '2026-01-05 08:00:00'}])
        self.process([{'enrollid': 7, 'time': '2026-01-05 17:00:00'}])

        self.assertEqual(
            list(AttendanceLog.objects.order_by('time').values_list('inout', flat=True)),
            [0, 1],
        )

    def test_retransmitted_batch_is_deduplicated(self):
        """Un terminal qui n'a pas reçu la réponse renvoie son lot."""
        records = [
            {'enrollid': 7, 'time': '2026-01-05 08:00:00'},
            {'enrollid': 8, 'time': '2026-01-05 08:01:00'},
        ]
        first, _ = self.process(records)
        second, _ = self.process(records)

        self.assertEqual(first, 2)
        self.assertEqual(second, 0, "le renvoi ne doit créer aucun doublon")
        self.assertEqual(AttendanceLog.objects.count(), 2)

    def test_logindex_is_persisted(self):
        self.process([{'enrollid': 7, 'time': '2026-01-05 08:00:00'}], logindex=42)
        self.assertEqual(AttendanceLog.objects.get().log_index, 42)

    def test_door_event_keeps_terminal_inout(self):
        """enrollid == 0 : événement de porte, `inout` figé par la spec (T2)."""
        self.process([
            {'enrollid': 0, 'time': '2026-01-05 08:00:00', 'inout': 1, 'event': 2},
        ])
        log = AttendanceLog.objects.get()
        self.assertEqual(log.inout, 1)
        self.assertEqual(log.event, 2)

    def test_user_is_linked_and_access_evaluated(self):
        user = BiometricUser.objects.create(
            terminal=self.terminal, enrollid=7, name='Nelly', is_enabled=False
        )
        _, access = self.process([{'enrollid': 7, 'time': '2026-01-05 08:00:00'}])

        log = AttendanceLog.objects.get()
        self.assertEqual(log.user_id, user.id)
        self.assertFalse(access, "un utilisateur désactivé ne doit pas ouvrir")
        self.assertFalse(log.access_granted)

    def test_unknown_user_is_allowed_by_default(self):
        _, access = self.process([{'enrollid': 999, 'time': '2026-01-05 08:00:00'}])
        self.assertTrue(access)
        self.assertIsNone(AttendanceLog.objects.get().user_id)

    def test_records_are_sorted_before_alternating(self):
        """Un lot désordonné doit être remis dans l'ordre chronologique."""
        self.process([
            {'enrollid': 7, 'time': '2026-01-05 17:00:00'},
            {'enrollid': 7, 'time': '2026-01-05 08:00:00'},
        ])
        self.assertEqual(
            list(AttendanceLog.objects.order_by('time').values_list('inout', flat=True)),
            [0, 1],
        )

    def test_forgotten_exit_does_not_shift_the_next_day(self):
        """Une sortie oubliee laisse la journee a un seul pointage.

        Le cas reel : quelqu'un badge en arrivant et repart sans badger. Sans
        borne de journee, son arrivee du lendemain devenait une SORTIE, et
        l'inversion se propageait a tout l'historique suivant -- rien dans la
        trame du terminal ne permettant de se resynchroniser.
        """
        self.process([{'enrollid': 7, 'time': '2026-01-05 08:00:00'}])
        # Pas de pointage de sortie le 5 : la journee reste a une seule ligne.
        self.process([{'enrollid': 7, 'time': '2026-01-06 08:00:00'}])

        self.assertEqual(
            list(AttendanceLog.objects.order_by('time').values_list('inout', flat=True)),
            [0, 0],
            "le premier pointage d'une journee est toujours une entree",
        )

    def test_each_day_restarts_at_entry(self):
        """Trois jours de suite, meme apres une journee complete."""
        self.process([
            {'enrollid': 7, 'time': '2026-01-05 08:00:00'},
            {'enrollid': 7, 'time': '2026-01-05 17:00:00'},
            {'enrollid': 7, 'time': '2026-01-06 08:00:00'},
            {'enrollid': 7, 'time': '2026-01-07 08:00:00'},
            {'enrollid': 7, 'time': '2026-01-07 17:00:00'},
        ])

        self.assertEqual(
            list(AttendanceLog.objects.order_by('time').values_list('inout', flat=True)),
            [0, 1, 0, 0, 1],
        )

    def test_batch_spanning_midnight_restarts_the_day_it_crosses(self):
        """Un lot peut enjamber minuit : la remise a zero doit suivre.

        Un terminal prive de reseau accumule, puis deverse plusieurs jours
        dans un seul `sendlog`.
        """
        self.process([
            {'enrollid': 7, 'time': '2026-01-05 08:00:00'},
            {'enrollid': 7, 'time': '2026-01-05 12:00:00'},
            {'enrollid': 7, 'time': '2026-01-05 13:00:00'},
            {'enrollid': 7, 'time': '2026-01-06 08:00:00'},
        ])

        self.assertEqual(
            list(AttendanceLog.objects.order_by('time').values_list('inout', flat=True)),
            [0, 1, 0, 0],
        )

    def test_day_boundary_follows_the_site_not_utc(self):
        """La journee est celle du site : minuit local, pas minuit UTC.

        A Kinshasa (UTC+1), un pointage a 23h30 et un a 00h30 sont deux
        journees. En UTC ils tomberaient tous deux le meme jour (22h30 et
        23h30) et le second serait pris pour une sortie.
        """
        self.process([{'enrollid': 7, 'time': '2026-01-05 23:30:00'}])
        self.process([{'enrollid': 7, 'time': '2026-01-06 00:30:00'}])

        self.assertEqual(
            list(AttendanceLog.objects.order_by('time').values_list('inout', flat=True)),
            [0, 0],
        )

    def test_two_users_keep_independent_daily_sequences(self):
        self.process([
            {'enrollid': 7, 'time': '2026-01-05 08:00:00'},
            {'enrollid': 8, 'time': '2026-01-05 08:01:00'},
            {'enrollid': 7, 'time': '2026-01-05 17:00:00'},
            {'enrollid': 8, 'time': '2026-01-06 08:00:00'},
        ])

        self.assertEqual(
            [log.inout for log in AttendanceLog.objects.filter(enrollid=7).order_by('time')],
            [0, 1],
        )
        self.assertEqual(
            [log.inout for log in AttendanceLog.objects.filter(enrollid=8).order_by('time')],
            [0, 0],
            "le 8 n'a pas badge sa sortie le 5 : le 6 reste une entree",
        )

    def test_backfilled_batch_is_anchored_before_its_own_records(self):
        """Un lot antidaté ne doit pas s'amorcer sur un pointage postérieur.

        Régression : `_get_last_inout` interrogeait la base sans `before_time`,
        donc le rattrapage d'historique (`getalllog`/`getnewlog` via
        `ResponseHandler._persist_log_page`) prenait pour amorce le pointage le
        plus RÉCENT de l'utilisateur, postérieur au lot traité, et inversait
        toute l'alternance.
        """
        # Pointage déjà connu, postérieur au lot rejoué ci-dessous.
        self.process([{'enrollid': 7, 'time': '2026-01-10 17:00:00'}])
        self.assertEqual(AttendanceLog.objects.get().inout, 0)

        # Rattrapage de deux pointages plus anciens.
        self.process([
            {'enrollid': 7, 'time': '2026-01-05 08:00:00'},
            {'enrollid': 7, 'time': '2026-01-05 12:00:00'},
        ])

        self.assertEqual(
            list(AttendanceLog.objects.order_by('time').values_list('inout', flat=True)),
            [0, 1, 0],
            "les deux lignes antidatées doivent alterner depuis rien, "
            "pas depuis le pointage du 10 janvier",
        )


class SendLogReplyTests(TestCase):
    """La réponse `sendlog` renvoyée au terminal (doc section T2)."""

    def setUp(self):
        self.terminal = Terminal.objects.create(sn='TESTSN0002', model='TM20')

    def reply(self, records):
        from devices.handlers.attendance import AttendanceHandler

        result = async_to_sync(AttendanceHandler().handle)(
            {'cmd': 'sendlog', 'sn': self.terminal.sn,
             'count': len(records), 'logindex': 5, 'record': records},
            terminal=self.terminal,
            sn=self.terminal.sn,
        )
        return result.response

    def test_count_echoes_received_records(self):
        records = [
            {'enrollid': 7, 'time': '2026-01-05 08:00:00'},
            {'enrollid': 8, 'time': '2026-01-05 08:01:00'},
        ]
        response = self.reply(records)

        self.assertTrue(response['result'])
        self.assertEqual(response['count'], 2)
        self.assertEqual(response['logindex'], 5)

    def test_count_echoes_even_when_every_record_is_a_duplicate(self):
        """Régression : `count: 0` sur un renvoi invitait à retransmettre sans fin.

        `count` est un écho du nombre reçu, pas un compteur d'insertions. Un
        firmware qui avance son pointeur de lecture sur cette valeur restait
        bloqué sur le même lot dès que la déduplication l'écartait entièrement.
        """
        records = [{'enrollid': 7, 'time': '2026-01-05 08:00:00'}]

        self.reply(records)
        response = self.reply(records)  # retransmission intégrale

        self.assertEqual(AttendanceLog.objects.count(), 1, "aucun doublon en base")
        self.assertTrue(response['result'])
        self.assertEqual(response['count'], 1, "le terminal doit lire son propre count")

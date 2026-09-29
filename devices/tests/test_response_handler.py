"""
Tests de la pagination des réponses terminal (`getuserlist`, `getalllog`,
`getnewlog`).

La spec ne définit pas la condition d'arrêt (doc section 6.2-8) : le serveur
relance `{"cmd": X, "stn": false}` jusqu'à épuisement. Deux garanties comptent
ici — ne jamais boucler sans pouvoir enregistrer, et ne jamais perdre le
garde-fou de nombre de pages.
"""

from asgiref.sync import async_to_sync
from django.test import TestCase

from devices.handlers.response import ResponseHandler
from devices.models import AttendanceLog, Terminal


def page(records, count=None, page_to=0):
    return {
        'ret': 'getalllog',
        'result': True,
        'count': count if count is not None else len(records),
        'from': 0,
        'to': page_to,
        'record': records,
    }


def logs(n, start=0):
    return [
        {'enrollid': 7, 'time': f'2026-01-05 {8 + start + i:02d}:00:00',
         'mode': 1, 'inout': 0, 'event': 0}
        for i in range(n)
    ]


_UNSET = object()


class PaginationTests(TestCase):
    def setUp(self):
        self.terminal = Terminal.objects.create(sn='TESTSN0005', model='TM20')
        self.handler = ResponseHandler()
        self.state = {}

    def handle(self, message, terminal=_UNSET):
        return async_to_sync(self.handler.handle)(
            message,
            terminal=self.terminal if terminal is _UNSET else terminal,
            sn=self.terminal.sn,
            pagination_state=self.state,
        ).response

    def test_full_page_asks_for_the_next_one(self):
        response = self.handle(page(logs(3)))

        self.assertEqual(response, {'cmd': 'getalllog', 'stn': False})
        self.assertEqual(AttendanceLog.objects.count(), 3)

    def test_shorter_page_ends_the_pagination(self):
        self.handle(page(logs(3)))
        response = self.handle(page(logs(1, start=10)))

        self.assertIsNone(response)
        self.assertEqual(self.state, {}, "l'état doit être purgé en fin de course")

    def test_missing_terminal_stops_instead_of_draining_the_device(self):
        """Régression : la boucle continuait sans rien persister.

        Le garde `if records and terminal:` sautait l'enregistrement mais
        renvoyait quand même la page suivante : le terminal déversait tout son
        historique dans le vide, avec un « pagination terminée (N
        enregistrements) » mensonger à la fin.
        """
        response = self.handle(page(logs(3)), terminal=None)

        self.assertIsNone(response, "sans terminal, la pagination doit s'arrêter")
        self.assertEqual(AttendanceLog.objects.count(), 0)
        self.assertEqual(self.state, {})

    def test_page_guard_is_not_reset_by_a_lost_shared_cache(self):
        """L'état vit sur la connexion, plus dans le cache Redis partagé.

        Un firmware qui renvoie indéfiniment la même page doit se heurter à
        MAX_PAGES ; l'état ne doit donc dépendre d'aucune expiration externe.
        """
        self.handler.MAX_PAGES = 3
        try:
            # Pages pleines et identiques en taille : aucun signal d'arrêt
            # naturel, seul le garde-fou peut interrompre.
            responses = [
                self.handle(page(logs(2, start=i * 2))) for i in range(4)
            ]
        finally:
            del self.handler.MAX_PAGES

        self.assertEqual(responses[:2], [{'cmd': 'getalllog', 'stn': False}] * 2)
        self.assertIsNone(responses[2], "le garde-fou doit couper à MAX_PAGES")

    def test_failed_page_interrupts_and_clears_state(self):
        self.handle(page(logs(2)))
        response = self.handle(
            {'ret': 'getalllog', 'result': False, 'reason': 1, 'record': []}
        )

        self.assertIsNone(response)
        self.assertEqual(self.state, {})

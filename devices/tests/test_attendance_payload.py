"""
Forme du corps envoyé aux services tiers pour les pointages.

Le contrat est volontairement uniforme : toujours un objet portant la clé
`attendances`, dont la valeur est un tableau — y compris quand il ne contient
qu'un seul pointage. C'est le cas le plus fréquent en exploitation (la
synchronisation tourne chaque minute, il est rare que deux personnes badgent
dans le même intervalle), donc celui qu'une forme variable ferait diverger du
cas groupé sans qu'on le remarque.
"""

import asyncio
from unittest.mock import AsyncMock, patch

from django.test import TestCase

from devices.integrations.base import AttendanceData
from devices.integrations.http_adapter import HTTPAdapter
from devices.models import ThirdPartyConfig


def _record(log_id: int) -> AttendanceData:
    return AttendanceData(
        log_id=log_id,
        terminal_sn='ZYTJ20128568',
        enrollid=7,
        external_user_id=None,
        user_name=f'User#{log_id}',
        timestamp='2026-09-29T09:00:00+00:00',
        mode=0,
        inout=0,
    )


class AttendancePayloadShapeTests(TestCase):
    def setUp(self):
        self.config = ThirdPartyConfig.objects.create(
            name='API RH',
            base_url='https://rh.example.com',
            attendance_endpoint='/api/v1/attendance',
            auth_type='none',
        )

    def _send(self, count):
        """Envoie `count` pointages et retourne le corps réellement transmis."""
        adapter = HTTPAdapter(self.config)
        response = AsyncMock()
        response.status_code = 200
        response.text = ''
        response.json.return_value = {}

        with patch.object(HTTPAdapter, '_request', new=AsyncMock(return_value=response)) as req:
            asyncio.run(adapter.send_attendance([_record(1000 + i) for i in range(count)]))

        return req.await_args.kwargs['json']

    def test_single_record_is_still_wrapped_in_a_list(self):
        """Le cas courant : un pointage seul, mais dans un tableau."""
        payload = self._send(1)

        self.assertEqual(list(payload), ['attendances'])
        self.assertIsInstance(payload['attendances'], list)
        self.assertEqual(len(payload['attendances']), 1)
        self.assertEqual(payload['attendances'][0]['log_id'], 1000)

    def test_several_records_share_the_same_shape(self):
        payload = self._send(3)

        self.assertEqual(list(payload), ['attendances'])
        self.assertEqual(
            [r['log_id'] for r in payload['attendances']], [1000, 1001, 1002]
        )

    def test_shape_does_not_depend_on_batch_size(self):
        """Le point de tout l'exercice : aucune bascule selon la taille du lot."""
        shapes = {tuple(self._send(n)) for n in (1, 2, 5)}
        self.assertEqual(shapes, {('attendances',)})

    def test_records_keep_the_same_fields_whatever_the_count(self):
        alone = self._send(1)['attendances'][0]
        among_others = self._send(3)['attendances'][0]

        self.assertEqual(set(alone), set(among_others))
        self.assertEqual(alone, among_others)

    def test_empty_list_sends_nothing(self):
        """Aucune requête pour un lot vide : le court-circuit est en amont."""
        adapter = HTTPAdapter(self.config)
        with patch.object(HTTPAdapter, '_request', new=AsyncMock()) as req:
            result = asyncio.run(adapter.send_attendance([]))

        req.assert_not_awaited()
        self.assertTrue(result.success)

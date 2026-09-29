"""
Forme du corps envoyé aux services tiers pour les pointages.

Le contrat attendu par les destinataires n'est pas uniforme : un pointage seul
part sans enveloppe, deux ou plus partent dans un objet sous la clé
`attendances`. La structure dépend donc de la taille du lot, et bascule d'une
synchronisation à l'autre selon ce qui s'est accumulé. Ces tests verrouillent
les deux formes et la frontière exacte entre elles.
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

    def test_single_record_is_sent_bare(self):
        payload = self._send(1)

        self.assertIsInstance(payload, dict)
        self.assertNotIn('attendances', payload)
        self.assertEqual(payload['log_id'], 1000)
        self.assertEqual(payload['terminal_sn'], 'ZYTJ20128568')

    def test_several_records_are_wrapped(self):
        payload = self._send(3)

        self.assertIsInstance(payload, dict)
        self.assertEqual(list(payload), ['attendances'])
        self.assertEqual(len(payload['attendances']), 3)
        self.assertEqual(
            [r['log_id'] for r in payload['attendances']], [1000, 1001, 1002]
        )

    def test_two_is_already_the_wrapped_form(self):
        """La bascule se fait à deux, pas à trois : c'est la frontière utile."""
        self.assertIn('attendances', self._send(2))

    def test_records_keep_the_same_fields_in_both_shapes(self):
        """Seule l'enveloppe change ; un pointage garde la même structure."""
        alone = self._send(1)
        wrapped = self._send(2)['attendances'][0]

        self.assertEqual(set(alone), set(wrapped))

    def test_empty_list_sends_nothing(self):
        adapter = HTTPAdapter(self.config)
        with patch.object(HTTPAdapter, '_request', new=AsyncMock()) as req:
            result = asyncio.run(adapter.send_attendance([]))

        req.assert_not_awaited()
        self.assertTrue(result.success)

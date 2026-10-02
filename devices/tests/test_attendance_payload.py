"""
Forme du corps envoyé aux services tiers pour les pointages.

Le contrat est contraint par les récepteurs en service, et il est variable :

    1 pointage    ->  l'objet nu, sans enveloppe
    2 et plus     ->  {"attendances": [ ... ]}

Cette forme n'est pas un choix du dépôt — elle a déjà été uniformisée puis
restaurée (32f3f24 -> f6fc303 -> ea6844f -> aujourd'hui). D'où ces tests : ils
existent pour qu'une « simplification » bien intentionnée casse ici plutôt
qu'en production, chez un récepteur qui ne sait lire qu'une des deux formes.

Ce que les tests surveillent en priorité, c'est la **branche groupée**. En
exploitation la synchronisation tourne chaque minute : il est rare que deux
personnes badgent dans le même intervalle, donc le lot d'un seul élément est le
cas normal et le lot groupé le cas qu'on ne voit presque jamais passer. C'est
celui qui se casserait sans qu'on le remarque.

Le contenu d'un enregistrement, lui, ne doit pas dépendre de la branche :
`timestamp` porte l'heure murale du terminal avec son offset dans les deux cas
(voir `test_terminal_time.py` pour l'origine de cette heure).
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
        timestamp='2026-09-29T09:00:00+01:00',
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
        """Le cas courant : un pointage seul, sans enveloppe ni tableau."""
        payload = self._send(1)

        self.assertIsInstance(payload, dict)
        self.assertNotIn('attendances', payload)
        self.assertEqual(payload['log_id'], 1000)
        self.assertEqual(payload['enrollid'], 7)

    def test_several_records_are_wrapped(self):
        """Le cas rare, donc celui que ces tests protegent vraiment."""
        payload = self._send(3)

        self.assertIsInstance(payload, dict)
        self.assertIsInstance(payload['attendances'], list)
        self.assertEqual(
            [r['log_id'] for r in payload['attendances']], [1000, 1001, 1002]
        )

    def test_two_records_already_use_the_wrapped_form(self):
        """La bascule est a deux, pas a trois : c'est la frontiere exacte."""
        payload = self._send(2)

        self.assertIn('attendances', payload)
        self.assertEqual(len(payload['attendances']), 2)

    def test_records_keep_the_same_fields_in_both_forms(self):
        """La branche ne doit changer que l'emballage, jamais le contenu."""
        alone = self._send(1)
        among_others = self._send(3)['attendances'][0]

        self.assertEqual(set(alone), set(among_others))
        self.assertEqual(alone, among_others)

    def test_timestamp_is_sent_untouched_in_both_forms(self):
        """L'heure murale du terminal traverse l'adapter sans retouche."""
        expected = '2026-09-29T09:00:00+01:00'

        self.assertEqual(self._send(1)['timestamp'], expected)
        self.assertEqual(self._send(3)['attendances'][0]['timestamp'], expected)

    def test_empty_list_sends_nothing(self):
        """Aucune requête pour un lot vide : le court-circuit est en amont."""
        adapter = HTTPAdapter(self.config)
        with patch.object(HTTPAdapter, '_request', new=AsyncMock()) as req:
            result = asyncio.run(adapter.send_attendance([]))

        req.assert_not_awaited()
        self.assertTrue(result.success)

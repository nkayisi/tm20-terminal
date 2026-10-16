"""
Forme du corps envoyé aux services tiers pour les pointages.

Le contrat est dicté par le récepteur en service (`data_recev.php`), qui
n'aiguille que sur deux formes :

    if (is_object($datareceive))      -> UN pointage, l'objet nu
    else if (is_array($datareceive))  -> un tableau RACINE, qu'il parcourt

D'où les deux formes envoyées, une par branche :

    1 pointage    ->  { ... }
    2 et plus     ->  [ { ... }, { ... } ]

Ce que ces tests interdisent avant tout, c'est l'enveloppe
`{"attendances": [...]}` : `json_decode` en fait un objet, le récepteur part
donc dans sa branche « un seul pointage », y cherche `timestamp` et
`external_user_id` qui n'y sont pas, ne trouve aucun matricule et n'insère
rien — en répondant 200. Le lot entier disparaît sans trace. Le dépôt a déjà
fait l'aller-retour sur cette forme (32f3f24 -> f6fc303 -> ea6844f -> ici),
d'où des tests qui nomment la contrainte plutôt que de la supposer connue.

L'attention porte surtout sur le lot groupé : la synchronisation tourne chaque
minute, il est rare que deux personnes badgent dans le même intervalle, donc le
lot d'un seul élément est le cas normal et le lot groupé celui qu'on ne voit
presque jamais passer en exploitation.

Le contenu d'un enregistrement ne dépend pas de la branche : `timestamp` porte
l'heure murale du terminal avec son offset dans les deux cas — le récepteur lit
ces chiffres littéralement, sans conversion (voir `test_terminal_time.py`).
"""

import asyncio
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.test import TestCase

from devices.integrations.base import AttendanceData
from devices.integrations.http_adapter import HTTPAdapter
from devices.models import AttendanceLog, Terminal, ThirdPartyConfig
from devices.protocol import TM20Parser
from devices.services.attendance import AttendanceService
from devices.services.attendance_sync_service import AttendanceSyncService


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

    def test_several_records_are_sent_as_a_root_array(self):
        """Le cas rare, donc celui que ces tests protegent vraiment."""
        payload = self._send(3)

        self.assertIsInstance(payload, list)
        self.assertEqual([r['log_id'] for r in payload], [1000, 1001, 1002])

    def test_two_records_already_use_the_array_form(self):
        """La bascule est a deux, pas a trois : c'est la frontiere exacte."""
        payload = self._send(2)

        self.assertIsInstance(payload, list)
        self.assertEqual(len(payload), 2)

    def test_no_wrapping_key_is_ever_sent(self):
        """Regression : {"attendances": [...]} fait disparaitre le lot.

        Le recepteur en fait un objet, cherche `timestamp` dessus, ne trouve
        rien et repond 200 sans avoir rien enregistre. Aucune forme envoyee ne
        doit donc porter de cle d'enveloppe.
        """
        for n in (1, 2, 5, 17):
            payload = self._send(n)
            keys = payload if isinstance(payload, dict) else {}
            for interdit in ('attendances', 'attendance', 'records', 'data'):
                self.assertNotIn(
                    interdit, keys,
                    f"enveloppe '{interdit}' reapparue pour un lot de {n}",
                )

    def test_records_keep_the_same_fields_in_both_forms(self):
        """La branche ne doit changer que l'emballage, jamais le contenu."""
        alone = self._send(1)
        among_others = self._send(3)[0]

        self.assertEqual(set(alone), set(among_others))
        self.assertEqual(alone, among_others)

    def test_timestamp_is_sent_untouched_in_both_forms(self):
        """L'heure murale du terminal traverse l'adapter sans retouche.

        Le recepteur fait `new DateTime($data->timestamp)->format('H:i:s')` :
        il lit les chiffres tels quels, sans convertir vers son propre fuseau.
        L'offset doit donc etre celui du site.
        """
        expected = '2026-09-29T09:00:00+01:00'

        self.assertEqual(self._send(1)['timestamp'], expected)
        self.assertEqual(self._send(3)[0]['timestamp'], expected)

    def test_empty_list_sends_nothing(self):
        """Aucune requête pour un lot vide : le court-circuit est en amont."""
        adapter = HTTPAdapter(self.config)
        with patch.object(HTTPAdapter, '_request', new=AsyncMock()) as req:
            result = asyncio.run(adapter.send_attendance([]))

        req.assert_not_awaited()
        self.assertTrue(result.success)


class InOutIsConsistentAtEveryLevelTests(TestCase):
    """`inout` doit porter la meme valeur a la racine et dans `metadata`.

    Le terminal emet toujours `inout: 0` -- la spec reserve ce champ au couple
    lecteur maitre / lecteur esclave (section 6.1-1) -- et c'est le serveur qui
    tient le sens de passage, par alternance bornee a la journee civile. La
    racine portait donc la valeur derivee pendant que `metadata`, recopie de
    `raw_payload`, gardait le 0 du terminal : le meme pointage se lisait
    « entree » ou « sortie » selon le niveau ouvert, et une sortie descendue
    dans `metadata` se comptait comme une entree sans rien pour le signaler.

    L'alignement se fait a l'envoi, pas a l'insertion : `raw_payload` reste la
    trame telle que le terminal l'a emise, et les pointages deja en base --
    dont le 0 est fige -- partent eux aussi avec la bonne valeur.
    """

    def setUp(self):
        self.terminal = Terminal.objects.create(sn='TESTSNIO01', model='TM20')
        self.config = ThirdPartyConfig.objects.create(
            name='API RH inout',
            base_url='https://rh.example.com',
            attendance_endpoint='/api/v1/attendance',
            auth_type='none',
        )

    def _receive(self, *times):
        """Rejoue un sendlog pour un meme agent, dans l'ordre donne."""
        for emitted in times:
            message = TM20Parser.parse_sendlog({
                'cmd': 'sendlog',
                'sn': self.terminal.sn,
                'count': 1,
                'logindex': 0,
                'record': [{
                    'enrollid': 7, 'time': emitted, 'mode': 1, 'inout': 0,
                }],
            })
            async_to_sync(AttendanceService().process_logs)(self.terminal, message)

        return list(AttendanceLog.objects.order_by('time'))

    def _payloads(self, logs):
        service = AttendanceSyncService(self.config, self.terminal)
        return [service._log_to_attendance_data(log).to_dict() for log in logs]

    def test_entry_and_exit_agree_at_both_levels(self):
        logs = self._receive('2026-09-29 08:00:00', '2026-09-29 17:00:00')
        entree, sortie = self._payloads(logs)

        self.assertEqual(entree['inout'], 0)
        self.assertEqual(entree['metadata']['inout'], 0)

        # Le cas qui divergeait : la sortie derivee contre le 0 du terminal.
        self.assertEqual(sortie['inout'], 1)
        self.assertEqual(sortie['metadata']['inout'], 1)

    def test_no_record_ever_contradicts_itself(self):
        """Quatre passages : l'alternance ne doit jamais desynchroniser."""
        logs = self._receive(
            '2026-09-29 08:00:00', '2026-09-29 12:00:00',
            '2026-09-29 13:00:00', '2026-09-29 17:00:00',
        )
        payloads = self._payloads(logs)

        self.assertEqual([p['inout'] for p in payloads], [0, 1, 0, 1])
        for p in payloads:
            self.assertEqual(
                p['inout'], p['metadata']['inout'],
                f"log_id={p['log_id']} se contredit entre ses deux niveaux",
            )

    def test_the_stored_frame_keeps_the_terminal_value(self):
        """L'alignement est un fait d'envoi, pas une reecriture de l'historique.

        `raw_payload` reste la trame emise par le terminal : c'est elle qui
        permet de rejouer ou d'auditer un lot. La valeur derivee vit dans la
        colonne `inout`, et n'est recopiee dans `metadata` qu'au moment de
        construire le corps.
        """
        logs = self._receive('2026-09-29 08:00:00', '2026-09-29 17:00:00')
        sortie = logs[1]

        self.assertEqual(sortie.inout, 1)
        self.assertEqual(sortie.raw_payload['inout'], 0)
        self.assertEqual(self._payloads([sortie])[0]['metadata']['inout'], 1)

    def test_the_rest_of_the_frame_is_untouched(self):
        """Seul `inout` est aligne ; le reste de la trame traverse intact."""
        logs = self._receive('2026-09-29 17:00:00')
        metadata = self._payloads(logs)[0]['metadata']

        # `time` reste l'horodatage nu du terminal : c'est `timestamp` a la
        # racine qui porte l'heure murale avec son offset.
        self.assertEqual(metadata['time'], '2026-09-29 17:00:00')
        self.assertEqual(metadata['enrollid'], 7)
        self.assertEqual(metadata['mode'], 1)
        self.assertEqual(
            set(metadata), set(logs[0].raw_payload),
            "l'alignement ne doit ni ajouter ni retirer de cle",
        )

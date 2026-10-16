"""La page publique du contrat doit montrer ce que le code envoie vraiment.

`docs/payload_pointages_services_tiers.md` et la page `/docs/pointages/`
portent les memes deux exemples de corps. Recopies a la main, ils vieillissent
en silence : le jour ou un champ change, la documentation decrit un format que
plus personne n'emet, et c'est l'equipe du recepteur qui paie la difference.

Ces tests rejouent le scenario exact des exemples a travers la chaine
d'emission et comparent le resultat a ce qui est publie. Modifier le payload
sans reprendre la documentation fait echouer la suite -- c'est tout l'objet du
fichier.

`log_id` est neutralise avant comparaison : il vient d'une sequence de base,
dont l'etat n'a rien a dire sur le format.
"""

import html
import json
import pathlib
import re

from asgiref.sync import async_to_sync
from django.test import TestCase, override_settings
from django.urls import reverse

from devices.models import BiometricUser, Terminal, ThirdPartyConfig
from devices.protocol import TM20Parser
from devices.services.attendance import AttendanceService
from devices.services.attendance_sync_service import AttendanceSyncService

MD_PATH = (
    pathlib.Path(__file__).resolve().parent.parent.parent
    / 'docs' / 'payload_pointages_services_tiers.md'
)

TAGS = re.compile(r'<[^>]+>')


def _strip(fragment: str) -> object:
    """Rend l'objet JSON porte par un fragment HTML colore."""
    return json.loads(html.unescape(TAGS.sub('', fragment)))


def _blank_ids(payload):
    """Neutralise `log_id`, qui depend de la sequence et non du format."""
    records = payload if isinstance(payload, list) else [payload]
    for record in records:
        record['log_id'] = 0
    return payload


def _kinshasa():
    return {'TERMINAL_TIMEZONE': 'Africa/Kinshasa'}


@override_settings(TIME_ZONE='Africa/Kinshasa')
class PublishedExamplesMatchTheCodeTests(TestCase):
    """Le scenario des deux exemples, rejoue de bout en bout."""

    def setUp(self):
        self.terminal = Terminal.objects.create(sn='ZYTJ20128568', model='TM20')
        self.config = ThirdPartyConfig.objects.create(
            name='API RH',
            base_url='https://rh.example.com',
            attendance_endpoint='/api/v1/attendance',
            auth_type='bearer',
        )

    def _emitted(self):
        """Les quatre pointages des exemples, tels que l'adapter les enverrait."""
        with override_settings(TM20_SETTINGS=_kinshasa()):
            BiometricUser.objects.create(
                terminal=self.terminal, enrollid=7,
                external_id='EMP-00142', name='KAYISIRIRYA Nelson')
            BiometricUser.objects.create(
                terminal=self.terminal, enrollid=12,
                external_id='EMP-00210', name='MUKENDI Grace')

            punches = [
                (7, '2026-10-16 07:02:11', 8, 1, None),
                (7, '2026-10-16 12:31:04', 8, 1, 36.4),
                (12, '2026-10-16 12:31:52', 3, 3, None),
                (0, '2026-10-16 14:05:09', 0, 0, None),
            ]
            for enrollid, when, mode, verifymode, temp in punches:
                record = {'enrollid': enrollid, 'time': when, 'mode': mode,
                          'inout': 0, 'event': 0, 'verifymode': verifymode}
                if temp is not None:
                    record['temp'] = temp
                message = TM20Parser.parse_sendlog({
                    'cmd': 'sendlog', 'sn': self.terminal.sn,
                    'count': 1, 'logindex': 0, 'record': [record],
                })
                async_to_sync(AttendanceService().process_logs)(
                    self.terminal, message)

            from devices.models import AttendanceLog
            logs = list(
                AttendanceLog.objects
                .select_related('terminal', 'user').order_by('time')
            )
            service = AttendanceSyncService(self.config)
            logs = [log for log in logs if service._is_matchable(log)]
            return [service._log_to_attendance_data(log).to_dict() for log in logs]

    def _published(self, source):
        """Les deux exemples tels que publies, par support."""
        if source == 'page':
            page = self.client.get(reverse('docs:attendance_payload')).content.decode()
            found = re.findall(
                r'<code data-example="(single|batch)">(.*?)</code>', page, re.S)
            blocks = {name: _strip(body) for name, body in found}
            return blocks['single'], blocks['batch']

        blocks = re.findall(r'```json\n(.*?)```', MD_PATH.read_text(), re.S)
        self.assertEqual(len(blocks), 2, "le .md doit porter deux exemples")
        return json.loads(blocks[0]), json.loads(blocks[1])

    def test_the_page_shows_the_single_punch_the_code_builds(self):
        expected = _blank_ids(self._emitted()[0])
        single, _ = self._published('page')

        self.assertEqual(_blank_ids(single), expected)

    def test_the_page_shows_the_batch_the_code_builds(self):
        expected = _blank_ids(self._emitted()[1:])
        _, batch = self._published('page')

        self.assertEqual(_blank_ids(batch), expected)

    def test_the_markdown_carries_the_same_two_examples(self):
        """Les deux supports ne doivent pas deriver l'un de l'autre."""
        page_single, page_batch = self._published('page')
        md_single, md_batch = self._published('md')

        self.assertEqual(_blank_ids(md_single), _blank_ids(page_single))
        self.assertEqual(_blank_ids(md_batch), _blank_ids(page_batch))

    def test_the_batch_is_a_root_array_and_the_single_is_not(self):
        """La forme publiee doit etre celle que le recepteur aiguille."""
        single, batch = self._published('page')

        self.assertIsInstance(single, dict)
        self.assertIsInstance(batch, list)

    def test_no_published_example_carries_an_envelope_key(self):
        single, _ = self._published('page')

        for interdit in ('attendances', 'attendance', 'records', 'data'):
            self.assertNotIn(interdit, single)


class DocPageIsPublicTests(TestCase):
    """Le lecteur vise n'a pas de compte : la page ne doit pas l'y renvoyer."""

    def test_an_anonymous_visitor_gets_the_page(self):
        response = self.client.get(reverse('docs:attendance_payload'))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Location', response.headers)

    def test_the_page_does_not_need_the_database(self):
        """Elle ne decrit qu'un format : aucune donnee d'exploitation dessus."""
        with self.assertNumQueries(0):
            self.client.get(reverse('docs:attendance_payload'))

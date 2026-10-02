"""
Contrat de l'API que consomme le dashboard temps réel.

Le gabarit `dashboard/index.html` est du code Alpine : il lit ce JSON et tranche
dessus sans aucune couche de conversion. Un champ dont le *type* change ne casse
donc rien de visible côté serveur — la page se contente d'afficher faux.

Régression à l'origine de ce fichier : `inout` était envoyé sous forme de
libellé (« Entrée » / « Sortie ») alors que le gabarit teste `log.inout === 0`.
La comparaison stricte d'une chaîne à un nombre est toujours fausse, donc
*tous* les pointages s'affichaient en « Sortie », y compris ceux que l'admin
Django montrait en « Entrée ».
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from devices.models import AttendanceLog, BiometricUser, Terminal


class LogsAPIContractTests(TestCase):
    def setUp(self):
        self.terminal = Terminal.objects.create(sn='TESTSNAPI1', model='TM20')
        self.user = BiometricUser.objects.create(
            terminal=self.terminal, enrollid=7, name='NKETANI TRIDA'
        )
        self.client = Client()
        self.client.force_login(
            get_user_model().objects.create_user(
                username='operateur', password='motdepasse'
            )
        )

    def _log(self, inout):
        return AttendanceLog.objects.create(
            terminal=self.terminal, user=self.user, enrollid=7,
            time=timezone.now(), mode=1, inout=inout,
        )

    def _logs(self):
        response = self.client.get(reverse('dashboard:logs'))
        self.assertEqual(response.status_code, 200)
        return response.json()['logs']

    def test_inout_is_the_protocol_value_not_its_label(self):
        """Le gabarit compare avec `=== 0` : il lui faut un entier."""
        self._log(inout=0)

        (log,) = self._logs()
        self.assertIsInstance(log['inout'], int)
        self.assertEqual(log['inout'], 0)

    def test_entry_and_exit_are_distinguishable(self):
        """Regression : les deux sens ressortaient identiques cote client."""
        self._log(inout=0)
        self._log(inout=1)

        valeurs = sorted(log['inout'] for log in self._logs())
        self.assertEqual(valeurs, [0, 1])

    def test_label_is_still_available_under_its_own_name(self):
        self._log(inout=0)

        (log,) = self._logs()
        self.assertEqual(log['inout_display'], 'Entrée')
        self.assertEqual(log['inout_class'], 'success')

    def test_exit_label_and_class(self):
        self._log(inout=1)

        (log,) = self._logs()
        self.assertEqual(log['inout_display'], 'Sortie')
        self.assertEqual(log['inout_class'], 'info')

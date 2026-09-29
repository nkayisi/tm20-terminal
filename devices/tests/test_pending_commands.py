"""
Tests de la corrélation des commandes en attente de réponse.

Le protocole ne porte aucun identifiant de corrélation (doc sections S3 et S6) :
la correspondance repose sur l'ordre d'envoi.
"""

from django.core.cache import cache
from django.test import TestCase

from devices.services import pending_commands


class PendingCommandsTests(TestCase):
    SN = 'TESTSN0001'

    def setUp(self):
        cache.clear()

    def test_fifo_order_is_preserved(self):
        """Régression : une clé unique par terminal écrasait le paquet précédent.

        Deux `setusername` d'affilée (limite de 50 enregistrements par paquet)
        doivent être dépilés dans l'ordre d'envoi.
        """
        pending_commands.push(self.SN, 'setusername', {'user_ids': [1, 2]})
        pending_commands.push(self.SN, 'setusername', {'user_ids': [3, 4]})

        self.assertEqual(pending_commands.pop(self.SN, 'setusername'), {'user_ids': [1, 2]})
        self.assertEqual(pending_commands.pop(self.SN, 'setusername'), {'user_ids': [3, 4]})
        self.assertIsNone(pending_commands.pop(self.SN, 'setusername'))

    def test_queues_are_isolated_per_command_and_terminal(self):
        pending_commands.push(self.SN, 'setusername', {'user_ids': [1]})
        pending_commands.push(self.SN, 'setuserinfo', {'enrollid': 7})
        pending_commands.push('AUTRE_SN', 'setusername', {'user_ids': [9]})

        self.assertEqual(pending_commands.pop(self.SN, 'setuserinfo'), {'enrollid': 7})
        self.assertEqual(pending_commands.pop(self.SN, 'setusername'), {'user_ids': [1]})
        self.assertEqual(pending_commands.pop('AUTRE_SN', 'setusername'), {'user_ids': [9]})

    def test_pop_on_empty_queue_returns_none(self):
        self.assertIsNone(pending_commands.pop(self.SN, 'setusername'))

    def test_clear_empties_all_queues_of_a_terminal(self):
        pending_commands.push(self.SN, 'setusername', {'user_ids': [1]})
        pending_commands.push(self.SN, 'setuserinfo', {'enrollid': 7})

        pending_commands.clear(self.SN)

        self.assertIsNone(pending_commands.pop(self.SN, 'setusername'))
        self.assertIsNone(pending_commands.pop(self.SN, 'setuserinfo'))

    def test_queue_is_capped(self):
        """Un terminal muet ne doit pas faire gonfler la file sans fin."""
        for i in range(pending_commands.MAX_PENDING + 10):
            pending_commands.push(self.SN, 'setuserinfo', {'enrollid': i})

        # Les plus anciennes sont abandonnees, les recentes conservees.
        first = pending_commands.pop(self.SN, 'setuserinfo')
        self.assertEqual(first, {'enrollid': 10})

    def test_missing_sn_is_ignored(self):
        pending_commands.push('', 'setusername', {'user_ids': [1]})
        self.assertIsNone(pending_commands.pop('', 'setusername'))

    def test_enrollid_zero_is_a_value_not_an_absence(self):
        """Régression : `if command.get('enrollid')` écartait l'enrollid 0.

        Le validateur n'interdit que les enrollid négatifs. Empiler par test de
        vérité laissait partir la commande SANS entrée dans la file, et toutes
        les réponses suivantes dépilaient les métadonnées du mauvais
        utilisateur.
        """
        pending_commands.push(self.SN, 'setuserinfo', {'enrollid': 0})
        pending_commands.push(self.SN, 'setuserinfo', {'enrollid': 7})

        self.assertEqual(pending_commands.pop(self.SN, 'setuserinfo'), {'enrollid': 0})
        self.assertEqual(pending_commands.pop(self.SN, 'setuserinfo'), {'enrollid': 7})

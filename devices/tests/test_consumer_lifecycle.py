"""
Tests du cycle de vie des connexions terminal.

Un terminal peut rouvrir une socket avant que la fermeture de la précédente
n'ait été livrée (timeout NAT, redémarrage). L'état partagé ne doit alors
jamais être détruit par la socket obsolète.
"""

import asyncio
import json
from datetime import datetime, timedelta

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, TestCase, override_settings

from devices.core.device_manager import DeviceManager


class FakeConsumer:
    """Double minimal : le DeviceManager n'appelle que `close()`."""

    def __init__(self, name):
        self.name = name
        self.closed = False

    async def close(self):
        self.closed = True


class UnregisterIdentityTests(TestCase):
    SN = 'TESTSN0003'

    def setUp(self):
        self.manager = DeviceManager.get_instance()
        # Le manager est un singleton de process : on repart d'un pool vide.
        self.manager._connections.clear()

    def tearDown(self):
        self.manager._connections.clear()

    def test_stale_consumer_cannot_unregister_its_replacement(self):
        """Régression : le `disconnect()` retardé tuait la connexion vivante.

        `unregister` ne portait que le SN : la fermeture tardive d'une socket
        déjà remplacée retirait l'entrée de la NOUVELLE connexion — terminal
        affiché hors ligne et commandes mises en file au lieu d'être envoyées.
        """
        old = FakeConsumer('ancienne')
        new = FakeConsumer('nouvelle')

        async_to_sync(self.manager.register)(self.SN, old)
        async_to_sync(self.manager.register)(self.SN, new)

        removed = async_to_sync(self.manager.unregister)(self.SN, consumer=old)

        self.assertFalse(removed, "l'ancienne socket ne doit rien retirer")
        self.assertIn(self.SN, self.manager._connections)
        self.assertIs(self.manager._connections[self.SN].consumer, new)

    def test_current_consumer_unregisters_itself(self):
        consumer = FakeConsumer('courante')
        async_to_sync(self.manager.register)(self.SN, consumer)

        removed = async_to_sync(self.manager.unregister)(self.SN, consumer=consumer)

        self.assertTrue(removed)
        self.assertNotIn(self.SN, self.manager._connections)

    def test_unregister_without_consumer_stays_unconditional(self):
        """Les appels d'administration (arrêt, purge) gardent l'ancien contrat."""
        async_to_sync(self.manager.register)(self.SN, FakeConsumer('x'))

        self.assertTrue(async_to_sync(self.manager.unregister)(self.SN))
        self.assertNotIn(self.SN, self.manager._connections)


class MalformedPayloadTests(SimpleTestCase):
    """Un message rejeté ne doit jamais laisser le terminal sans réponse."""

    def make_consumer(self):
        from devices.consumers import TM20ConsumerV2

        consumer = TM20ConsumerV2()
        consumer.sent = []

        async def fake_send(text_data=None, **kwargs):
            consumer.sent.append(text_data)

        consumer.send = fake_send
        return consumer

    def test_non_dict_payload_does_not_raise(self):
        """Régression : `message.get('cmd')` sur une liste levait AttributeError.

        Le routing accepte désormais tout chemin : n'importe quel client peut
        envoyer `[]` ou `5`. L'exception était avalée par le `except Exception`
        englobant — aucun `ret` émis, donc la retransmission silencieuse que ce
        chemin visait justement à supprimer, plus une trace complète par trame.
        """
        consumer = self.make_consumer()

        for payload in ('[]', '5', '"reg"'):
            with self.subTest(payload=payload):
                with self.assertNoLogs('devices.consumer', level='ERROR'):
                    async_to_sync(consumer.receive)(text_data=payload)

    def test_invalid_command_still_gets_a_failure_reply(self):
        consumer = self.make_consumer()

        async_to_sync(consumer.receive)(text_data='{"cmd": "reg"}')

        self.assertEqual(len(consumer.sent), 1, "le terminal doit recevoir un `ret`")
        reply = json.loads(consumer.sent[0])
        self.assertEqual(reply['ret'], 'reg')
        self.assertFalse(reply['result'])


class LivenessProbeTests(SimpleTestCase):
    """Le heartbeat doit distinguer « terminal inactif » de « terminal mort ».

    Régression : `last_message_at` n'étant alimenté que par `receive()`, et les
    TM20 ne répondant pas aux frames ping WebSocket, un terminal parfaitement
    sain mais sans pointage (la nuit) était fermé à chaque CONNECTION_TIMEOUT
    et reconnectait en boucle.
    """

    def make_consumer(self, silent_for=50):
        from devices.consumers import TM20ConsumerV2

        consumer = TM20ConsumerV2()
        consumer.sn = 'TESTSN0004'
        consumer.sent = []
        consumer.closed = False

        async def fake_send(text_data=None, **kwargs):
            consumer.sent.append(json.loads(text_data))

        async def fake_close(*args, **kwargs):
            consumer.closed = True

        consumer.send = fake_send
        consumer.close = fake_close
        consumer.last_message_at = datetime.now() - timedelta(seconds=silent_for)
        return consumer

    def run_loop(self, consumer, duration=0.05):
        async def runner():
            task = asyncio.create_task(consumer._heartbeat_loop())
            await asyncio.sleep(duration)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        async_to_sync(runner)()

    def settings_with(self, timeout):
        from django.conf import settings

        return {**settings.TM20_SETTINGS,
                'HEARTBEAT_INTERVAL': 0.01,
                'CONNECTION_TIMEOUT': timeout}

    def test_idle_terminal_is_probed_not_closed(self):
        consumer = self.make_consumer(silent_for=50)

        with override_settings(TM20_SETTINGS=self.settings_with(timeout=600)):
            self.run_loop(consumer)

        self.assertFalse(consumer.closed, "un terminal inactif ne doit pas être coupé")
        self.assertTrue(consumer.sent, "une sonde de vivacité devait partir")
        self.assertEqual(consumer.sent[0]['cmd'], 'gettime')

    def test_silence_beyond_timeout_closes_the_connection(self):
        consumer = self.make_consumer(silent_for=50)

        with override_settings(TM20_SETTINGS=self.settings_with(timeout=10)):
            self.run_loop(consumer)

        self.assertTrue(
            consumer.closed,
            "une socket muette malgré les sondes doit finir par être fermée",
        )

    def test_probe_is_not_repeated_within_the_interval(self):
        consumer = self.make_consumer(silent_for=50)
        consumer._last_probe_at = datetime.now()

        self.assertFalse(consumer._should_probe(interval=30))
        consumer._last_probe_at = datetime.now() - timedelta(seconds=31)
        self.assertTrue(consumer._should_probe(interval=30))

    def test_unregistered_connection_is_never_probed(self):
        """Avant `reg`, aucune commande n'a de destinataire identifiable."""
        consumer = self.make_consumer(silent_for=50)
        consumer.sn = None

        with override_settings(TM20_SETTINGS=self.settings_with(timeout=600)):
            self.run_loop(consumer)

        self.assertEqual(consumer.sent, [])

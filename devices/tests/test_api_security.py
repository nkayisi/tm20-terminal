"""
Tests de protection des endpoints JSON de gestion.

Ces vues sont authentifiées par cookie de session et exposent des actions
destructrices (`opendoor`, `reboot`, `cleanuser`, création de configuration) :
elles doivent refuser à la fois l'anonyme et la requête sans jeton CSRF.
"""

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from devices.models import Terminal


class CommandEndpointSecurityTests(TestCase):
    """Régression : `csrf_exempt` + session = CSRF exploitable.

    L'authentification par session avait été ajoutée sans retirer
    `csrf_exempt` : n'importe quel site tiers pouvait faire ouvrir une porte
    ou rebooter un terminal depuis le navigateur d'un exploitant connecté.
    """

    PATHS = (
        '/api/terminals/MIGTEST01/command/',   # SendCommandView
        '/api/api/configs/',                   # ThirdPartyConfigListView
    )

    def setUp(self):
        Terminal.objects.create(sn='MIGTEST01', model='TM20')
        self.user = get_user_model().objects.create_user(
            username='operateur', password='motdepasse'
        )

    def logged_client(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        return client

    def test_post_without_csrf_token_is_rejected(self):
        for path in self.PATHS:
            with self.subTest(path=path):
                response = self.logged_client().post(
                    path,
                    data=json.dumps({'command': 'opendoor', 'name': 'x',
                                     'base_url': 'https://x.test'}),
                    content_type='application/json',
                )
                self.assertEqual(
                    response.status_code, 403,
                    "une session seule ne doit pas suffire à agir",
                )

    def test_post_with_csrf_token_is_accepted(self):
        client = self.logged_client()
        client.get('/dashboard/')                 # dépose le cookie csrftoken
        token = client.cookies['csrftoken'].value

        response = client.post(
            '/api/terminals/MIGTEST01/command/',
            data=json.dumps({'command': 'gettime'}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

    def test_anonymous_is_rejected_before_anything_else(self):
        for path in self.PATHS:
            with self.subTest(path=path):
                response = Client().post(
                    path,
                    data=json.dumps({'command': 'opendoor'}),
                    content_type='application/json',
                )
                self.assertEqual(response.status_code, 401)

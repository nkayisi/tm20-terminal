"""
Diagnostic de connectivité des terminaux.

Répond à la question « le terminal atteint-il le serveur ? » sans avoir à
lire les journaux : adresse à configurer sur le terminal, présence live, et
surveillance en direct des tentatives de connexion.
"""

import socket
import time
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from devices.core.device_manager import DeviceManager
from devices.models import Terminal

PORT = 7788


class Command(BaseCommand):
    help = "Diagnostique la connectivité des terminaux TM20"

    def add_arguments(self, parser):
        parser.add_argument(
            '--watch',
            type=int,
            default=0,
            metavar='SECONDES',
            help="Surveille les connexions pendant N secondes et signale tout changement.",
        )

    def handle(self, *args, **options):
        self._show_listen_addresses()
        self._show_live_presence()
        self._show_known_terminals()

        if options['watch']:
            self._watch(options['watch'])
        else:
            self.stdout.write(
                "\nAstuce : `--watch 120` surveille les connexions pendant "
                "2 minutes, le temps de redémarrer le terminal."
            )

    # --- sections ---------------------------------------------------------

    def _show_listen_addresses(self):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n1. Adresse à configurer sur le terminal"
        ))

        if self._in_container():
            # L'IP visible depuis le conteneur est celle du réseau Docker :
            # elle n'est PAS joignable depuis le terminal.
            self.stdout.write(
                "  Serveur dans un conteneur : l'adresse à saisir sur le terminal\n"
                "  est celle de la MACHINE HÔTE sur le réseau local.\n"
                "\n"
                "      ws://<IP-de-l-hote>:%d/\n"
                "\n"
                "  Relevez-la sur l'hôte avec :\n"
                "      macOS   : ipconfig getifaddr en0\n"
                "      Linux   : hostname -I\n"
                "      Windows : ipconfig" % PORT
            )
            seen = sorted(self._local_ipv4())
            if seen:
                self.stdout.write(self.style.WARNING(
                    "\n  (vu depuis le conteneur : %s — réseau Docker,\n"
                    "   inutilisable depuis le terminal)" % ', '.join(seen)
                ))
        else:
            addresses = sorted(self._local_ipv4())
            if not addresses:
                self.stdout.write(self.style.WARNING("  Aucune adresse IPv4 détectée."))
                return
            for ip in addresses:
                self.stdout.write("  ws://%s:%d/" % (ip, PORT))

        self.stdout.write(
            "\n  Le terminal doit être sur le MÊME réseau que cette adresse.\n"
            "  Le chemin n'a aucune importance : tout chemin est accepté."
        )

    def _show_live_presence(self):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n2. Terminaux connectés en ce moment"
        ))

        sns = DeviceManager.get_connected_sns_from_redis()
        details = DeviceManager.get_connected_details_from_redis()

        if not sns:
            self.stdout.write(self.style.WARNING("  Aucun terminal connecté."))
            return

        for sn in sns:
            info = details.get(sn) or {}
            self.stdout.write(self.style.SUCCESS(
                "  %s  depuis %s (%s message(s))" % (
                    sn, info.get('connected_at', '?'), info.get('message_count', 0)
                )
            ))

    def _show_known_terminals(self):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n3. Terminaux connus de l'application"
        ))

        terminals = Terminal.objects.all().order_by('-last_seen')
        if not terminals:
            self.stdout.write(
                "  Aucun terminal enregistré : aucun n'a jamais envoyé de `reg`."
            )
            return

        connected = set(DeviceManager.get_connected_sns_from_redis())
        now = timezone.now()
        for t in terminals:
            state = "EN LIGNE" if t.sn in connected else "hors ligne"
            if t.last_seen:
                age = int((now - t.last_seen).total_seconds())
                seen = "vu il y a %d min" % (age // 60) if age >= 60 else "vu il y a %d s" % age
            else:
                seen = "jamais vu"
            self.stdout.write("  [%-9s] %-24s %-16s %s" % (
                state, t.short_label, t.ip_address or "IP inconnue", seen
            ))

    def _watch(self, seconds: int):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n4. Surveillance pendant %ds — redémarrez le terminal maintenant" % seconds
        ))

        previous = set(DeviceManager.get_connected_sns_from_redis())
        deadline = time.monotonic() + seconds

        while time.monotonic() < deadline:
            time.sleep(2)
            current = set(DeviceManager.get_connected_sns_from_redis())
            for sn in sorted(current - previous):
                self.stdout.write(self.style.SUCCESS("  + %s vient de se connecter" % sn))
            for sn in sorted(previous - current):
                self.stdout.write(self.style.WARNING("  - %s s'est déconnecté" % sn))
            previous = current

        if previous:
            self.stdout.write(self.style.SUCCESS(
                "\n  %d terminal/terminaux connecté(s) : %s" % (
                    len(previous), ', '.join(sorted(previous))
                )
            ))
        else:
            self.stdout.write(self.style.ERROR(
                "\n  Aucune connexion reçue.\n"
                "  Le terminal n'atteint pas ce serveur : vérifiez l'adresse IP et\n"
                "  le port configurés SUR le terminal, et qu'il est bien sur le\n"
                "  même réseau que l'hôte."
            ))

    # --- utilitaires ------------------------------------------------------

    @staticmethod
    def _in_container() -> bool:
        return Path('/.dockerenv').exists()

    @staticmethod
    def _local_ipv4():
        """Adresses IPv4 non-loopback vues depuis ce processus."""
        found = set()
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = info[4][0]
                if not ip.startswith('127.'):
                    found.add(ip)
        except socket.gaierror:
            pass

        # Repli : l'adresse utilisée pour sortir vers l'extérieur.
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            found.add(s.getsockname()[0])
            s.close()
        except OSError:
            pass

        return found

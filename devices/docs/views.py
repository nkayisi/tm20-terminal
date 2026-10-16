"""
Documentation publique.

Les contrats d'integration sont lus par des gens qui n'ont pas de compte sur
ce serveur -- l'equipe qui ecrit le recepteur, en general chez le client. Ces
vues sont donc volontairement hors `LoginRequiredMixin` : elles ne decrivent
que la forme des echanges, jamais une donnee d'exploitation. Rien de ce
qu'elles rendent ne depend de la base.
"""

from django.views.generic import TemplateView


class AttendancePayloadDocView(TemplateView):
    """Contrat du corps envoye aux services tiers pour les pointages.

    Le pendant web de `docs/payload_pointages_services_tiers.md`. Les deux
    exemples qui y figurent sont tenus synchronises avec la chaine d'emission
    par `devices/tests/test_docs_payload_page.py` : ils ne peuvent pas devenir
    faux sans faire echouer la suite.
    """

    template_name = 'devices/docs/attendance_payload.html'

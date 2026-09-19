"""
Répare les terminaux dont `is_active` a été mis à False par l'ancien bug.

Auparavant, le consumer WebSocket faisait `is_active=False` à CHAQUE
déconnexion (reconnexion, timeout heartbeat, redémarrage du terminal). Comme
toutes les pages de gestion filtrent `is_active=True`, un terminal pourtant
connecté disparaissait de « Synchronisation Utilisateurs », etc.

`is_active` redevient ce qu'il aurait toujours dû être : un drapeau
d'administration (« terminal géré/activé »). L'état de connexion live est,
lui, lu depuis Redis. Cette migration réactive les terminaux en liste blanche
qui avaient été désactivés à tort.
"""

from django.db import migrations


def reactivate_whitelisted_terminals(apps, schema_editor):
    Terminal = apps.get_model('devices', 'Terminal')
    Terminal.objects.filter(is_whitelisted=True, is_active=False).update(is_active=True)


def noop_reverse(apps, schema_editor):
    # Pas de retour arrière : on ne peut pas savoir lesquels étaient
    # volontairement désactivés avant la réparation.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('devices', '0003_biometric_user_refactor'),
    ]

    operations = [
        migrations.RunPython(reactivate_whitelisted_terminals, noop_reverse),
    ]

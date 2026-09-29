"""
Briques d'interface partagées par tous les gabarits du dashboard.

Ces tags existent pour retirer trois choses des pages :
  - les SVG recopiés à la main (`{% icon %}` pointe un sprite unique) ;
  - le balisage de formulaire dupliqué, et avec lui les classes Tailwind
    codées en dur dans `devices/dashboard/forms.py` (`{% field %}`) ;
  - la navigation, dont l'état actif reposait sur un mélange d'égalité exacte
    et de test de sous-chaîne sur `url_name` (`{% sidebar_nav %}`).
"""

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
#
# `match` est un ensemble explicite de `url_name`. L'ancien code testait
# `'attendance' in url_name` : un futur `attendance_detail` aurait allumé
# l'entrée « Sync Pointages » par accident. Une appartenance à un ensemble ne
# se trompe pas.
# « Vue d'ensemble » a ete retiree : ses indicateurs existent deja sur le
# monitoring et ses quatre cartes-boutons dupliquaient exactement cette barre.
# « Horaires » est hors navigation pour l'instant ; la page reste joignable par
# son URL et reviendra comme onglet de la fiche terminal.
NAV_SECTIONS = [
    {
        'label': None,
        'items': [
            {'url': 'dashboard:index', 'label': 'Monitoring temps réel',
             'icon': 'bolt', 'match': {'index'}},
        ],
    },
    {
        'label': 'Gestion',
        'items': [
            {'url': 'dashboard:third_party_configs', 'label': 'Services tiers',
             'icon': 'cloud',
             'match': {'third_party_configs', 'third_party_config_edit'}},
            {'url': 'dashboard:user_sync', 'label': 'Sync utilisateurs',
             'icon': 'user-group', 'match': {'user_sync'}},
            {'url': 'dashboard:attendance_sync', 'label': 'Sync pointages',
             'icon': 'clipboard-list', 'match': {'attendance_sync'}},
        ],
    },
]


@register.inclusion_tag('ui/_nav.html', takes_context=True)
def sidebar_nav(context):
    """Rend la navigation latérale depuis un manifeste unique."""
    match = getattr(context.get('request'), 'resolver_match', None)
    current = match.url_name if match else ''
    sections = []
    for section in NAV_SECTIONS:
        sections.append({
            'label': section['label'],
            'items': [
                {**item, 'is_current': current in item['match']}
                for item in section['items']
            ],
        })
    return {'sections': sections}


# ---------------------------------------------------------------------------
# Icônes
# ---------------------------------------------------------------------------
@register.inclusion_tag('ui/_icon.html')
def icon(name, css_class='size-5'):
    """Référence un symbole du sprite.

    La taille est passée par l'appelant sous forme de classe complète. Ne
    jamais la composer ici (`w-{{ n }}`) : le purge de Tailwind analyse le
    source de façon statique et ne verrait pas une classe construite.
    """
    return {'name': name, 'css_class': css_class}


# ---------------------------------------------------------------------------
# Formulaires
# ---------------------------------------------------------------------------
@register.inclusion_tag('ui/_field.html')
def field(bound_field, help_text='', css_class=''):
    """Rend un champ complet : libellé, widget, aide, erreurs.

    Signale aussi l'état invalide au widget (`aria-invalid`), ce qui suffit à
    le colorer : la règle vit dans la feuille de style, pas dans le Python.
    """
    widget_attrs = bound_field.field.widget.attrs
    if bound_field.errors:
        widget_attrs['aria-invalid'] = 'true'
    if help_text or bound_field.help_text:
        widget_attrs['aria-describedby'] = f'{bound_field.auto_id}_help'
    return {
        'field': bound_field,
        'help_text': help_text or bound_field.help_text,
        'css_class': css_class,
        'is_checkbox': bound_field.widget_type == 'checkbox',
    }


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------
@register.simple_tag(takes_context=True)
def querystring(context, **kwargs):
    """Réécrit la query string courante en préservant les autres paramètres.

    Indispensable dès qu'une page combine filtres, tri et pagination : sans
    cela, changer de page perd les filtres. `None` retire un paramètre.
    """
    request = context.get('request')
    params = request.GET.copy() if request else {}
    for key, value in kwargs.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode() if hasattr(params, 'urlencode') else ''
    return mark_safe(f'?{encoded}' if encoded else '')


@register.simple_tag
def pct(used, total):
    """Pourcentage borné à 100, pour une barre de capacité."""
    try:
        used, total = float(used or 0), float(total or 0)
    except (TypeError, ValueError):
        return 0
    if total <= 0:
        return 0
    return min(round(used / total * 100), 100)


@register.filter
def tone_for_message(tags):
    """Traduit les tags du framework messages en tons du design system."""
    mapping = {
        'success': 'success',
        'error': 'danger',
        'warning': 'warning',
        'info': 'info',
        'debug': 'neutral',
    }
    for tag in (tags or '').split():
        if tag in mapping:
            return mapping[tag]
    return 'info'

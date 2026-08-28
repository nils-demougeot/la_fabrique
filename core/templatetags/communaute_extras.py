"""Filtres et balises des gabarits de l'onglet Partage.

Volontairement minimal : uniquement ce qu'un gabarit ne sait pas faire seul
(répéter N fois, formater un nombre à la française, choisir une teinte
d'avatar stable).
"""

from django import template

register = template.Library()


@register.filter(name='repeter')
def repeter(nombre):
    """Itérable de `nombre` éléments — pour dessiner N cubes, N barres…

    ``{% for _ in 3|repeter %}`` est plus lisible qu'un `range` passé par la
    vue quand la valeur est une constante du design.
    """
    try:
        return range(int(nombre))
    except (TypeError, ValueError):
        return range(0)


@register.filter(name='adversaire')
def adversaire(duel, utilisateur):
    """L'autre joueuse d'un duel, vue depuis `utilisateur`."""
    if duel is None or utilisateur is None:
        return None
    return duel.adversaire_de(utilisateur)


@register.filter(name='jusqua')
def jusqua(depart, arrivee):
    """Plage ``depart..arrivee`` (borne haute exclue)."""
    try:
        return range(int(depart), int(arrivee))
    except (TypeError, ValueError):
        return range(0)


@register.filter(name='espace_millier')
def espace_millier(valeur):
    """1240 → « 1 240 ».

    Espace insécable ordinaire (U+00A0) plutôt que fine (U+202F) :
    c'est la largeur des maquettes, et le nombre ne se coupe jamais
    en fin de ligne.
    """
    try:
        entier = int(valeur)
    except (TypeError, ValueError):
        return valeur
    return f"{entier:,}".replace(",", " ")


# Teintes d'avatar de la maquette, dans l'ordre où elles y apparaissent.
_TEINTES_JETON = ['t-or', 't-vert', 't-violet', 't-corail']


@register.filter(name='teinte')
def teinte(utilisateur):
    """Teinte du jeton rond — la même couleur suit la couturière partout.

    Elle vient du profil de jeu quand elle y est renseignée ; sinon on la
    déduit de la clé du compte, ce qui reste stable dans le temps.
    """
    profil = getattr(utilisateur, 'profil_jeu', None)
    if profil is not None and profil.teinte:
        return profil.teinte
    pk = getattr(utilisateur, 'pk', None) or 0
    return _TEINTES_JETON[pk % len(_TEINTES_JETON)]


@register.filter(name='initiales')
def initiales(utilisateur):
    """Initiales affichées dans les jetons ronds."""
    profil = getattr(utilisateur, 'profil_jeu', None)
    if profil is not None:
        return profil.initiales
    prenom = (getattr(utilisateur, 'first_name', '') or
              getattr(utilisateur, 'username', '') or '?').strip()
    nom = (getattr(utilisateur, 'last_name', '') or '').strip()
    if nom:
        return (prenom[0] + nom[0]).upper()
    return prenom[:2].upper()


@register.filter(name='nom_court')
def nom_court(utilisateur):
    """« Sofia D. » si le nom complet est connu, sinon l'identifiant."""
    profil = getattr(utilisateur, 'profil_jeu', None)
    if profil is not None:
        return profil.nom_affiche
    prenom = getattr(utilisateur, 'first_name', '') or ''
    nom = getattr(utilisateur, 'last_name', '') or ''
    if prenom and nom:
        return f"{prenom} {nom[0]}."
    return prenom or getattr(utilisateur, 'username', '')


@register.filter(name='prenom')
def prenom(utilisateur):
    return (getattr(utilisateur, 'first_name', '') or
            getattr(utilisateur, 'username', ''))


@register.filter(name='mentions', is_safe=True)
def mentions(message):
    """Rend le texte d'un message avec ses « @ » mis en avant.

    Seules les mentions **résolues** (celles enregistrées à l'envoi) sont
    surlignées : un « @ » qui ne désigne personne reste du texte ordinaire.
    Tout est échappé avant assemblage — le contenu vient des utilisatrices.
    """
    from django.utils.html import escape
    from django.utils.safestring import mark_safe

    texte = escape(message.contenu or '')
    if not texte or '@' not in texte:
        return mark_safe(texte.replace('\n', '<br>'))

    for membre in message.mentions.all():
        for etiquette in filter(None, [
            f"{membre.first_name} {membre.last_name[:1]}."
            if membre.first_name and membre.last_name else None,
            membre.first_name,
            membre.username,
        ]):
            cible = escape(f"@{etiquette}")
            if cible in texte:
                texte = texte.replace(
                    cible, f'<span class="cg-mention">{cible}</span>', 1)
                break

    return mark_safe(texte.replace('\n', '<br>'))


@register.filter(name='depuis')
def depuis(date_heure):
    """Ancienneté en une seule unité : « 12 min », « 3 h », « 9 j ».

    `timesince` produit « 12 minutes, 30 secondes » ; le tronquer laisse une
    ellipse (« 12 … ») au milieu des pastilles de la maquette.
    """
    from django.utils import timezone

    if not date_heure:
        return ''
    minutes = int((timezone.now() - date_heure).total_seconds() // 60)
    if minutes < 60:
        return f"{max(1, minutes)} min"
    if minutes < 60 * 24:
        return f"{minutes // 60} h"
    return f"{minutes // (60 * 24)} j"

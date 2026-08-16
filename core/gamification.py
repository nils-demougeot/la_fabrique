"""Logique de jeu de l'onglet Partage.

Un seul endroit décide : ce qu'est un niveau, comment une série de jours se
prolonge ou se casse, comment l'XP se répartit entre le total et la saison, et
comment on avance une quête. Les vues n'appellent que les fonctions publiques
d'ici, jamais les règles à la main.

Points d'entrée principaux
--------------------------
``profil_de(user)``            profil de jeu (créé au besoin)
``etat_joueuse(user)``         dict complet pour la carte d'atelier
``gagner_xp(user, n, motif)``  crédite XP total + XP de saison
``marquer_activite(user)``     fait vivre la série de jours
``avancer_quete(user, code)``  progression d'une quête, récompense incluse
``classement(user)``           lignes de classement de la ligue courante
"""

import re
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from .models import (
    Utilisateur, Amitie, CoffreQuotidien, DefiVille, Duel, Ecusson, EcussonObtenu,
    Notification, PalierReclame, PalierSaison, ParticipationLigue, ProfilJeu,
    Quete, QueteUtilisateur, Saison, TransactionPieces,
)


# ─────────────────────────────────────────────────────────────────────────────
# Niveaux d'atelier — barème unique de l'application
# ─────────────────────────────────────────────────────────────────────────────
# Le niveau se calcule à partir des CP (points d'atelier), eux-mêmes tirés de
# l'activité réelle : tissus scannés, étapes de couture réalisées, projets
# terminés. C'est le barème du tableau de bord, et la communauté s'en sert tel
# quel — un seul endroit décide de ce qu'est un niveau.
#
# À ne pas confondre avec l'XP de saison (`ParticipationLigue.xp_saison`), qui
# est un compteur de compétition remis à zéro à chaque saison et sert au seul
# classement de ligue.

POINTS_PAR_VETEMENT = 20
POINTS_PAR_ETAPE = 10
POINTS_PAR_PROJET = 60

# (CP cumulés requis pour atteindre le niveau, nom du niveau).
NIVEAUX_ATELIER = [
    (0,    'Première aiguille'),
    (120,  'Fil conducteur'),
    (320,  'Main sûre'),
    (620,  'Belle ouvrage'),
    (1000, 'Artisan du textile'),
    (1500, "Maître d'atelier"),
]
NIVEAU_MAX = len(NIVEAUX_ATELIER)


def points_depuis_activite(nb_vetements, nb_etapes, nb_projets):
    """CP d'atelier à partir des compteurs d'activité déjà calculés."""
    return (nb_vetements * POINTS_PAR_VETEMENT
            + nb_etapes * POINTS_PAR_ETAPE
            + nb_projets * POINTS_PAR_PROJET)


def niveau_depuis_points(points):
    """Décompose un total de CP en niveau, nom, progression dans le palier.

    Les clés `nom`, `numero`, `points`, `pourcentage`, `points_restants` et
    `niveau_suivant` sont celles qu'attend le tableau de bord ; les autres
    servent à la carte d'atelier de la communauté.
    """
    points = max(0, int(points or 0))

    index = 0
    for i, (seuil, _) in enumerate(NIVEAUX_ATELIER):
        if points >= seuil:
            index = i

    seuil_courant, nom = NIVEAUX_ATELIER[index]
    if index + 1 < len(NIVEAUX_ATELIER):
        seuil_suivant = NIVEAUX_ATELIER[index + 1][0]
        palier = seuil_suivant - seuil_courant
        dans_niveau = points - seuil_courant
        pourcentage = round(dans_niveau / palier * 100)
        restants = seuil_suivant - points
        niveau_suivant = index + 2
        nom_suivant = NIVEAUX_ATELIER[index + 1][1]
    else:
        # Dernier niveau : la barre reste pleine, il n'y a plus rien à viser.
        palier = max(1, seuil_courant - NIVEAUX_ATELIER[index - 1][0])
        dans_niveau = palier
        pourcentage, restants, niveau_suivant, nom_suivant = 100, 0, None, None
        seuil_suivant = seuil_courant

    return {
        'numero': index + 1,
        'nom': nom,
        'points': points,
        'seuil_courant': seuil_courant,
        'seuil_suivant': seuil_suivant,
        'points_dans_niveau': dans_niveau,
        'points_palier': palier,
        'pourcentage': pourcentage,
        'points_restants': restants,
        'niveau_suivant': niveau_suivant,
        'nom_suivant': nom_suivant,
    }


def points_atelier(user):
    """CP d'atelier de `user`, recalculés depuis son activité réelle."""
    from django.db.models import Count
    from .models import ProgressionProjet, Vetement

    nb_vetements = Vetement.objects.filter(utilisateur=user).count()

    nb_etapes = nb_projets = 0
    progressions = (
        ProgressionProjet.objects
        .filter(utilisateur=user)
        .annotate(nb_etapes_patron=Count('patron__etapes'))
    )
    for progression in progressions:
        if progression.termine:
            nb_projets += 1
            nb_etapes += progression.nb_etapes_patron
        else:
            # Étapes validées d'un projet en cours = étape courante − 1.
            nb_etapes += max(0, progression.etape_actuelle - 1)

    return points_depuis_activite(nb_vetements, nb_etapes, nb_projets)


def niveau_de(user):
    """Niveau d'atelier complet de `user`."""
    return niveau_depuis_points(points_atelier(user))


def montee_de_niveau(user, niveau=None):
    """Niveau fraîchement atteint et jamais fêté, sinon None.

    Le niveau se recalculant depuis les CP, rien n'indique en soi qu'il vient
    de monter : on le compare au dernier niveau célébré (`ProfilJeu.niveau_vu`).
    """
    profil = profil_de(user)
    niveau = niveau or niveau_de(user)

    # Premier passage : on cale le repère sans rien fêter rétroactivement.
    if profil.niveau_vu == 0:
        profil.niveau_vu = niveau['numero']
        profil.save(update_fields=['niveau_vu'])
        return None

    return niveau if niveau['numero'] > profil.niveau_vu else None


def marquer_niveau_vu(user, numero):
    """Enregistre que la célébration du niveau `numero` a été montrée."""
    profil = profil_de(user)
    if numero > profil.niveau_vu:
        profil.niveau_vu = numero
        profil.save(update_fields=['niveau_vu'])
    return profil


# Ce que chaque niveau ouvre. Purement éditorial : sert à donner une raison
# de viser le palier suivant, sans rien contraindre côté code.
AVANTAGES_NIVEAU = {
    1: ["Banque de tissus", "Premiers patrons"],
    2: ["Duels entre amis", "Salons de quartier"],
    3: ["Patrons intermédiaires", "Défis de ville"],
    4: ["Patrons avancés", "Boutique complète"],
    5: ["Ateliers à animer", "Écussons rares"],
    6: ["Écusson Diamant", "Tous les patrons"],
}


def detail_points(user):
    """Décomposition des CP : ce qui les a produits, ligne par ligne.

    Sert à répondre « d'où viennent mes points ? » sur l'écran de progression.
    """
    from django.db.models import Count
    from .models import ProgressionProjet, Vetement

    nb_vetements = Vetement.objects.filter(utilisateur=user).count()
    nb_etapes = nb_projets = 0
    for progression in (ProgressionProjet.objects.filter(utilisateur=user)
                        .annotate(nb_etapes_patron=Count('patron__etapes'))):
        if progression.termine:
            nb_projets += 1
            nb_etapes += progression.nb_etapes_patron
        else:
            nb_etapes += max(0, progression.etape_actuelle - 1)

    return [
        {'cle': 'tissus', 'libelle': 'Tissus analysés', 'nombre': nb_vetements,
         'unite': POINTS_PAR_VETEMENT, 'points': nb_vetements * POINTS_PAR_VETEMENT,
         'route': 'ajout_textile', 'action': 'Scanner un tissu'},
        {'cle': 'etapes', 'libelle': 'Étapes de couture', 'nombre': nb_etapes,
         'unite': POINTS_PAR_ETAPE, 'points': nb_etapes * POINTS_PAR_ETAPE,
         'route': 'patrons', 'action': 'Reprendre un projet'},
        {'cle': 'projets', 'libelle': 'Projets terminés', 'nombre': nb_projets,
         'unite': POINTS_PAR_PROJET, 'points': nb_projets * POINTS_PAR_PROJET,
         'route': 'patrons', 'action': 'Choisir un patron'},
    ]


def echelle_niveaux(user, niveau=None):
    """Les six niveaux avec leur état vis-à-vis de la joueuse.

    état ∈ {acquis, courant, avenir} — c'est l'échelle complète de l'écran
    de progression.
    """
    niveau = niveau or niveau_de(user)
    lignes = []
    for index, (seuil, nom) in enumerate(NIVEAUX_ATELIER):
        numero = index + 1
        if numero < niveau['numero']:
            etat = 'acquis'
        elif numero == niveau['numero']:
            etat = 'courant'
        else:
            etat = 'avenir'
        lignes.append({
            'numero': numero,
            'nom': nom,
            'seuil': seuil,
            'etat': etat,
            'avantages': AVANTAGES_NIVEAU.get(numero, []),
            'points_manquants': max(0, seuil - niveau['points']),
        })
    return lignes


def signaler_montee_de_niveau(user):
    """Notifie la joueuse si elle vient de franchir un niveau.

    Appelé après toute action susceptible de faire bouger les CP ; la
    notification n'est déposée qu'une fois grâce à `niveau_vu`.
    """
    niveau = niveau_de(user)
    if montee_de_niveau(user, niveau) is None:
        return None
    return notifier(
        user, 'niveau',
        f"Niveau {niveau['numero']} · {niveau['nom']}",
        "Un coffre du sentier t'attend peut-être.",
        lien_url='communaute_progression',
    )


# ─────────────────────────────────────────────────────────────────────────────
# Profil de jeu
# ─────────────────────────────────────────────────────────────────────────────

def _code_atelier(user):
    """Code de parrainage stable et lisible : FAB-4821."""
    return f"FAB-{4000 + (user.pk * 37) % 5999:04d}"


def profil_de(user):
    """Profil de jeu de `user`, créé au premier accès."""
    profil, cree = ProfilJeu.objects.get_or_create(
        utilisateur=user,
        defaults={'code_atelier': _code_atelier(user)},
    )
    if not profil.code_atelier:
        profil.code_atelier = _code_atelier(user)
        profil.save(update_fields=['code_atelier'])
    return profil


def saison_active():
    """Saison en cours, ou la plus récente si aucune n'est marquée active."""
    return Saison.objects.filter(active=True).first() or Saison.objects.first()


def participation_de(user, saison=None):
    """Inscription de `user` à la ligue de la saison courante."""
    saison = saison or saison_active()
    if not saison:
        return None
    participation, _ = ParticipationLigue.objects.get_or_create(
        utilisateur=user, saison=saison, defaults={'ligue': 'or'},
    )
    return participation


# ─────────────────────────────────────────────────────────────────────────────
# Série de jours
# ─────────────────────────────────────────────────────────────────────────────

def _cle_semaine(jour=None):
    jour = jour or timezone.localdate()
    annee, semaine, _ = jour.isocalendar()
    return f"{annee}-W{semaine:02d}"


def _cle_jour(jour=None):
    return (jour or timezone.localdate()).isoformat()


@transaction.atomic
def marquer_activite(user, jour=None):
    """Compte une journée d'atelier et fait vivre la série.

    - même jour        : rien à faire ;
    - lendemain        : la série avance d'un cran ;
    - un jour sauté    : un gel est consommé si disponible, sinon la série
                         repart à 1 ;
    - plus d'un jour   : la série repart à 1.
    """
    profil = profil_de(user)
    jour = jour or timezone.localdate()

    if profil.derniere_activite == jour:
        return profil

    jour_gele = None
    if profil.derniere_activite is None:
        profil.serie_actuelle = 1
    else:
        ecart = (jour - profil.derniere_activite).days
        if ecart == 1:
            profil.serie_actuelle += 1
        elif ecart == 2 and profil.gels > 0:
            # Un seul jour manqué : le gel protège la série. On retient
            # lequel, pour que le calendrier de la semaine ne montre un gel
            # que là où il a réellement joué.
            profil.gels -= 1
            profil.serie_actuelle += 1
            jour_gele = jour - timedelta(days=1)
        else:
            profil.serie_actuelle = 1

    profil.serie_record = max(profil.serie_record, profil.serie_actuelle)
    profil.derniere_activite = jour

    # Calendrier hebdomadaire (écran 45b) : remis à zéro au changement de semaine.
    cle = _cle_semaine(jour)
    if profil.semaine_cle != cle:
        profil.jours_geles = ''
    jours = set(profil.jours_travailles) if profil.semaine_cle == cle else set()
    jours.add(jour.weekday())
    geles = set(profil.jours_geles_travailles) if profil.semaine_cle == cle else set()
    if jour_gele is not None and _cle_semaine(jour_gele) == cle:
        geles.add(jour_gele.weekday())
    profil.semaine_cle = cle
    profil.jours_semaine = ','.join(str(j) for j in sorted(jours))
    profil.jours_geles = ','.join(str(j) for j in sorted(geles))

    profil.save()
    return profil


def serie_en_danger(profil):
    """True si la série n'a pas encore été entretenue aujourd'hui."""
    return profil.derniere_activite != timezone.localdate()


def calendrier_semaine(profil):
    """7 cases (lundi → dimanche) pour l'écran 45b.

    Chaque case : {lettre, etat} avec etat ∈ {fait, gel, aujourdhui, vide}.
    """
    lettres = ['L', 'M', 'M', 'J', 'V', 'S', 'D']
    aujourd_hui = timezone.localdate()
    meme_semaine = profil.semaine_cle == _cle_semaine()
    faits = set(profil.jours_travailles) if meme_semaine else set()
    geles = set(profil.jours_geles_travailles) if meme_semaine else set()
    cases = []
    for i, lettre in enumerate(lettres):
        if i == aujourd_hui.weekday() and i not in faits:
            etat = 'aujourdhui'
        elif i in faits:
            etat = 'fait'
        elif i in geles:
            etat = 'gel'
        else:
            etat = 'vide'
        cases.append({'lettre': lettre, 'etat': etat})
    return cases


# ─────────────────────────────────────────────────────────────────────────────
# XP et pièces
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def gagner_xp(user, montant, motif=''):
    """Crédite l'XP au total du joueur ET à sa saison, puis marque la journée.

    Retourne (profil, participation) après mise à jour.
    """
    montant = max(0, int(montant))
    profil = profil_de(user)
    if montant:
        profil.xp_total += montant
        profil.save(update_fields=['xp_total'])

        participation = participation_de(user)
        if participation:
            participation.xp_saison += montant
            participation.save(update_fields=['xp_saison'])
    else:
        participation = participation_de(user)

    marquer_activite(user)
    verifier_ecussons(user)
    return profil, participation


@transaction.atomic
def crediter_pieces(user, montant, libelle, icone='piece'):
    """Ajoute (ou retire) des pièces et journalise la transaction."""
    user.soldePieces = max(0, user.soldePieces + int(montant))
    user.save(update_fields=['soldePieces'])
    TransactionPieces.objects.create(
        utilisateur=user, libelle=libelle, montant=int(montant), icone=icone,
    )
    return user.soldePieces


def depenser_pieces(user, montant, libelle, icone='piece'):
    """Débite des pièces si le solde suffit. Retourne (ok, message)."""
    montant = int(montant)
    if user.soldePieces < montant:
        return False, "Pas assez de pièces."
    crediter_pieces(user, -montant, libelle, icone)
    return True, "C'est à toi !"


# ─────────────────────────────────────────────────────────────────────────────
# Quêtes
# ─────────────────────────────────────────────────────────────────────────────

def quetes_du_jour(user):
    """Avancements des quêtes quotidiennes, créés au besoin."""
    cle = _cle_jour()
    avancements = []
    for quete in Quete.objects.filter(active=True, periode='jour'):
        avancement, _ = QueteUtilisateur.objects.get_or_create(
            utilisateur=user, quete=quete, periode_cle=cle,
        )
        avancements.append(avancement)
    return avancements


def quetes_de_la_semaine(user):
    cle = _cle_semaine()
    avancements = []
    for quete in Quete.objects.filter(active=True, periode='semaine'):
        avancement, _ = QueteUtilisateur.objects.get_or_create(
            utilisateur=user, quete=quete, periode_cle=cle,
        )
        avancements.append(avancement)
    return avancements


@transaction.atomic
def avancer_quete(user, code_quete, pas=1):
    """Fait progresser une quête et verse sa récompense à l'achèvement.

    Silencieux si la quête n'existe pas : les appels depuis le reste de
    l'application ne doivent pas casser parce qu'une quête a été retirée.
    """
    quete = Quete.objects.filter(code=code_quete, active=True).first()
    if not quete:
        return None

    cle = _cle_jour() if quete.periode == 'jour' else _cle_semaine()
    avancement, _ = QueteUtilisateur.objects.get_or_create(
        utilisateur=user, quete=quete, periode_cle=cle,
    )
    if avancement.terminee:
        return avancement

    avancement.avancement = min(quete.objectif, avancement.avancement + pas)
    if avancement.avancement >= quete.objectif:
        avancement.terminee = True
        if not avancement.recompense_versee:
            avancement.recompense_versee = True
            avancement.save()
            if quete.xp:
                gagner_xp(user, quete.xp, f"Quête : {quete.libelle}")
            if quete.pieces:
                crediter_pieces(user, quete.pieces, f"Quête : {quete.libelle}")
            _ouvrir_droit_coffre(user)
            return avancement
    avancement.save()
    return avancement


def _ouvrir_droit_coffre(user):
    """Crée le coffre du jour dès que toutes les quêtes quotidiennes sont faites."""
    avancements = quetes_du_jour(user)
    if avancements and all(a.terminee for a in avancements):
        coffre, cree = CoffreQuotidien.objects.get_or_create(
            utilisateur=user, periode_cle=_cle_jour(), defaults={'pieces': 30},
        )
        if cree:
            notifier(
                user, 'coffre', 'Coffre du jour débloqué',
                f"Toutes tes quêtes sont faites · {coffre.pieces} pièces.",
                lien_url='communaute_quetes',
            )


def coffre_du_jour(user):
    return CoffreQuotidien.objects.filter(utilisateur=user, periode_cle=_cle_jour()).first()


# ─────────────────────────────────────────────────────────────────────────────
# Sentier de la saison (paliers)
# ─────────────────────────────────────────────────────────────────────────────

def sentier_saison(user, points=None):
    """Paliers de la saison, chacun avec son état vis-à-vis de la joueuse.

    Les seuils se lisent en CP d'atelier — la même unité que la barre de
    progression de la carte : franchir un niveau ouvre un coffre.

    état ∈ {reclame, pret, verrouille} — c'est ce qui décide du rendu du
    « sentier » (37a) : coche verte, carte dorée « Ouvrir mon cadeau », ou
    pastille grise.
    """
    saison = saison_active()
    if not saison:
        return []
    points = points_atelier(user) if points is None else points
    reclames = set(
        PalierReclame.objects.filter(utilisateur=user, palier__saison=saison)
        .values_list('palier_id', flat=True)
    )

    # Les coffres s'ouvrent dans l'ordre : un seul palier est « prêt » à la
    # fois, même si les CP en ont débloqué plusieurs d'un coup. Sans cela le
    # sentier afficherait deux cartes dorées « Ouvrir mon cadeau » côte à côte.
    lignes = []
    deja_pret = False
    for palier in saison.paliers.select_related('patron', 'ecusson'):
        if palier.id in reclames:
            etat = 'reclame'
        elif points >= palier.points_requis and not deja_pret:
            etat = 'pret'
            deja_pret = True
        else:
            etat = 'verrouille'
        lignes.append({'palier': palier, 'etat': etat,
                       'points_manquants': max(0, palier.points_requis - points),
                       'atteint': points >= palier.points_requis})
    return lignes


def palier_a_reclamer(user):
    """Premier palier atteint mais pas encore ouvert (la carte dorée du 37a)."""
    for ligne in sentier_saison(user):
        if ligne['etat'] == 'pret':
            return ligne['palier']
    return None


@transaction.atomic
def reclamer_palier(user, palier):
    """Ouvre un coffre de palier : verse pièces, gels, patron et écusson.

    Retourne la liste des récompenses pour l'écran 45d, ou None si le palier
    était déjà ouvert / pas encore atteint.
    """
    if points_atelier(user) < palier.points_requis:
        return None
    _, cree = PalierReclame.objects.get_or_create(utilisateur=user, palier=palier)
    if not cree:
        return None

    # Les récompenses sont volontairement sérialisables (aucun objet modèle) :
    # elles transitent par la session entre le POST qui ouvre le coffre et le
    # GET qui l'annonce.
    recompenses = []
    if palier.pieces:
        crediter_pieces(user, palier.pieces, f"Coffre · palier {palier.numero}", 'coffre')
        recompenses.append({
            'type': 'pieces', 'titre': f"+{palier.pieces} pièces",
            'detail': f"Total : {user.soldePieces} pièces",
        })
    if palier.gels:
        profil = profil_de(user)
        profil.gels += palier.gels
        profil.save(update_fields=['gels'])
        recompenses.append({
            'type': 'gel',
            'titre': f"+{palier.gels} gel{'s' if palier.gels > 1 else ''} de série",
            'detail': f"Tu en as {profil.gels} en réserve",
        })
    if palier.patron:
        recompenses.append({
            'type': 'patron', 'titre': f"Patron « {palier.patron.titre} »",
            'detail': "Ajouté à ta bibliothèque",
        })
    if palier.ecusson:
        EcussonObtenu.objects.get_or_create(utilisateur=user, ecusson=palier.ecusson)
        recompenses.append({
            'type': 'ecusson', 'titre': f"Écusson « {palier.ecusson.nom} »",
            'detail': "Cousu sur ta carte d'atelier",
            'icone': palier.ecusson.icone,
            'couleur_haut': palier.ecusson.couleur_haut,
            'couleur_bas': palier.ecusson.couleur_bas,
        })
    return recompenses


# ─────────────────────────────────────────────────────────────────────────────
# Classement / ligue
# ─────────────────────────────────────────────────────────────────────────────

# Nombre de places qui montent d'une ligue, et seuil de descente.
PLACES_PROMOTION = 5
PLACES_MAINTIEN = 5


def classement(user, portee='ligue', limite=None):
    """Lignes de classement pour l'écran 45a et l'aperçu du 37a.

    portee ∈ {'ligue', 'amies', 'quartier', 'ville'} — le podium et le
    surlignage « Toi » se déduisent du rang.
    """
    saison = saison_active()
    if not saison:
        return []

    # Les comptes d'administration ne jouent pas : les laisser dans la ligue
    # gonflerait l'effectif et ajouterait des lignes à 0 XP en bas de tableau.
    qs = (
        ParticipationLigue.objects
        .filter(saison=saison)
        .exclude(utilisateur__is_staff=True)
        .exclude(utilisateur__is_superuser=True)
        .select_related('utilisateur', 'utilisateur__profil_jeu')
    )
    ma_participation = participation_de(user, saison)

    if portee == 'ligue' and ma_participation:
        qs = qs.filter(ligue=ma_participation.ligue)
    elif portee == 'amies':
        ids = set(ids_amies(user)) | {user.pk}
        qs = qs.filter(utilisateur_id__in=ids)
    elif portee in ('quartier', 'ville'):
        profil = profil_de(user)
        champ = 'utilisateur__profil_jeu__quartier' if portee == 'quartier' else 'utilisateur__profil_jeu__ville'
        valeur = profil.quartier if portee == 'quartier' else profil.ville
        qs = qs.filter(**{champ: valeur})

    qs = qs.order_by('-xp_saison', 'utilisateur__username')
    if limite:
        qs = qs[:limite]

    lignes = []
    for rang, participation in enumerate(qs, start=1):
        joueuse = participation.utilisateur
        profil = getattr(joueuse, 'profil_jeu', None)
        lignes.append({
            'rang': rang,
            'utilisateur': joueuse,
            'profil': profil,
            'xp': participation.xp_saison,
            'serie': profil.serie_actuelle if profil else 0,
            'est_moi': joueuse.pk == user.pk,
            'promu': rang <= PLACES_PROMOTION,
            'relegue': False,
        })

    total = len(lignes)
    for ligne in lignes:
        ligne['relegue'] = total > PLACES_MAINTIEN and ligne['rang'] > total - PLACES_MAINTIEN
    return lignes


def mon_rang(user, lignes=None):
    lignes = lignes if lignes is not None else classement(user)
    for ligne in lignes:
        if ligne['est_moi']:
            return ligne
    return None


def ecart_avec_le_dessus(lignes, rang):
    """XP qui séparent la joueuse de la place au-dessus (« 35 XP DE LÉA »)."""
    if rang <= 1 or rang > len(lignes):
        return None
    dessus = lignes[rang - 2]
    return {'xp': max(0, dessus['xp'] - lignes[rang - 1]['xp']),
            'prenom': _prenom(dessus['utilisateur'])}


def _prenom(user):
    return user.first_name or user.username


# ─────────────────────────────────────────────────────────────────────────────
# Amies
# ─────────────────────────────────────────────────────────────────────────────

def ids_amies(user):
    """Identifiants des amies acceptées, dans les deux sens du lien."""
    envoyees = Amitie.objects.filter(de=user, acceptee=True).values_list('vers_id', flat=True)
    recues = Amitie.objects.filter(vers=user, acceptee=True).values_list('de_id', flat=True)
    return set(envoyees) | set(recues)


def amies_de(user):
    return (
        Utilisateur.objects.filter(pk__in=ids_amies(user))
        .select_related('profil_jeu')
        .order_by('first_name', 'username')
    )


def lien_amitie(user, cible):
    """Lien existant entre deux couturières, quel que soit le sens."""
    return (
        Amitie.objects
        .filter(models_q_lien(user, cible))
        .first()
    )


def models_q_lien(user, cible):
    from django.db.models import Q
    return ((Q(de=user) & Q(vers=cible)) | (Q(de=cible) & Q(vers=user)))


def etat_amitie(user, cible):
    """État de la relation vu par `user` : amies / envoyee / recue / aucune."""
    if cible.pk == user.pk:
        return 'moi'
    lien = lien_amitie(user, cible)
    if not lien:
        return 'aucune'
    if lien.acceptee:
        return 'amies'
    return 'envoyee' if lien.de_id == user.pk else 'recue'


def demandes_recues(user):
    """Invitations en attente de réponse de `user`."""
    return (
        Amitie.objects.filter(vers=user, acceptee=False)
        .select_related('de', 'de__profil_jeu')
    )


@transaction.atomic
def inviter_amie(user, cible):
    """Envoie une demande d'amitié, ou accepte celle déjà reçue de `cible`.

    Retourne (amitie, etat) où etat ∈ {envoyee, amies, deja}.
    """
    if cible.pk == user.pk:
        return None, 'moi'

    lien = lien_amitie(user, cible)
    if lien and lien.acceptee:
        return lien, 'deja'

    # Invitation croisée : les deux se sont invitées, on scelle directement.
    if lien and lien.de_id == cible.pk:
        return accepter_amitie(user, lien), 'amies'
    if lien:
        return lien, 'envoyee'

    lien = Amitie.objects.create(de=user, vers=cible, acceptee=False)
    notifier(
        cible, 'amitie_demande',
        f"{_prenom(user)} veut t'ajouter",
        "Accepte pour comparer vos semaines.",
        lien_url='communaute_amies', emetteur=user,
    )
    return lien, 'envoyee'


@transaction.atomic
def accepter_amitie(user, amitie):
    """Accepte une invitation reçue. Sans effet si elle ne vise pas `user`."""
    if amitie.vers_id != user.pk or amitie.acceptee:
        return amitie
    amitie.acceptee = True
    amitie.date_reponse = timezone.now()
    amitie.save(update_fields=['acceptee', 'date_reponse'])
    notifier(
        amitie.de, 'amitie_acceptee',
        f"{_prenom(user)} a accepté ton invitation",
        "Vous apparaissez maintenant dans le même classement.",
        lien_url='communaute', emetteur=user,
    )
    return amitie


def refuser_amitie(user, amitie):
    """Décline une invitation reçue — le lien disparaît, sans notification."""
    if amitie.vers_id == user.pk and not amitie.acceptee:
        amitie.delete()


def chercher_couturieres(user, requete='', limite=20):
    """Recherche par prénom, nom, identifiant ou code d'atelier.

    Sans requête : suggère des couturières du même quartier, puis de la même
    ville — celles qu'on a le plus de chances de croiser à un atelier.
    """
    from django.db.models import Q

    base = (
        Utilisateur.objects
        .exclude(pk=user.pk)
        .exclude(is_staff=True)
        .exclude(is_superuser=True)
        .select_related('profil_jeu')
    )

    requete = (requete or '').strip()
    if requete:
        code = requete.upper().replace(' ', '')
        resultats = base.filter(
            Q(first_name__icontains=requete)
            | Q(last_name__icontains=requete)
            | Q(username__icontains=requete)
            | Q(profil_jeu__code_atelier__iexact=code)
        )
    else:
        profil = profil_de(user)
        deja = ids_amies(user)
        resultats = base.exclude(pk__in=deja).filter(
            Q(profil_jeu__quartier=profil.quartier) | Q(profil_jeu__ville=profil.ville)
        )

    return list(resultats.order_by('first_name', 'username')[:limite])


# ─────────────────────────────────────────────────────────────────────────────
# Salons — création, mentions, messages à pièce jointe
# ─────────────────────────────────────────────────────────────────────────────

# « @Léa », « @Sofia D. », « @thomas.b » : lettres accentuées, points et
# tirets acceptés, en un ou deux mots.
_MENTION = re.compile(r'@([\w.\-]+(?:\s+[\w.\-]+)?)', re.UNICODE)


def salons_visibles(user):
    """Salons ouverts, plus les salons privés dont `user` est membre.

    Les messages privés (`est_mp`) sont exclus : ce sont des salons « prive »
    techniquement, mais ils ont leur propre liste (`salons_mp`) et n'ont rien
    à faire dans « Les salons ».
    """
    from django.db.models import Q
    from .models import Salon

    return (
        Salon.objects
        .filter(Q(membres=user) | ~Q(type_salon='prive'))
        .exclude(est_mp=True)
        .distinct()
    )


# ─────────────────────────────────────────────────────────────────────────────
# Messages privés — salon « prive » à deux, réutilisant le système de salons
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def salon_mp_avec(user, autre):
    """Salon de message privé entre `user` et `autre`, créé au besoin."""
    from .models import Salon

    if autre.pk == user.pk:
        return None

    existant = (
        Salon.objects.filter(est_mp=True, membres=user).filter(membres=autre).first()
    )
    if existant:
        return existant

    salon = Salon.objects.create(
        nom=f"MP {min(user.pk, autre.pk)}-{max(user.pk, autre.pk)}",
        type_salon='prive', est_mp=True, createur=user,
    )
    salon.membres.add(user, autre)
    return salon


def salons_mp(user):
    """Fils de messages privés de `user`, le plus récent en tête."""
    from .models import Salon

    salons = list(
        Salon.objects.filter(est_mp=True, membres=user).prefetch_related('membres')
    )
    aujourdhui = timezone.localdate()
    for salon_obj in salons:
        salon_obj.autre = next(
            (m for m in salon_obj.membres.all() if m.pk != user.pk), None
        )
        if salon_obj.autre is not None:
            profil_autre = getattr(salon_obj.autre, 'profil_jeu', None)
            salon_obj.autre.est_en_ligne = bool(
                profil_autre and profil_autre.derniere_activite == aujourdhui
            )
        salon_obj.dernier = (
            salon_obj.messages.select_related('auteur').order_by('-date_envoi').first()
        )
    salons.sort(
        key=lambda s: s.dernier.date_envoi if s.dernier else s.date_creation,
        reverse=True,
    )
    return [s for s in salons if s.autre is not None]


@transaction.atomic
def creer_salon(user, nom, description='', membres=(), motif='denim'):
    """Ouvre un salon privé et y convie des amies."""
    from .models import Salon

    nom = (nom or '').strip()[:80]
    if not nom:
        return None

    salon = Salon.objects.create(
        nom=nom, description=(description or '').strip()[:200],
        type_salon='prive', motif=motif, createur=user,
    )
    salon.membres.add(user)

    amies = ids_amies(user)
    for membre in membres:
        # On n'ajoute que des amies : un salon privé ne se peuple pas au hasard.
        if membre.pk not in amies:
            continue
        salon.membres.add(membre)
        notifier(
            membre, 'salon', f"{_prenom(user)} t'a ajouté à « {salon.nom} »",
            'Entre dans le salon pour dire bonjour.',
            lien_url='communaute_salon', args=[salon.pk], emetteur=user,
        )
    return salon


def resoudre_mentions(salon, texte):
    """Couturières citées avec « @ » dans `texte`, cherchées parmi les membres.

    La correspondance se fait sur le prénom, le « Prénom N. » affiché et
    l'identifiant — c'est ce que la joueuse voit et peut taper.
    """
    if not texte or '@' not in texte:
        return []

    membres = list(salon.membres.select_related('profil_jeu'))
    index = {}
    for membre in membres:
        for cle in filter(None, {
            (membre.first_name or '').lower(),
            membre.username.lower(),
            f"{membre.first_name} {membre.last_name[:1]}.".lower()
            if membre.first_name and membre.last_name else None,
        }):
            index[cle] = membre

    trouves, vus = [], set()
    for brut in _MENTION.findall(texte):
        candidat = brut.strip().lower()
        # « @Sofia D. tu » : on retente sur le premier mot si l'expression
        # complète ne correspond à personne.
        membre = index.get(candidat) or index.get(candidat.split()[0])
        if membre and membre.pk not in vus:
            vus.add(membre.pk)
            trouves.append(membre)
    return trouves


@transaction.atomic
def publier_message(user, salon, contenu='', type_message='texte', piece=None,
                    motifs=''):
    """Publie un message, résout ses mentions et prévient qui de droit.

    `piece` est l'objet joint ; son type détermine le champ rempli.
    """
    from .models import MessageSalon

    contenu = (contenu or '').strip()
    if not contenu and piece is None and not motifs:
        return None

    salon.membres.add(user)
    message = MessageSalon(
        salon=salon, auteur=user, contenu=contenu,
        type_message=type_message, motifs=motifs,
    )
    if piece is not None:
        champ = {
            'patron': 'patron', 'etape': 'etape', 'tissu': 'vetement',
            'defi_ville': 'defi_ville', 'duel': 'duel', 'troc': 'annonce',
            'evenement': 'evenement', 'ecusson': 'ecusson',
        }.get(type_message)
        if champ:
            setattr(message, champ, piece)
    message.save()

    mentionnees = resoudre_mentions(salon, contenu)
    if mentionnees:
        message.mentions.set(mentionnees)
        for membre in mentionnees:
            notifier(
                membre, 'salon', f"{_prenom(user)} t'a cité dans « {salon.nom} »",
                contenu[:90], lien_url='communaute_salon', args=[salon.pk],
                emetteur=user,
            )

    avancer_quete(user, 'repondre-salon')
    return message


def partageables(user):
    """Ce que `user` peut joindre à un message, prêt pour le sélecteur.

    Le sélecteur se lit en deux temps : on choisit d'abord *un type* de
    widget, puis l'objet précis. Chaque type reçoit donc ici sa propre
    collection, plus un `apercu` — l'objet servant d'exemple dans la galerie,
    pour montrer à quoi la carte ressemblera une fois postée.
    """
    from .models import EvenementCommunaute, Patron, ProgressionProjet, Vetement

    # Les étapes ne se partagent que pour ses propres projets : « l'étape 4 »
    # n'a de sens que si on est en train de la coudre.
    projets = []
    progressions = (
        ProgressionProjet.objects.filter(utilisateur=user)
        .select_related('patron').prefetch_related('patron__etapes')
        .order_by('termine', '-date_derniere_activite')[:6]
    )
    for progression in progressions:
        etapes = list(progression.patron.etapes.all())
        if etapes:
            projets.append({
                'progression': progression,
                'patron': progression.patron,
                'etapes': etapes,
                'numero_courant': progression.etape_actuelle,
            })

    etape = None
    if projets:
        courant = projets[0]
        etape = next((e for e in courant['etapes']
                      if e.numero == courant['numero_courant']), courant['etapes'][0])

    patrons = list(Patron.objects.order_by('-id')[:12])
    tissus = list(Vetement.objects.filter(utilisateur=user).order_by('-id')[:12])
    evenements = list(
        EvenementCommunaute.objects.filter(date_evenement__gte=timezone.localdate())[:8]
    )
    ecussons = list(
        EcussonObtenu.objects.filter(utilisateur=user).select_related('ecusson')[:12]
    )
    amies = list(amies_de(user))[:8]
    defi = defi_ville_actif(user)
    duel = duel_en_cours(user)

    return {
        'patrons': patrons,
        'tissus': tissus,
        'projets': projets,
        'etape': etape,
        'defi': defi,
        'duel': duel,
        'amies': amies,
        'evenements': evenements,
        'ecussons': ecussons,
        # Aperçus de la galerie : le premier élément de chaque famille.
        'apercu': {
            'patron': patrons[0] if patrons else None,
            'tissu': tissus[0] if tissus else None,
            'etape': etape,
            'defi': defi,
            'duel': duel,
            'evenement': evenements[0] if evenements else None,
            'ecusson': ecussons[0].ecusson if ecussons else None,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Réactions aux messages
# ─────────────────────────────────────────────────────────────────────────────

# Jeu fermé, et volontairement court : une réaction doit se choisir d'un coup
# d'œil, et les compteurs n'ont de sens que si tout le monde tape dans la même
# palette. Ordre = ordre d'affichage de la palette.
EMOJIS = ['❤️', '🔥', '👏', '💡', '😮', '🪡']


@transaction.atomic
def basculer_reaction(user, message, emoji):
    """Pose ou retire la réaction `emoji` de `user` sur `message`.

    Retourne True si la réaction a été posée, False si elle a été retirée,
    None si l'émoji n'appartient pas à la palette.
    """
    from .models import ReactionMessage

    if emoji not in EMOJIS:
        return None

    reaction = ReactionMessage.objects.filter(
        message=message, utilisateur=user, emoji=emoji).first()
    if reaction:
        reaction.delete()
        return False

    ReactionMessage.objects.create(message=message, utilisateur=user, emoji=emoji)
    # L'autrice du message est prévenue de la première réaction d'une personne,
    # pas de chaque émoji : sinon un message applaudi devient un flot d'alertes.
    if not ReactionMessage.objects.filter(
            message=message, utilisateur=user).exclude(emoji=emoji).exists():
        notifier(
            message.auteur, 'salon',
            f"{_prenom(user)} a réagi {emoji}",
            (message.contenu or 'Ton message')[:90],
            lien_url='communaute_salon', args=[message.salon_id], emetteur=user,
        )
    return True


def reactions_par_message(messages, user):
    """Regroupe les réactions d'une liste de messages, prêtes à l'affichage.

    Retourne ``{id_message: [{emoji, nombre, par_moi, noms}]}`` — les émojis
    sont rendus dans l'ordre de la palette, pour que la même réaction reste à
    la même place d'un message à l'autre.
    """
    from .models import ReactionMessage

    ids = [m.pk for m in messages]
    if not ids:
        return {}

    groupes = {}
    lignes = (
        ReactionMessage.objects
        .filter(message_id__in=ids)
        .select_related('utilisateur')
    )
    for reaction in lignes:
        seau = groupes.setdefault(reaction.message_id, {})
        entree = seau.setdefault(reaction.emoji, {'emoji': reaction.emoji, 'nombre': 0,
                                                  'par_moi': False, 'noms': []})
        entree['nombre'] += 1
        entree['noms'].append(_prenom(reaction.utilisateur))
        if reaction.utilisateur_id == user.pk:
            entree['par_moi'] = True

    rang = {emoji: i for i, emoji in enumerate(EMOJIS)}
    return {
        cle: sorted(seau.values(), key=lambda e: rang.get(e['emoji'], 99))
        for cle, seau in groupes.items()
    }


# ─────────────────────────────────────────────────────────────────────────────
# Notifications
# ─────────────────────────────────────────────────────────────────────────────

def notifier(destinataire, type_notif, titre, detail='', lien_url='', emetteur=None,
             args=None):
    """Dépose une notification. `lien_url` est un nom d'URL Django.

    Ne notifie jamais quelqu'un de sa propre action : sans ce garde-fou, on se
    verrait annoncer ses propres réponses ou ses propres invitations.
    """
    from django.urls import NoReverseMatch, reverse

    if emetteur is not None and emetteur.pk == destinataire.pk:
        return None

    lien = ''
    if lien_url:
        try:
            lien = reverse(lien_url, args=args or [])
        except NoReverseMatch:
            lien = lien_url

    return Notification.objects.create(
        destinataire=destinataire, type_notif=type_notif, titre=titre,
        detail=detail, lien=lien, emetteur=emetteur,
    )


def notifications_de(user, limite=20):
    return list(user.notifications.select_related('emetteur')[:limite])


def nb_notifications_non_lues(user):
    return user.notifications.filter(lue=False).count()


def marquer_notifications_lues(user):
    return user.notifications.filter(lue=False).update(lue=True)


# ─────────────────────────────────────────────────────────────────────────────
# Duels
# ─────────────────────────────────────────────────────────────────────────────

def duel_en_cours(user):
    """Duel actif de la joueuse (le plus récent si plusieurs)."""
    maintenant = timezone.now()
    return (
        Duel.objects.filter(statut='en_cours', date_fin__gt=maintenant)
        .filter(models_q_joueuse(user))
        .select_related('joueuse_a', 'joueuse_b')
        .first()
    )


def models_q_joueuse(user):
    from django.db.models import Q
    return Q(joueuse_a=user) | Q(joueuse_b=user)


def creer_duel(user, adversaire, duree_heures=24, mise=20, xp=60):
    """Lance un duel express contre une amie, et l'en avertit."""
    duel = Duel.objects.create(
        joueuse_a=user, joueuse_b=adversaire,
        mise_pieces=mise, xp_gain=xp,
        date_fin=timezone.now() + timedelta(hours=duree_heures),
    )
    notifier(
        adversaire, 'duel',
        f"{_prenom(user)} t'a défié",
        f"{duree_heures} h pour coudre le plus de pièces.",
        lien_url='communaute_duel', args=[duel.pk], emetteur=user,
    )
    return duel


# ─────────────────────────────────────────────────────────────────────────────
# Écussons
# ─────────────────────────────────────────────────────────────────────────────

def verifier_ecussons(user):
    """Attribue les écussons dont la condition est désormais remplie.

    Les conditions sont volontairement simples et lisibles : elles se lisent
    depuis l'état du profil et de la participation, sans table de règles.
    """
    profil = profil_de(user)
    niveau = niveau_de(user)['numero']
    participation = participation_de(user)

    from .models import Vetement, ProgressionProjet

    acquis = {
        'braise-or': profil.serie_record >= 30,
        'eclair': Duel.objects.filter(models_q_joueuse(user), statut='termine').count() >= 10,
        'toile': Vetement.objects.filter(utilisateur=user).count() >= 10,
        'bobine': ProgressionProjet.objects.filter(utilisateur=user, termine=True).count() >= 3,
        'etoile': ProgressionProjet.objects.filter(utilisateur=user, termine=True).count() >= 5,
        'diamant': niveau >= NIVEAU_MAX,
        'mentor': user.reponses_entraide.filter(validee=True).count() >= 3,
        'ruban': bool(participation and participation.xp_saison >= 1000),
    }

    nouveaux = []
    deja = set(EcussonObtenu.objects.filter(utilisateur=user).values_list('ecusson__code', flat=True))
    for code, obtenu in acquis.items():
        if not obtenu or code in deja:
            continue
        ecusson = Ecusson.objects.filter(code=code).first()
        if ecusson:
            EcussonObtenu.objects.get_or_create(utilisateur=user, ecusson=ecusson)
            nouveaux.append(ecusson)
    return nouveaux


# Condition de chaque écusson auto-attribué (voir `verifier_ecussons`),
# exprimée en (valeur atteinte, valeur cible) pour dessiner l'anneau de
# progression des cases « en cours ». Les écussons hors de cette liste
# (offerts par un palier, achetés, ou secrets) n'ont pas d'anneau : rien ne
# permet d'en mesurer l'avancement d'un coup d'œil.
def _progres_ecussons(user):
    from .models import ProgressionProjet, Vetement

    profil = profil_de(user)
    niveau = niveau_de(user)['numero']
    participation = participation_de(user)

    return {
        'braise-or': (profil.serie_record, 30),
        'eclair': (Duel.objects.filter(models_q_joueuse(user), statut='termine').count(), 10),
        'toile': (Vetement.objects.filter(utilisateur=user).count(), 10),
        'bobine': (ProgressionProjet.objects.filter(utilisateur=user, termine=True).count(), 3),
        'etoile': (ProgressionProjet.objects.filter(utilisateur=user, termine=True).count(), 5),
        'diamant': (niveau, NIVEAU_MAX),
        'mentor': (user.reponses_entraide.filter(validee=True).count(), 3),
        'ruban': (participation.xp_saison if participation else 0, 1000),
    }


def collection_ecussons(user):
    """Catalogue complet, marqué obtenu / à débloquer, groupé par catégorie."""
    obtenus = {
        eo.ecusson_id: eo
        for eo in EcussonObtenu.objects.filter(utilisateur=user).select_related('ecusson')
    }
    progres = _progres_ecussons(user)
    groupes = []
    for code, libelle in Ecusson.CATEGORIES:
        items = []
        for ecusson in Ecusson.objects.filter(categorie=code):
            atteint, cible = progres.get(ecusson.code, (0, 0))
            pct = min(100, round(atteint / cible * 100)) if cible else None
            items.append({'ecusson': ecusson, 'obtenu': ecusson.id in obtenus,
                          'date': obtenus[ecusson.id].date_obtention if ecusson.id in obtenus else None,
                          'progres_pct': pct})
        if items:
            groupes.append({'code': code, 'libelle': libelle.upper(), 'items': items})

    total = Ecusson.objects.count()
    return {
        'groupes': groupes,
        'nb_obtenus': len(obtenus),
        'nb_restants': max(0, total - len(obtenus)),
        'total': total,
        'pourcentage': round(len(obtenus) / total * 100) if total else 0,
        'par_rang': _repartition_par_rang(obtenus.values()),
        'dernier': (EcussonObtenu.objects.filter(utilisateur=user)
                    .select_related('ecusson').first()),
    }


def _repartition_par_rang(obtentions):
    """« 3 OR · 2 LAINE · 4 TOILE » — compte des écussons obtenus par rang."""
    comptes = {}
    for obtention in obtentions:
        comptes[obtention.ecusson.rang] = comptes.get(obtention.ecusson.rang, 0) + 1
    libelles = dict(Ecusson.RANGS)
    return [
        {'libelle': libelles[code].upper(), 'nombre': comptes[code]}
        for code, _ in Ecusson.RANGS if comptes.get(code)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Défi de ville
# ─────────────────────────────────────────────────────────────────────────────

def defi_ville_actif(user):
    profil = profil_de(user)
    return DefiVille.objects.filter(actif=True, ville=profil.ville).first() or \
        DefiVille.objects.filter(actif=True).first()


def repartition_quartiers(defi, limite=3):
    """m² par quartier, du plus fourni au moins fourni (cartes du 37a)."""
    if not defi:
        return []
    totaux = {}
    for contribution in defi.contributions.all():
        totaux[contribution.quartier] = totaux.get(contribution.quartier, 0.0) + contribution.m2
    if not totaux:
        return []
    maxi = max(totaux.values()) or 1
    lignes = [
        {'quartier': quartier, 'm2': round(m2, 1), 'pourcentage': round(m2 / maxi * 100)}
        for quartier, m2 in sorted(totaux.items(), key=lambda kv: -kv[1])
    ]
    return lignes[:limite]


def ma_contribution(defi, user):
    if not defi:
        return 0.0
    contribution = defi.contributions.filter(utilisateur=user).first()
    return round(contribution.m2, 1) if contribution else 0.0


# Le défi bascule d'un cap à l'autre : on ne prévient qu'une fois par cap.
CAPS_DEFI = (25, 50, 75, 100)


@transaction.atomic
def declarer_m2(user, defi, surface, commentaire=''):
    """Enregistre une surface sauvée : journal, cumuls, XP, notifications.

    Retourne un dict de ce qui s'est passé, pour que la vue puisse en rendre
    compte sans refaire les calculs.
    """
    from .models import ContributionDefiVille, DeclarationM2

    surface = round(float(surface), 2)
    if not defi or surface <= 0:
        return None

    profil = profil_de(user)
    avant = defi.total_m2

    DeclarationM2.objects.create(
        defi=defi, utilisateur=user, m2=surface,
        quartier=profil.quartier, commentaire=commentaire.strip()[:140],
    )

    contribution, _ = ContributionDefiVille.objects.get_or_create(
        defi=defi, utilisateur=user, defaults={'quartier': profil.quartier},
    )
    contribution.m2 += surface
    contribution.quartier = profil.quartier
    contribution.save()

    participation = participation_de(user)
    if participation:
        participation.m2_sauves += surface
        participation.save(update_fields=['m2_sauves'])

    # 10 XP par m² : la surface reste l'unité de mesure de l'application.
    xp = int(surface * 10)
    gagner_xp(user, xp, 'Défi de ville')

    apres = defi.total_m2
    cap_franchi = next(
        (cap for cap in CAPS_DEFI
         if avant / defi.objectif_m2 * 100 < cap <= apres / defi.objectif_m2 * 100),
        None,
    ) if defi.objectif_m2 else None

    if cap_franchi:
        notifier(
            user, 'defi',
            f"{defi.ville} passe les {cap_franchi} %",
            f"{apres} m² sur {int(defi.objectif_m2)} m² recousus.",
            lien_url='communaute_defi_ville',
        )

    return {
        'surface': surface,
        'xp': xp,
        'total': apres,
        'ma_part': round(contribution.m2, 1),
        'cap_franchi': cap_franchi,
    }


def classement_quartiers(defi):
    """Tous les quartiers du défi, du plus fourni au moins fourni."""
    if not defi:
        return []
    totaux, participantes = {}, {}
    for contribution in defi.contributions.all():
        totaux[contribution.quartier] = totaux.get(contribution.quartier, 0.0) + contribution.m2
        participantes.setdefault(contribution.quartier, set()).add(contribution.utilisateur_id)

    if not totaux:
        return []
    maxi = max(totaux.values()) or 1
    return [
        {'quartier': quartier, 'm2': round(m2, 1),
         'pourcentage': round(m2 / maxi * 100),
         'part': round(m2 / (defi.total_m2 or 1) * 100),
         'nb': len(participantes.get(quartier, ()))}
        for quartier, m2 in sorted(totaux.items(), key=lambda kv: -kv[1])
    ]


def meilleures_contributrices(defi, limite=5):
    if not defi:
        return []
    return list(
        defi.contributions.select_related('utilisateur', 'utilisateur__profil_jeu')
        .order_by('-m2')[:limite]
    )


def mes_declarations(defi, user, limite=10):
    if not defi:
        return []
    return list(defi.declarations.filter(utilisateur=user)[:limite])


# ─────────────────────────────────────────────────────────────────────────────
# État complet pour la carte d'atelier
# ─────────────────────────────────────────────────────────────────────────────

def etat_joueuse(user):
    """Tout ce qu'affiche la carte d'atelier, commune aux trois onglets."""
    profil = profil_de(user)
    saison = saison_active()
    participation = participation_de(user, saison)
    niveau = niveau_de(user)
    total_ecussons = Ecusson.objects.count()

    jours_restants = None
    if saison:
        jours_restants = max(0, (saison.date_fin - timezone.localdate()).days)

    return {
        'profil': profil,
        'niveau': niveau,
        'saison': saison,
        'saison_jours_restants': jours_restants,
        'participation': participation,
        'pieces': user.soldePieces,
        'nb_ecussons': EcussonObtenu.objects.filter(utilisateur=user).count(),
        'total_ecussons': total_ecussons,
        'serie': profil.serie_actuelle,
        'gels': profil.gels,
        'serie_en_danger': serie_en_danger(profil),
    }

"""Vues de l'onglet Partage (communauté « atelier »).

Découpage des écrans de la maquette :

    37a  onglet Atelier    ─┐
    46a  onglet Amis        ├─ `communaute` (une seule vue, trois onglets)
    46b  onglet Entraide   ─┘

    45a  classement complet      45f  duel en cours
    45b  série plein écran       45g  salon de discussion
    45c  boutique de pièces      45h  fiche d'événement
    45d  ouverture de coffre     45i  quêtes du jour
    45e  collection d'écussons   45j  fin de saison

Les règles du jeu ne sont jamais écrites ici : elles viennent toutes de
``core.gamification``.
"""

from datetime import timedelta

from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import gamification as jeu
from .models import (
    Amitie, AnnonceTroc, DisponibiliteEntraide, Duel, Ecusson, EcussonObtenu,
    EvenementCommunaute, InscriptionEvenement, MessageSalon, OffreBoutique,
    PalierSaison, ParticipationLigue, ProfilJeu, QuestionEntraide,
    ReponseEntraide, Salon, TransactionPieces, Utilisateur,
)


# ─────────────────────────────────────────────────────────────────────────────
# Socle commun aux trois onglets
# ─────────────────────────────────────────────────────────────────────────────

def _socle(request, onglet):
    """Contexte partagé : en-tête de saison, carte d'atelier, onglet actif."""
    contexte = jeu.etat_joueuse(request.user)
    contexte.update({
        'onglet': onglet,
        'nav_active': 'partage',
        'coffre_jour': jeu.coffre_du_jour(request.user),
        'nb_notifications': jeu.nb_notifications_non_lues(request.user),
        'nb_demandes': jeu.demandes_recues(request.user).count(),
        # Pastille du bouton « conversations » : les messages de salon
        # signalés et pas encore lus.
        'nb_messages': request.user.notifications.filter(
            type_notif='salon', lue=False).count(),
    })
    return contexte


@login_required
def communaute(request):
    """Page Partage. `?onglet=` choisit Atelier (défaut), Amis ou Entraide."""
    onglet = request.GET.get('onglet', 'atelier')
    if onglet not in ('atelier', 'amis', 'entraide'):
        onglet = 'atelier'

    contexte = _socle(request, onglet)

    if onglet == 'atelier':
        contexte.update(_contexte_atelier(request))
    elif onglet == 'amis':
        contexte.update(_contexte_amis(request))
    else:
        contexte.update(_contexte_entraide(request))

    return render(request, 'core/communaute.html', contexte)


def _contexte_atelier(request):
    """Onglet Atelier (37a) : sentier de saison, ligue, défi de ville, agenda."""
    user = request.user

    # Le sentier entier est rendu dans une zone qui défile : on voit trois
    # crans à la fois, mais rien n'empêche de remonter le chemin parcouru ou
    # d'aller lorgner les paliers suivants. Le cran courant est marqué pour que
    # la vue s'ouvre dessus.
    sentier = jeu.sentier_saison(user)
    index_courant = next((i for i, l in enumerate(sentier) if l['etat'] == 'pret'), None)
    if index_courant is None:
        index_courant = next((i for i, l in enumerate(sentier) if l['etat'] == 'verrouille'), 0)
    for index, ligne in enumerate(sentier):
        ligne['courant'] = index == index_courant
    nb_reclames = sum(1 for l in sentier if l['etat'] == 'reclame')

    lignes = jeu.classement(user, 'ligue')
    ma_ligne = jeu.mon_rang(user, lignes)
    podium = lignes[:3]
    # Podium visuel : 2ᵉ à gauche, 1ʳᵉ au centre, 3ᵉ à droite.
    podium_ordonne = []
    if len(podium) >= 2:
        podium_ordonne.append(podium[1])
    if podium:
        podium_ordonne.append(podium[0])
    if len(podium) >= 3:
        podium_ordonne.append(podium[2])

    xp_maxi = lignes[0]['xp'] if lignes else 1
    for ligne in lignes:
        ligne['largeur'] = max(12, round(ligne['xp'] / (xp_maxi or 1) * 100))

    defi = jeu.defi_ville_actif(user)
    # Compté ici : `timeuntil` en gabarit produit « 5 jours, 3 heures », que
    # `truncatewords` abîmerait en « 5 … » dans la pastille « J-6 ».
    defi_jours = max(0, (defi.date_fin - timezone.localdate()).days) if defi else None

    filtre_agenda = request.GET.get('agenda', 'tout')
    evenements = EvenementCommunaute.objects.filter(
        date_evenement__gte=timezone.localdate()
    ).annotate(nb_inscrites=Count('participants'))
    if filtre_agenda == 'en_ligne':
        evenements = evenements.filter(format_evenement='en_ligne')
    elif filtre_agenda == 'pres':
        evenements = evenements.filter(distance_km__isnull=False).order_by('distance_km')
    elif filtre_agenda == 'mes':
        evenements = evenements.filter(participants=user)
    evenements = list(evenements[:8])

    mes_inscriptions = set(
        InscriptionEvenement.objects.filter(utilisateur=user)
        .values_list('evenement_id', flat=True)
    )
    for evenement in evenements:
        evenement.est_inscrite = evenement.id in mes_inscriptions

    saison = jeu.saison_active()
    fin_ligue = None
    if saison:
        fin_ligue = max(0, (saison.date_fin - timezone.localdate()).days)

    return {
        'sentier': sentier,
        'nb_paliers': len(sentier),
        'nb_paliers_reclames': nb_reclames,
        'pourcentage_paliers': round(nb_reclames / len(sentier) * 100) if sentier else 0,
        'classement': lignes[:6],
        'podium': podium_ordonne,
        'ma_ligne': ma_ligne,
        'nb_joueuses': len(lignes),
        'fin_ligue_jours': fin_ligue,
        'defi_ville': defi,
        'defi_jours': defi_jours,
        'quartiers': jeu.repartition_quartiers(defi),
        'ma_part_m2': jeu.ma_contribution(defi, user),
        'evenements': evenements,
        'nb_evenements': EvenementCommunaute.objects.filter(
            date_evenement__gte=timezone.localdate()).count(),
        'nb_mes_evenements': len(mes_inscriptions),
        'filtre_agenda': filtre_agenda,
    }


def _contexte_amis(request):
    """Onglet Amis (46a) : parrainage, duel, classement entre amies, troc."""
    user = request.user
    profil = jeu.profil_de(user)

    duel = jeu.duel_en_cours(user)
    contexte_duel = None
    if duel:
        mon_score, son_score = duel.scores_pour(user)
        maxi = max(mon_score, son_score, 1)
        contexte_duel = {
            'duel': duel,
            'adversaire': duel.adversaire_de(user),
            'mon_score': mon_score,
            'son_score': son_score,
            'ma_barre': round(mon_score / maxi * 100),
            'sa_barre': round(son_score / maxi * 100),
            'heures_restantes': max(0, int((duel.date_fin - timezone.now()).total_seconds() // 3600)),
        }

    # Rail des amies : les plus actives d'abord (série, puis prénom), pour que
    # les comptes endormis ne monopolisent pas la première vue du rail.
    amies = sorted(
        jeu.amies_de(user),
        key=lambda a: (-getattr(getattr(a, 'profil_jeu', None), 'serie_actuelle', 0),
                       (a.first_name or a.username).lower()),
    )
    for amie in amies:
        amie.est_en_ligne = _en_ligne(amie)

    # Amies encore libres pour un défi express : celles sans duel en cours.
    # Les mieux classées d'abord — c'est contre elles qu'on veut se mesurer.
    en_duel = {
        d.adversaire_de(user).pk
        for d in Duel.objects.filter(jeu.models_q_joueuse(user), statut='en_cours')
    }
    xp_par_amie = dict(
        ParticipationLigue.objects
        .filter(saison=jeu.saison_active(), utilisateur__in=amies)
        .values_list('utilisateur_id', 'xp_saison')
    )
    defiables = sorted(
        (a for a in amies if a.pk not in en_duel),
        key=lambda a: -xp_par_amie.get(a.pk, 0),
    )[:6]

    periode = request.GET.get('periode', 'semaine')
    lignes_amies = jeu.classement(user, 'amies')

    annonces = (
        AnnonceTroc.objects.filter(statut='ouverte')
        .exclude(auteur=user)
        .select_related('auteur')[:6]
    )
    mes_annonces = AnnonceTroc.objects.filter(auteur=user, statut='ouverte').count()

    return {
        'code_atelier': profil.code_atelier,
        'contexte_duel': contexte_duel,
        'amies': amies,
        'nb_amies': len(amies),
        'nb_amies_en_ligne': sum(1 for a in amies if _en_ligne(a)),
        'amies_defiables': defiables,
        'classement_amies': lignes_amies,
        'periode': periode,
        'annonces': list(annonces),
        'mes_annonces': mes_annonces,
    }


# Questions affichées d'emblée dans l'onglet Entraide ; « Voir + » en ajoute
# autant à chaque fois.
QUESTIONS_PAR_PAGE = 4


def _decorer_questions(questions):
    """Ajoute à chaque question l'ancienneté et sa meilleure réponse."""
    for question in questions:
        question.minutes = max(
            1, int((timezone.now() - question.date_creation).total_seconds() // 60))
        question.reponse_top = question.reponses.select_related('auteur').first()
    return questions


def _contexte_entraide(request):
    """Onglet Entraide (46b) : mes questions, celles des autres, entraide."""
    user = request.user
    filtre = request.GET.get('filtre', 'tout')

    # « Voir + » agrandit la liste au lieu de paginer : on reste sur la page,
    # et le lien reste partageable.
    try:
        limite = max(QUESTIONS_PAR_PAGE, int(request.GET.get('questions', QUESTIONS_PAR_PAGE)))
    except (TypeError, ValueError):
        limite = QUESTIONS_PAR_PAGE

    mes_questions = _decorer_questions(list(
        QuestionEntraide.objects.filter(auteur=user)
        .select_related('auteur').annotate(nb_rep=Count('reponses'))[:5]
    ))

    # Le fil principal ne montre que les questions des autres : les siennes
    # ont leur propre section, les y répéter n'apprendrait rien.
    questions = (
        QuestionEntraide.objects.exclude(auteur=user)
        .select_related('auteur').annotate(nb_rep=Count('reponses'))
    )
    if filtre == 'sans_reponse':
        questions = questions.filter(nb_rep=0)
    elif filtre in ('denim', 'machine'):
        questions = questions.filter(tags__icontains=filtre)
    elif filtre == 'pres':
        profil = jeu.profil_de(user)
        questions = questions.filter(auteur__profil_jeu__ville=profil.ville)

    total_filtre = questions.count()
    questions = _decorer_questions(list(questions[:limite]))

    dispos = (
        DisponibiliteEntraide.objects.filter(en_ligne=True)
        .exclude(utilisateur=user)
        .select_related('utilisateur', 'utilisateur__profil_jeu')[:6]
    )
    dispos_data = []
    for dispo in dispos:
        niveau = jeu.niveau_de(dispo.utilisateur)
        dispos_data.append({'dispo': dispo, 'niveau': niveau['numero']})

    salon_sos = Salon.objects.filter(type_salon='sos').first()

    return {
        'mes_questions': mes_questions,
        'nb_mes_questions': QuestionEntraide.objects.filter(auteur=user).count(),
        'questions': questions,
        'nb_questions': QuestionEntraide.objects.exclude(auteur=user).count(),
        'nb_sans_reponse': QuestionEntraide.objects.exclude(auteur=user)
                                                   .annotate(n=Count('reponses'))
                                                   .filter(n=0).count(),
        'filtre_entraide': filtre,
        'limite_questions': limite,
        'reste_questions': max(0, total_filtre - len(questions)),
        'prochaine_limite': limite + QUESTIONS_PAR_PAGE,
        'dispos': dispos_data,
        'salon_sos': salon_sos,
        'nb_sos_en_ligne': DisponibiliteEntraide.objects.filter(en_ligne=True).count(),
        'mes_salons': list(jeu.salons_visibles(user).filter(membres=user)[:4]),
    }


def _en_ligne(utilisateur):
    """Heuristique d'activité : une activité aujourd'hui = « en ligne »."""
    profil = getattr(utilisateur, 'profil_jeu', None)
    return bool(profil and profil.derniere_activite == timezone.localdate())


# ─────────────────────────────────────────────────────────────────────────────
# Progression — échelle des niveaux et célébration de montée
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def progression(request):
    """Écran plein de la progression : d'où viennent les CP, où ils mènent."""
    niveau = jeu.niveau_de(request.user)
    montee = jeu.montee_de_niveau(request.user, niveau)
    sentier = jeu.sentier_saison(request.user, niveau['points'])

    return render(request, 'core/communaute_progression.html', {
        'nav_active': 'partage',
        'niveau': niveau,
        'echelle': jeu.echelle_niveaux(request.user, niveau),
        'detail': jeu.detail_points(request.user),
        'palier_pret': next((l for l in sentier if l['etat'] == 'pret'), None),
        'palier_suivant': next((l for l in sentier if l['etat'] == 'verrouille'), None),
        # Une montée jamais fêtée déclenche la célébration à l'ouverture.
        'celebrer': montee is not None,
    })


@login_required
@require_POST
def progression_vue(request):
    """Referme la célébration : le niveau atteint est marqué comme vu."""
    jeu.marquer_niveau_vu(request.user, jeu.niveau_de(request.user)['numero'])
    return redirect('communaute_progression')


# ─────────────────────────────────────────────────────────────────────────────
# Notifications
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def notifications(request):
    """Feuille des notifications, groupées par jour.

    Les marquer lues à l'ouverture est volontaire : la pastille disparaît dès
    qu'on a regardé, ce qui est le comportement attendu d'un centre de notifs.
    """
    lignes = jeu.notifications_de(request.user, limite=30)
    aujourdhui = timezone.localdate()

    groupes = []
    for notification in lignes:
        jour = timezone.localtime(notification.date_creation).date()
        if jour == aujourdhui:
            libelle = "Aujourd'hui"
        elif (aujourdhui - jour).days == 1:
            libelle = 'Hier'
        else:
            libelle = f"Le {jour:%d/%m}"
        if not groupes or groupes[-1]['libelle'] != libelle:
            groupes.append({'libelle': libelle, 'items': []})
        groupes[-1]['items'].append(notification)

    jeu.marquer_notifications_lues(request.user)

    return render(request, 'core/communaute/_feuille_notifications.html', {
        'groupes': groupes,
        'nb': len(lignes),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Amies — recherche, invitations, profil communautaire
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def amies(request):
    """Chercher des couturières, répondre aux invitations, voir ses amies."""
    requete = (request.GET.get('q') or '').strip()
    resultats = jeu.chercher_couturieres(request.user, requete)

    # Chaque résultat porte l'état de la relation : le bouton en dépend.
    for personne in resultats:
        personne.etat_lien = jeu.etat_amitie(request.user, personne)
        personne.niveau = jeu.niveau_de(personne)['numero']

    return render(request, 'core/communaute_amies.html', {
        'nav_active': 'partage',
        'requete': requete,
        'resultats': resultats,
        'demandes': jeu.demandes_recues(request.user),
        'amies': list(jeu.amies_de(request.user)),
        'code_atelier': jeu.profil_de(request.user).code_atelier,
    })


@login_required
@require_POST
def inviter_amie(request, pk):
    cible = get_object_or_404(Utilisateur, pk=pk)
    jeu.inviter_amie(request.user, cible)
    return redirect(request.POST.get('retour') or 'communaute_amies')


@login_required
@require_POST
def repondre_amitie(request, pk):
    """Accepte ou décline une invitation reçue."""
    amitie = get_object_or_404(Amitie, pk=pk, vers=request.user)
    if request.POST.get('reponse') == 'accepter':
        jeu.accepter_amitie(request.user, amitie)
    else:
        jeu.refuser_amitie(request.user, amitie)
    return redirect(request.POST.get('retour') or 'communaute_amies')


@login_required
def profil_couturiere(request, pk):
    """Fiche communautaire d'une couturière : niveau, série, écussons, duels."""
    personne = get_object_or_404(
        Utilisateur.objects.select_related('profil_jeu'), pk=pk
    )
    if personne.pk == request.user.pk:
        return redirect('communaute_progression')

    profil = jeu.profil_de(personne)
    participation = jeu.participation_de(personne)
    lignes = jeu.classement(request.user, 'ligue')
    rang = next((l['rang'] for l in lignes if l['utilisateur'].pk == personne.pk), None)

    duel = next(
        (d for d in Duel.objects.filter(statut='en_cours').filter(
            jeu.models_q_joueuse(request.user))
         if d.adversaire_de(request.user).pk == personne.pk),
        None,
    )

    return render(request, 'core/communaute_profil.html', {
        'nav_active': 'partage',
        'personne': personne,
        'profil': profil,
        'niveau': jeu.niveau_de(personne),
        'participation': participation,
        'rang': rang,
        'etat_lien': jeu.etat_amitie(request.user, personne),
        'lien': jeu.lien_amitie(request.user, personne),
        'duel': duel,
        'ecussons': EcussonObtenu.objects.filter(utilisateur=personne)
                                        .select_related('ecusson')[:8],
        'nb_ecussons': EcussonObtenu.objects.filter(utilisateur=personne).count(),
        'total_ecussons': Ecusson.objects.count(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 45a · Classement complet
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def classement_complet(request):
    portee = request.GET.get('portee', 'ligue')
    if portee not in ('ligue', 'amies', 'quartier', 'ville'):
        portee = 'ligue'

    lignes = jeu.classement(request.user, portee)
    ma_ligne = jeu.mon_rang(request.user, lignes)
    ecart = jeu.ecart_avec_le_dessus(lignes, ma_ligne['rang']) if ma_ligne else None

    participation = jeu.participation_de(request.user)
    saison = jeu.saison_active()
    reste = None
    if saison:
        # Compte à rebours réel jusqu'à la fin de la saison, à minuit.
        fin = timezone.make_aware(
            timezone.datetime.combine(saison.date_fin, timezone.datetime.min.time())
        )
        restant = fin - timezone.now()
        if restant.total_seconds() > 0:
            reste = {'jours': restant.days,
                     'heures': restant.seconds // 3600}

    return render(request, 'core/communaute_classement.html', {
        'nav_active': 'partage',
        'lignes': lignes,
        'ma_ligne': ma_ligne,
        'ecart': ecart,
        'portee': portee,
        'participation': participation,
        'nom_ligue': participation.get_ligue_display() if participation else 'Ligue Or',
        'ligue_suivante': participation.ligue_suivante_nom if participation else 'Platine',
        'nb_joueuses': len(lignes),
        'reste': reste,
        'places_promotion': jeu.PLACES_PROMOTION,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 45b · Série plein écran
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def serie(request):
    profil = jeu.profil_de(request.user)
    cases = jeu.calendrier_semaine(profil)
    faits = sum(1 for c in cases if c['etat'] == 'fait')

    # Prochain écusson de série : le premier palier de jours non atteint.
    # Chaque palier a son nom, pour ne pas promettre la Braise d'or à
    # quelqu'un qui vise en réalité les sept premiers jours.
    PALIERS_SERIE = [
        (7, 'la Flamme'), (14, 'la Braise'), (30, "la Braise d'or"),
        (60, 'le Foyer'), (100, 'la Forge'),
    ]
    prochain = next(((j, nom) for j, nom in PALIERS_SERIE if profil.serie_record < j), None)

    return render(request, 'core/communaute_serie.html', {
        'nav_active': 'partage',
        'profil': profil,
        'cases': cases,
        'jours_faits': faits,
        'prochain_palier': prochain[0] if prochain else None,
        'prochain_ecusson': prochain[1] if prochain else None,
        'jours_avant_palier': max(0, prochain[0] - profil.serie_actuelle) if prochain else 0,
        'en_danger': jeu.serie_en_danger(profil),
    })


@login_required
@require_POST
def entretenir_serie(request):
    """« Entretenir ma série » : compte la journée d'atelier."""
    profil = jeu.marquer_activite(request.user)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'serie': profil.serie_actuelle, 'record': profil.serie_record})
    return redirect('communaute_serie')


# ─────────────────────────────────────────────────────────────────────────────
# 45c · Boutique de pièces
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def boutique(request):
    categorie = request.GET.get('cat', 'tout')
    offres = OffreBoutique.objects.select_related('patron', 'ecusson')
    if categorie != 'tout':
        offres = offres.filter(categorie=categorie)

    niveau = jeu.niveau_de(request.user)['numero']

    def _decore(offre):
        offre.verrouillee = offre.niveau_requis > niveau
        return offre

    offre_du_jour = OffreBoutique.objects.filter(mise_en_avant=True).first()
    heures_restantes = None
    if offre_du_jour and offre_du_jour.fin_offre:
        heures_restantes = max(0, int((offre_du_jour.fin_offre - timezone.now()).total_seconds() // 3600))

    gagnees_semaine = sum(
        t.montant for t in TransactionPieces.objects.filter(
            utilisateur=request.user, montant__gt=0,
            date_transaction__gte=timezone.now() - timedelta(days=7))
    )

    return render(request, 'core/communaute_boutique.html', {
        'nav_active': 'partage',
        'categorie': categorie,
        'offre_du_jour': _decore(offre_du_jour) if offre_du_jour else None,
        'heures_restantes': heures_restantes,
        'patrons': [_decore(o) for o in offres.filter(categorie='patron')[:6]],
        'gels': [_decore(o) for o in offres.filter(categorie='gel')],
        'ecussons': [_decore(o) for o in offres.filter(categorie='ecusson')],
        'transactions': TransactionPieces.objects.filter(utilisateur=request.user)[:4],
        'pieces_gagnees_semaine': gagnees_semaine,
        'niveau': niveau,
    })


@login_required
@require_POST
def acheter_offre(request, pk):
    offre = get_object_or_404(OffreBoutique, pk=pk)
    niveau = jeu.niveau_de(request.user)['numero']

    if offre.niveau_requis > niveau:
        return _reponse_achat(request, False, f"Niveau {offre.niveau_requis} requis.")

    ok, message = jeu.depenser_pieces(request.user, offre.prix_pieces, offre.nom, 'boutique')
    if not ok:
        return _reponse_achat(request, False, message)

    if offre.quantite_gels:
        profil = jeu.profil_de(request.user)
        profil.gels += offre.quantite_gels
        profil.save(update_fields=['gels'])
    if offre.ecusson:
        EcussonObtenu.objects.get_or_create(utilisateur=request.user, ecusson=offre.ecusson)

    return _reponse_achat(request, True, message)


def _reponse_achat(request, ok, message):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': ok, 'message': message,
                             'solde': request.user.soldePieces}, status=200 if ok else 400)
    return redirect('communaute_boutique')


# ─────────────────────────────────────────────────────────────────────────────
# 45d · Ouverture de coffre
# ─────────────────────────────────────────────────────────────────────────────

# Clé de session où transite le contenu du coffre entre l'ouverture (POST) et
# son annonce (GET) — schéma Post/Redirect/Get : un rafraîchissement de
# l'écran de récompense ne peut donc pas réouvrir un coffre.
CLE_COFFRE = 'communaute_coffre_ouvert'


@login_required
@require_POST
def ouvrir_coffre(request, pk=None):
    """Ouvre un coffre de palier (pk fourni) ou le coffre du jour (sans pk)."""
    user = request.user

    if pk is not None:
        palier = get_object_or_404(PalierSaison, pk=pk)
        recompenses = jeu.reclamer_palier(user, palier)
        if recompenses is None:
            # Déjà ouvert ou pas encore atteint : retour au sentier.
            return redirect('communaute')
        titre = f"PALIER {palier.numero}"
    else:
        coffre = jeu.coffre_du_jour(user)
        if not coffre or coffre.ouvert:
            return redirect('communaute_quetes')
        coffre.ouvert = True
        coffre.date_ouverture = timezone.now()
        coffre.save(update_fields=['ouvert', 'date_ouverture'])
        jeu.crediter_pieces(user, coffre.pieces, "Coffre du jour", 'coffre')
        recompenses = [{
            'type': 'pieces', 'titre': f"+{coffre.pieces} pièces",
            'detail': f"Total : {user.soldePieces} pièces",
        }]
        titre = "COFFRE DU JOUR"

    request.session[CLE_COFFRE] = {'titre': titre, 'recompenses': recompenses}
    return redirect('communaute_coffre_resultat')


@login_required
def coffre_resultat(request):
    """Annonce le contenu du coffre qui vient d'être ouvert.

    Rien en session (accès direct, ou écran déjà vu) : on renvoie au sentier
    plutôt que d'afficher un coffre vide.
    """
    contenu = request.session.pop(CLE_COFFRE, None)
    if not contenu:
        return redirect('communaute')

    return render(request, 'core/communaute_coffre.html', {
        'nav_active': 'partage',
        'recompenses': contenu['recompenses'],
        'titre_palier': contenu['titre'],
        'saison': jeu.saison_active(),
        'prochain': next(
            (l for l in jeu.sentier_saison(request.user) if l['etat'] != 'reclame'), None
        ),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 45e · Collection d'écussons
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def ecussons(request):
    jeu.verifier_ecussons(request.user)
    collection = jeu.collection_ecussons(request.user)

    # Les pastilles de rang comptent TOUTE la collection : elles doivent rester
    # stables quand on filtre l'affichage, d'où le calcul avant le filtrage.
    par_rang = collection['par_rang']

    filtre = request.GET.get('filtre', 'tout')
    if filtre != 'tout':
        for groupe in collection['groupes']:
            if filtre == 'obtenus':
                groupe['items'] = [i for i in groupe['items'] if i['obtenu']]
            elif filtre == 'manquants':
                groupe['items'] = [i for i in groupe['items'] if not i['obtenu']]
            elif filtre == 'or':
                groupe['items'] = [i for i in groupe['items'] if i['ecusson'].rang == 'or']
        collection['groupes'] = [g for g in collection['groupes'] if g['items']]

    return render(request, 'core/communaute_ecussons.html', {
        'nav_active': 'partage',
        'collection': collection,
        'filtre': filtre,
        'par_rang': par_rang,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 45f · Duel en cours
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def duel(request, pk):
    duel_obj = get_object_or_404(
        Duel.objects.select_related('joueuse_a', 'joueuse_b'), pk=pk
    )
    if request.user.pk not in (duel_obj.joueuse_a_id, duel_obj.joueuse_b_id):
        return redirect('communaute')

    mon_score, son_score = duel_obj.scores_pour(request.user)
    maxi = max(mon_score, son_score, 1)
    pieces = duel_obj.pieces_comptees.select_related('utilisateur')

    return render(request, 'core/communaute_duel.html', {
        'nav_active': 'partage',
        'duel': duel_obj,
        'adversaire': duel_obj.adversaire_de(request.user),
        'mon_score': mon_score,
        'son_score': son_score,
        'ma_barre': round(mon_score / maxi * 100),
        'sa_barre': round(son_score / maxi * 100),
        'heures_restantes': max(0, int((duel_obj.date_fin - timezone.now()).total_seconds() // 3600)),
        'pieces_comptees': pieces,
    })


@login_required
@require_POST
def defier(request, pk):
    """Lance un duel express de 24 h contre une amie.

    Lancé depuis un salon (`salon` en POST), le duel s'y annonce aussitôt :
    défier quelqu'un dans le fil et le dire au salon sont le même geste.
    """
    adversaire = get_object_or_404(Utilisateur, pk=pk)
    if adversaire.pk == request.user.pk:
        return redirect('communaute')
    duel_obj = jeu.creer_duel(request.user, adversaire)

    salon_obj = Salon.objects.filter(pk=request.POST.get('salon')).first()
    if salon_obj and salon_obj.membres.filter(pk=request.user.pk).exists():
        jeu.publier_message(
            request.user, salon_obj,
            contenu=f"Je défie {adversaire.first_name or adversaire.username} !",
            type_message='duel', piece=duel_obj,
        )
        return redirect('communaute_salon', pk=salon_obj.pk)

    return redirect('communaute_duel', pk=duel_obj.pk)


# ─────────────────────────────────────────────────────────────────────────────
# 45g · Salon de discussion
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def salon(request, pk):
    salon_obj = get_object_or_404(Salon.objects.prefetch_related('membres'), pk=pk)

    # Un salon privé ne se lit que de l'intérieur.
    if salon_obj.est_prive and not salon_obj.membres.filter(pk=request.user.pk).exists():
        return redirect('communaute_salons')

    messages = list(
        salon_obj.messages
        .select_related('auteur', 'annonce', 'patron', 'etape', 'etape__patron',
                        'vetement', 'defi_ville', 'duel', 'evenement', 'ecusson')
        .prefetch_related('mentions')
        .order_by('date_envoi')[:60]
    )
    # Les réactions sont attachées aux messages plutôt que passées à part : le
    # gabarit boucle déjà sur les messages, il n'a pas à croiser deux listes.
    groupes = jeu.reactions_par_message(messages, request.user)
    for message in messages:
        message.reactions_groupees = groupes.get(message.pk, [])

    membres = list(salon_obj.membres.select_related('profil_jeu')[:12])
    autre = None
    if salon_obj.est_mp:
        autre = next((m for m in membres if m.pk != request.user.pk), None)
        if autre is not None:
            autre.est_en_ligne = _en_ligne(autre)

    return render(request, 'core/communaute_salon.html', {
        'nav_active': 'partage',
        'salon': salon_obj,
        'autre': autre,
        'messages': messages,
        'membres': membres,
        'nb_membres': salon_obj.membres.count(),
        'nb_en_ligne': sum(1 for m in membres if _en_ligne(m)),
        'est_membre': salon_obj.membres.filter(pk=request.user.pk).exists(),
        'emojis': jeu.EMOJIS,
        # Contenu du sélecteur de partage.
        'partage': jeu.partageables(request.user),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Messages privés
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def messages_prives(request):
    """Liste des fils de messages privés (accessible depuis l'onglet Amis)."""
    return render(request, 'core/communaute_messages.html', {
        'nav_active': 'partage',
        'salons': jeu.salons_mp(request.user),
    })


@login_required
@require_POST
def ouvrir_message_prive(request, pk):
    """Ouvre (ou crée) le fil privé avec `pk`, puis y entre directement."""
    autre = get_object_or_404(Utilisateur, pk=pk)
    if autre.pk == request.user.pk:
        return redirect('communaute_messages')
    salon_obj = jeu.salon_mp_avec(request.user, autre)
    return redirect('communaute_salon', pk=salon_obj.pk)


# ─────────────────────────────────────────────────────────────────────────────
# Partage du code d'atelier
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def partager_code(request):
    """Page de partage du code d'atelier — sous-page de l'onglet Amis."""
    profil = jeu.profil_de(request.user)
    return render(request, 'core/communaute_partage_code.html', {
        'nav_active': 'partage',
        'code_atelier': profil.code_atelier,
    })


# Chaque type de partage sait où retrouver son objet : la vue d'envoi n'a pas
# à connaître les modèles un par un.
_PIECES_JOINTES = {
    'patron': ('Patron', None),
    'etape': ('EtapePatron', None),
    'tissu': ('Vetement', 'utilisateur'),      # on ne partage que ses tissus
    'defi_ville': ('DefiVille', None),
    'duel': ('Duel', None),
    'evenement': ('EvenementCommunaute', None),
    'ecusson': ('Ecusson', None),
}


@login_required
@require_POST
def envoyer_message(request, pk):
    """Publie un message : texte simple, ou texte + pièce jointe partagée."""
    salon_obj = get_object_or_404(Salon, pk=pk)
    if salon_obj.est_prive and not salon_obj.membres.filter(pk=request.user.pk).exists():
        return redirect('communaute_salons')

    contenu = (request.POST.get('contenu') or '').strip()
    type_message = request.POST.get('type_message', 'texte')
    if type_message not in dict(MessageSalon.TYPES):
        type_message = 'texte'

    piece = None
    if type_message in _PIECES_JOINTES:
        nom_modele, champ_proprietaire = _PIECES_JOINTES[type_message]
        modele = apps.get_model('core', nom_modele)
        filtres = {'pk': request.POST.get('piece')}
        if champ_proprietaire:
            filtres[champ_proprietaire] = request.user
        piece = modele.objects.filter(**filtres).first()
        # Un écusson n'a pas de propriétaire dans son modèle : l'appartenance
        # se lit dans la table d'obtention. On ne se vante que des siens.
        if piece is not None and type_message == 'ecusson' and not EcussonObtenu.objects.filter(
                utilisateur=request.user, ecusson=piece).exists():
            piece = None
        if piece is None:
            # Pièce introuvable ou pas à soi : on retombe sur un simple texte.
            type_message = 'texte'

    message = jeu.publier_message(
        request.user, salon_obj, contenu=contenu,
        type_message=type_message, piece=piece,
    )
    if message is None:
        return redirect('communaute_salon', pk=pk)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'id': message.id,
            'contenu': message.contenu,
            'heure': timezone.localtime(message.date_envoi).strftime('%H:%M'),
        })
    return redirect('communaute_salon', pk=pk)


@login_required
@require_POST
def reagir_message(request, pk):
    """Pose ou retire une réaction sur un message du salon.

    Le lien de retour porte l'ancre du message : après le POST, on revient
    exactement là où on lisait, et pas en haut du fil.
    """
    message = get_object_or_404(
        MessageSalon.objects.select_related('salon'), pk=pk
    )
    salon_obj = message.salon
    if salon_obj.est_prive and not salon_obj.membres.filter(pk=request.user.pk).exists():
        return redirect('communaute_salons')

    pose = jeu.basculer_reaction(request.user, message, request.POST.get('emoji', ''))

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        groupes = jeu.reactions_par_message([message], request.user)
        return JsonResponse({'pose': pose, 'reactions': groupes.get(message.pk, [])})

    return redirect(f"{reverse('communaute_salon', args=[salon_obj.pk])}#msg-{message.pk}")


@login_required
def creer_salon(request):
    """Ouvre un salon privé et y convie des amies."""
    if request.method == 'POST':
        membres = Utilisateur.objects.filter(
            pk__in=request.POST.getlist('membres')
        )
        salon_obj = jeu.creer_salon(
            request.user,
            nom=request.POST.get('nom', ''),
            description=request.POST.get('description', ''),
            membres=membres,
            motif=request.POST.get('motif', 'denim'),
        )
        if salon_obj:
            return redirect('communaute_salon', pk=salon_obj.pk)

    return render(request, 'core/communaute_creer_salon.html', {
        'nav_active': 'partage',
        'amies': list(jeu.amies_de(request.user)),
        'motifs': ['denim', 'toile', 'lin', 'laine', 'vert'],
    })


# ─────────────────────────────────────────────────────────────────────────────
# 45h · Fiche d'événement
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def evenement(request, pk):
    evenement_obj = get_object_or_404(
        EvenementCommunaute.objects.select_related('animatrice'), pk=pk
    )
    inscription = InscriptionEvenement.objects.filter(
        utilisateur=request.user, evenement=evenement_obj
    ).first()

    inscrites = list(evenement_obj.participants.select_related('profil_jeu')[:12])
    ids_amies = jeu.ids_amies(request.user)
    amies_presentes = [p for p in inscrites if p.pk in ids_amies]

    return render(request, 'core/communaute_evenement.html', {
        'nav_active': 'partage',
        'evenement': evenement_obj,
        'inscription': inscription,
        'est_inscrite': inscription is not None,
        'inscrites': inscrites,
        'nb_inscrites': evenement_obj.participants.count(),
        'amies_presentes': amies_presentes,
        'reste_inscrites': max(0, evenement_obj.participants.count() - 3),
    })


@login_required
@require_POST
def basculer_inscription(request, pk):
    evenement_obj = get_object_or_404(EvenementCommunaute, pk=pk)
    inscription = InscriptionEvenement.objects.filter(
        utilisateur=request.user, evenement=evenement_obj
    ).first()

    if inscription:
        inscription.delete()
        inscrite = False
    else:
        InscriptionEvenement.objects.create(utilisateur=request.user, evenement=evenement_obj)
        inscrite = True

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'inscrite': inscrite,
                             'nb': evenement_obj.participants.count()})
    return redirect('communaute_evenement', pk=pk)


# ─────────────────────────────────────────────────────────────────────────────
# 45i · Quêtes du jour
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def quetes(request):
    user = request.user
    du_jour = jeu.quetes_du_jour(user)
    de_la_semaine = jeu.quetes_de_la_semaine(user)
    faites = sum(1 for q in du_jour if q.terminee)

    # Quête en cours : la première non terminée, mise en avant sur l'écran.
    en_cours = next((q for q in du_jour if not q.terminee), None)

    minuit = timezone.localtime().replace(hour=0, minute=0, second=0) + timedelta(days=1)
    heures_avant_reset = max(0, int((minuit - timezone.localtime()).total_seconds() // 3600))

    return render(request, 'core/communaute_quetes.html', {
        'nav_active': 'partage',
        'quetes_jour': du_jour,
        'quetes_semaine': de_la_semaine,
        'nb_faites': faites,
        'nb_total': len(du_jour),
        'quete_en_cours': en_cours,
        'coffre': jeu.coffre_du_jour(user),
        'restantes': max(0, len(du_jour) - faites),
        'heures_avant_reset': heures_avant_reset,
        'pourcentage': round(faites / len(du_jour) * 100) if du_jour else 0,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 45j · Fin de saison
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def fin_saison(request):
    """Bilan de saison + promotion. Affiché à la clôture d'une saison ou en
    tapant le résumé depuis l'onglet Atelier."""
    saison = jeu.saison_active()
    participation = jeu.participation_de(request.user, saison)
    lignes = jeu.classement(request.user)
    ma_ligne = jeu.mon_rang(request.user, lignes)
    rang = ma_ligne['rang'] if ma_ligne else len(lignes)
    promue = rang <= jeu.PLACES_PROMOTION

    return render(request, 'core/communaute_fin_saison.html', {
        'nav_active': 'partage',
        'saison': saison,
        'participation': participation,
        'rang': rang,
        'nb_joueuses': len(lignes),
        'promue': promue,
        'ligue_atteinte': participation.ligue_suivante_nom if (participation and promue)
        else (participation.get_ligue_display() if participation else 'Ligue Or'),
        'ecusson_saison': Ecusson.objects.filter(code=f'saison-{saison.numero:02d}').first() if saison else None,
    })


@login_required
@require_POST
def reclamer_fin_saison(request):
    """Encaisse le bilan : passage de ligue et remise à zéro des XP de saison."""
    saison = jeu.saison_active()
    participation = jeu.participation_de(request.user, saison)
    if not participation or participation.bilan_vu:
        return redirect('communaute')

    lignes = jeu.classement(request.user)
    ma_ligne = jeu.mon_rang(request.user, lignes)
    if ma_ligne and ma_ligne['rang'] <= jeu.PLACES_PROMOTION:
        suivante = participation.ligue_suivante
        if suivante:
            participation.ligue = suivante
    participation.bilan_vu = True
    participation.save(update_fields=['ligue', 'bilan_vu'])
    return redirect('communaute')


# ─────────────────────────────────────────────────────────────────────────────
# Actions transverses
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def defi_ville(request):
    """Écran complet du défi de ville : avancée, quartiers, contributrices."""
    defi = jeu.defi_ville_actif(request.user)
    if not defi:
        return redirect('communaute')

    profil = jeu.profil_de(request.user)
    quartiers = jeu.classement_quartiers(defi)
    mon_quartier = next(
        (q for q in quartiers if q['quartier'] == profil.quartier), None
    )

    return render(request, 'core/communaute_defi_ville.html', {
        'nav_active': 'partage',
        'defi': defi,
        'jours_restants': max(0, (defi.date_fin - timezone.localdate()).days),
        'quartiers': quartiers,
        'mon_quartier': mon_quartier,
        'rang_quartier': (quartiers.index(mon_quartier) + 1) if mon_quartier else None,
        'contributrices': jeu.meilleures_contributrices(defi),
        'ma_part': jeu.ma_contribution(defi, request.user),
        'mes_declarations': jeu.mes_declarations(defi, request.user),
        'restant': round(max(0, defi.objectif_m2 - defi.total_m2), 1),
        # Surfaces courantes proposées en un tap, pour éviter la saisie.
        'raccourcis': [0.2, 0.5, 1, 2],
    })


@login_required
@require_POST
def declarer_m2(request):
    """« Déclarer mes m² » — saisie libre ou raccourci."""
    defi = jeu.defi_ville_actif(request.user)
    if not defi:
        return redirect('communaute')

    try:
        surface = float((request.POST.get('m2') or '0').replace(',', '.'))
    except ValueError:
        surface = 0.0

    # Garde-fou : au-delà, c'est une faute de frappe, pas une pièce cousue.
    if surface <= 0 or surface > 50:
        return redirect('communaute_defi_ville')

    jeu.declarer_m2(request.user, defi, surface,
                    commentaire=request.POST.get('commentaire', ''))
    return redirect('communaute_defi_ville')


def _retour_onglet(onglet):
    """Redirection vers un onglet précis de la page Partage."""
    return redirect(f"{reverse('communaute')}?onglet={onglet}")


@login_required
@require_POST
def poser_question(request):
    contenu = (request.POST.get('contenu') or '').strip()
    if contenu:
        QuestionEntraide.objects.create(
            auteur=request.user, contenu=contenu,
            tags=(request.POST.get('tags') or '').strip(),
        )
    return _retour_onglet('entraide')


@login_required
def question(request, pk):
    """Fil complet d'une question : la réponse retenue d'abord, puis les autres."""
    question_obj = get_object_or_404(
        QuestionEntraide.objects.select_related('auteur', 'auteur__profil_jeu'), pk=pk
    )
    reponses = list(
        question_obj.reponses.select_related('auteur', 'auteur__profil_jeu')
    )
    for reponse in reponses:
        reponse.niveau = jeu.niveau_de(reponse.auteur)['numero']

    return render(request, 'core/communaute_question.html', {
        'nav_active': 'partage',
        'question': question_obj,
        'reponses': reponses,
        'est_autrice': question_obj.auteur_id == request.user.pk,
        'a_repondu': any(r.auteur_id == request.user.pk for r in reponses),
        'minutes': max(1, int((timezone.now() - question_obj.date_creation).total_seconds() // 60)),
    })


@login_required
@require_POST
def repondre_question(request, pk):
    question_obj = get_object_or_404(QuestionEntraide, pk=pk)
    contenu = (request.POST.get('contenu') or '').strip()
    if contenu:
        ReponseEntraide.objects.create(
            question=question_obj, auteur=request.user, contenu=contenu
        )
        jeu.gagner_xp(request.user, question_obj.xp_gain, "Réponse d'entraide")
        jeu.avancer_quete(request.user, 'aider-couturiere')
        jeu.notifier(
            question_obj.auteur, 'reponse',
            f"{request.user.first_name or request.user.username} a répondu à ta question",
            contenu[:90],
            lien_url='communaute_question', args=[question_obj.pk],
            emetteur=request.user,
        )
    return redirect('communaute_question', pk=pk)


@login_required
@require_POST
def valider_reponse(request, pk):
    """L'autrice de la question retient une réponse — elle clôt le fil."""
    reponse = get_object_or_404(
        ReponseEntraide.objects.select_related('question'), pk=pk
    )
    question_obj = reponse.question
    if question_obj.auteur_id != request.user.pk:
        return redirect('communaute_question', pk=question_obj.pk)

    # Une seule réponse retenue à la fois.
    question_obj.reponses.update(validee=False)
    reponse.validee = True
    reponse.save(update_fields=['validee'])
    question_obj.resolue = True
    question_obj.save(update_fields=['resolue'])

    # Le coup de main est récompensé au moment où il est reconnu utile.
    jeu.crediter_pieces(reponse.auteur, 15, 'Réponse retenue', 'piece')
    jeu.notifier(
        reponse.auteur, 'reponse', 'Ta réponse a été retenue',
        '+15 pièces pour le coup de main.',
        lien_url='communaute_question', args=[question_obj.pk],
        emetteur=request.user,
    )
    return redirect('communaute_question', pk=question_obj.pk)


@login_required
def salons(request):
    """Liste des salons, avec leur dernier message et leur défi coopératif."""
    # Un salon privé n'apparaît que pour ses membres.
    mes_salons = list(
        jeu.salons_visibles(request.user)
        .prefetch_related('membres')
        .annotate(nb_membres=Count('membres', distinct=True))
    )
    ids_miens = set(request.user.salons.values_list('pk', flat=True))

    for salon_obj in mes_salons:
        salon_obj.est_membre = salon_obj.pk in ids_miens
        salon_obj.dernier = (
            salon_obj.messages.select_related('auteur').order_by('-date_envoi').first()
        )

    # Les salons dont on fait partie remontent en tête.
    mes_salons.sort(key=lambda s: (not s.est_membre, s.nom))

    return render(request, 'core/communaute_salons.html', {
        'nav_active': 'partage',
        'salons': mes_salons,
        'nb_miens': len(ids_miens),
    })


@login_required
@require_POST
def rejoindre_salon(request, pk):
    salon_obj = get_object_or_404(Salon, pk=pk)
    salon_obj.membres.add(request.user)
    return redirect('communaute_salon', pk=pk)


@login_required
@require_POST
def prendre_annonce(request, pk):
    """« Je prends » / « J'en ai » sur une annonce de troc."""
    annonce = get_object_or_404(AnnonceTroc, pk=pk)
    if annonce.statut == 'ouverte' and annonce.auteur_id != request.user.pk:
        annonce.statut = 'reservee'
        annonce.preneuse = request.user
        annonce.save(update_fields=['statut', 'preneuse'])
        jeu.gagner_xp(request.user, 20, "Troc de chutes")
    return _retour_onglet('amis')


@login_required
@require_POST
def ajouter_amie(request):
    """Ajout par code d'atelier (« FAB-4821 ») — même flux que la recherche :
    une invitation part, elle n'est pas acceptée d'office."""
    code = (request.POST.get('code') or '').strip().upper()
    profil = ProfilJeu.objects.filter(code_atelier=code).first()
    if profil and profil.utilisateur_id != request.user.pk:
        jeu.inviter_amie(request.user, profil.utilisateur)
        return redirect('communaute_amies')
    return _retour_onglet('amis')

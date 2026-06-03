import base64
import json
import re
import urllib.parse
from io import BytesIO

import qrcode as qrcode_lib

from django.core.files.base import ContentFile
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta
import math

from django.http import HttpResponse, JsonResponse
from core.models import (Vetement, Utilisateur, Patron, EtapePatron, ProgressionProjet, PatronLike,
                         PostCommunaute, LikePost, SauvegardePost, CommentairePost, Suivi, Hashtag, Badge)

BADGE_DEFINITIONS = [
    {'nom': 'Premier Projet',      'emoji': '🏆', 'description': '1er projet terminé',        'condition': 'Terminer 1 projet'},
    {'nom': '5 Projets',           'emoji': '⭐', 'description': 'Créateur confirmé',           'condition': 'Terminer 5 projets'},
    {'nom': '10 Projets',          'emoji': '🥇', 'description': 'Grand créateur',             'condition': 'Terminer 10 projets'},
    {'nom': '1er com',              'emoji': '💬', 'description': 'Actif dans la communauté',   'condition': 'Poster 1 commentaire'},
    {'nom': '5 com',               'emoji': '🗣️', 'description': 'Très bavard !',             'condition': 'Poster 5 commentaires'},
    {'nom': 'Premier Like',        'emoji': '❤️', 'description': 'Soutien de la communauté',  'condition': 'Donner 1 like'},
    {'nom': '10 Likes',            'emoji': '🔥', 'description': 'Fan de la première heure',   'condition': 'Donner 10 likes'},
    {'nom': 'Première Création',   'emoji': '✨', 'description': 'Première création partagée', 'condition': 'Partager 1 création'},
    {'nom': 'Artiste',             'emoji': '🎨', 'description': 'Créateur prolifique',        'condition': 'Partager 5 créations'},
    {'nom': 'Éco Warrior',         'emoji': '🌿', 'description': 'Badge exclusif',             'condition': 'Acheter dans la boutique'},
]


def check_and_award_badges(user):
    nb_projets = ProgressionProjet.objects.filter(utilisateur=user, termine=True).count()
    nb_commentaires = CommentairePost.objects.filter(utilisateur=user).count()
    nb_likes = LikePost.objects.filter(utilisateur=user).count()
    nb_posts = PostCommunaute.objects.filter(utilisateur=user).count()

    to_award = [
        ('Premier Projet',      '🏆', '1er projet terminé',        nb_projets >= 1),
        ('5 Projets',           '⭐', 'Créateur confirmé',           nb_projets >= 5),
        ('10 Projets',          '🥇', 'Grand créateur',             nb_projets >= 10),
        ('1er com',             '💬', 'Actif dans la communauté',   nb_commentaires >= 1),
        ('5 com',              '🗣️', 'Très bavard !',             nb_commentaires >= 5),
        ('Premier Like',        '❤️', 'Soutien de la communauté',  nb_likes >= 1),
        ('10 Likes',            '🔥', 'Fan de la première heure',   nb_likes >= 10),
        ('Première Création',   '✨', 'Première création partagée', nb_posts >= 1),
        ('Artiste',             '🎨', 'Créateur prolifique',        nb_posts >= 5),
    ]

    for nom, emoji, description, condition in to_award:
        if condition:
            Badge.objects.get_or_create(
                utilisateur=user,
                nom=nom,
                defaults={'emoji': emoji, 'description': description},
            )


def home(request):
    context = {
        'user_coins': '1,250'
    }
    return render(request, 'core/index.html', context)


@login_required
def dashboard(request):
    user = request.user
    OBJECTIF_M2 = 15.0

    vetements_user = Vetement.objects.filter(utilisateur=user)
    surface_totale = round(sum(v.surfaceExploitable for v in vetements_user), 2)
    co2_economise = round(sum(calculer_co2_vetement(v) for v in vetements_user), 1)

    surface_pourcentage = min(100, round((surface_totale / OBJECTIF_M2) * 100))
    surface_restante = round(max(0, OBJECTIF_M2 - surface_totale), 1)

    # Projets terminés
    termines_qs = (
        ProgressionProjet.objects
        .filter(utilisateur=user, termine=True)
        .select_related('patron')
        .order_by('-date_derniere_activite')
    )
    projets_termines = []
    nb_etapes_realisees = 0
    for prog in termines_qs:
        p = prog.patron
        total_etapes = p.etapes.count()
        nb_etapes_realisees += total_etapes
        projets_termines.append({
            'titre': p.titre,
            'image': p.photo.url if p.photo else None,
            'difficulte_label': DIFFICULTE_LABELS.get(p.difficulte, str(p.difficulte)),
            'duree': p.duree or '?',
            'date_fin': prog.date_derniere_activite,
            'patron_id': p.pk,
        })

    badges_earned = {b.nom: b for b in Badge.objects.filter(utilisateur=user)}
    has_eco_warrior = 'Éco Warrior' in badges_earned

    nb_projets_badge      = ProgressionProjet.objects.filter(utilisateur=user, termine=True).count()
    nb_commentaires_badge = CommentairePost.objects.filter(utilisateur=user).count()
    nb_likes_badge        = LikePost.objects.filter(utilisateur=user).count()
    nb_posts_badge        = PostCommunaute.objects.filter(utilisateur=user).count()

    BADGE_PROGRESS = {
        'Premier Projet':    (min(nb_projets_badge, 1),          1),
        '5 Projets':         (min(nb_projets_badge, 5),          5),
        '10 Projets':        (min(nb_projets_badge, 10),         10),
        '1er com':            (min(nb_commentaires_badge, 1),     1),
        '5 com':             (min(nb_commentaires_badge, 5),      5),
        'Premier Like':      (min(nb_likes_badge, 1),             1),
        '10 Likes':          (min(nb_likes_badge, 10),            10),
        'Première Création': (min(nb_posts_badge, 1),             1),
        'Artiste':           (min(nb_posts_badge, 5),             5),
        'Éco Warrior':       (1 if has_eco_warrior else 0,        1),
    }

    badges_display = []
    for bd in BADGE_DEFINITIONS:
        earned = badges_earned.get(bd['nom'])
        current, max_val = BADGE_PROGRESS.get(bd['nom'], (0, 1))
        pct = round((current / max_val) * 100) if max_val > 0 else 0
        badges_display.append({
            'nom': bd['nom'],
            'emoji': bd['emoji'],
            'description': bd['description'],
            'condition': bd['condition'],
            'earned': earned is not None,
            'date_obtention': earned.date_obtention if earned else None,
            'progress_current': current,
            'progress_max': max_val,
            'progress_pct': pct,
        })

    context = {
        'surface_totale': surface_totale,
        'surface_objectif': OBJECTIF_M2,
        'surface_pourcentage': surface_pourcentage,
        'surface_restante': surface_restante,
        'credits': user.soldePieces,
        'co2_economise': co2_economise,
        'projets_termines': projets_termines,
        'nb_projets_termines': len(projets_termines),
        'nb_etapes_realisees': nb_etapes_realisees,
        'badges_display': badges_display,
        'has_eco_warrior': has_eco_warrior,
    }
    return render(request, 'core/dashboard.html', context)


@login_required
def acheter_badge(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'}, status=405)

    BADGE_NOM = 'Éco Warrior'
    BADGE_COUT = 10
    user = request.user

    if Badge.objects.filter(utilisateur=user, nom=BADGE_NOM).exists():
        return JsonResponse({'success': False, 'error': 'Badge déjà obtenu'})

    if user.soldePieces < BADGE_COUT:
        return JsonResponse({'success': False, 'error': 'Pas assez de pièces'})

    user.soldePieces -= BADGE_COUT
    user.save()
    Badge.objects.create(
        utilisateur=user,
        nom=BADGE_NOM,
        emoji='🌿',
        description='Badge exclusif affiché sur votre profil',
    )
    return JsonResponse({'success': True, 'nouveau_solde': user.soldePieces})


def calculate_polygon_area(points, width_cm, height_cm):
    """
    Calcule l'aire d'un polygone avec la formule du lacet (Shoelace formula).
    Les points sont des coordonnées relatives (0 à 1).
    """
    if len(points) < 3:
        return 0.0

    real_points = []
    for p in points:
        real_points.append((p['x'] * width_cm, p['y'] * height_cm))

    area = 0.0
    n = len(real_points)
    for i in range(n):
        j = (i + 1) % n
        area += real_points[i][0] * real_points[j][1]
        area -= real_points[j][0] * real_points[i][1]
        
    return abs(area) / 2.0

@login_required
def ajout_textile(request):
    context = {'result_ready': False}

    if request.method == 'POST':
        try:
            damage_sizes = request.POST.getlist('damage_size[]')
            
            coords_str = request.POST.get('polygon_coords', '[]')
            polygon_points = json.loads(coords_str)
            
            calib_str = request.POST.get('calibration_coords', '[]')
            calib_points = json.loads(calib_str)
            
            calib_distance_cm = float(request.POST.get('calibration_distance', 0))
            img_w = float(request.POST.get('image_width', 1))
            img_h = float(request.POST.get('image_height', 1))


            total_defect_area_m2 = 0.0

            for size_str in damage_sizes:
                size_cm = float(size_str)
                total_defect_area_m2 += (size_cm * size_cm) / 10000.0

            if len(polygon_points) >= 3 and len(calib_points) == 2 and calib_distance_cm > 0:
                
                c1_x, c1_y = calib_points[0]['x'] * img_w, calib_points[0]['y'] * img_h
                c2_x, c2_y = calib_points[1]['x'] * img_w, calib_points[1]['y'] * img_h
                
                distance_px = math.sqrt((c2_x - c1_x)**2 + (c2_y - c1_y)**2)
                
                if distance_px == 0:
                    raise ValueError("Points d'étalonnage confondus.")
                
                cm_per_px = calib_distance_cm / distance_px
                
                px_points = [(p['x'] * img_w, p['y'] * img_h) for p in polygon_points]
                
                area_px2 = 0.0
                n = len(px_points)
                for i in range(n):
                    j = (i + 1) % n
                    area_px2 += px_points[i][0] * px_points[j][1]
                    area_px2 -= px_points[j][0] * px_points[i][1]
                area_px2 = abs(area_px2) / 2.0
                
                polygon_area_cm2 = area_px2 * (cm_per_px ** 2)
                polygon_area_m2 = polygon_area_cm2*2 / 10000.0
                
                usable_area_m2 = max(0, polygon_area_m2 - total_defect_area_m2)
                
                percentage = int((usable_area_m2 / polygon_area_m2) * 100) if polygon_area_m2 > 0 else 0
                
                
                # SAUVEGARDE DANS LA BASE DE DONNÉES
                
                type_vetement = request.POST.get('clothing_type', 'inconnu')
                largeur_cm = float(request.POST.get('width', 0))
                hauteur_cm = float(request.POST.get('height', 0))
                nom_vetement = request.POST.get('nom_vetement', '').strip() or f"{type_vetement.capitalize()} de {request.user.username}"
                qualite = int(request.POST.get('qualite', 3))
                couleur = request.POST.get('couleur', '')
                matiere_raw = request.POST.get('material', 'coton:100').strip() or 'coton:100'

                photo_fichier = None
                photo_data = request.POST.get('photo_data', '')
                if photo_data and ';base64,' in photo_data:
                    fmt, imgstr = photo_data.split(';base64,')
                    ext = fmt.split('/')[-1]
                    photo_fichier = ContentFile(base64.b64decode(imgstr), name=f'vetement.{ext}')

                nouveau_vetement = Vetement.objects.create(
                    utilisateur=request.user,
                    nomVetement=nom_vetement,
                    photoURL=photo_fichier,
                    typeVetement=type_vetement,
                    largeur=largeur_cm,
                    hauteur=hauteur_cm,
                    surfaceTotale=polygon_area_m2,
                    surfaceTaches=total_defect_area_m2,
                    surfaceTrous=0.0,
                    surfaceExploitable=usable_area_m2,
                    etat="À transformer",
                    qualite=qualite,
                    couleur=couleur,
                    matiere=matiere_raw,
                )

                coins_earned = 3
                request.user.soldePieces += coins_earned
                request.user.save()

                context.update({
                    'result_ready': True,
                    'usable_area': round(usable_area_m2, 2),
                    'percentage': percentage,
                    'coins_earned': 3,
                })
            else:
                context['error'] = "Veuillez compléter le tracé et l'étalonnage de la photo."

        except (ValueError, json.JSONDecodeError, ZeroDivisionError):
            context['error'] = "Erreur dans le calcul de la surface. Recommencez le tracé."

    return render(request, 'core/ajout_textile.html', context)


DIFFICULTE_LABELS = {1: 'Débutant', 2: 'Intermédiaire', 3: 'Avancé'}

MATERIAL_LABELS = {
    'coton': 'Coton', 'polyester': 'Polyester', 'laine': 'Laine', 'lin': 'Lin',
    'soie': 'Soie', 'viscose': 'Viscose', 'nylon': 'Nylon', 'elasthanne': 'Élasthanne',
    'acrylique': 'Acrylique', 'cachemire': 'Cachemire', 'bambou': 'Bambou', 'velours': 'Velours',
    'denim': 'Denim', 'cuir': 'Cuir', 'satin': 'Satin', 'modal': 'Modal',
}

# kg CO₂eq évités par kg de textile non jeté
# Représente les émissions de fin de vie évitées : transport vers tri/export + incinération/enfouissement
# N'inclut PAS les émissions évitées de production d'un vêtement neuf
CO2_PAR_MATIERE = {
    'coton':        1.3,   # Fibre cellulosique, incinération ~1.8 kg CO₂/kg, enfouissement ~0.3 kg
    'lin':          1.2,
    'viscose':      1.2,
    'bambou':       1.1,
    'modal':        1.2,
    'laine':        1.4,   # Décomposition anaérobie avec dégagement de méthane
    'cachemire':    1.4,
    'soie':         1.5,
    'velours':      1.3,
    'satin':        1.3,
    'denim':        1.3,   # Essentiellement du coton traité
    'polyester':    1.8,   # Synthétique, incinération ~2.5 kg CO₂/kg (haute teneur en carbone)
    'nylon':        1.9,
    'acrylique':    1.7,
    'elasthanne':   1.7,
    'cuir':         2.0,   # Produits chimiques de tannage + transport
}

# Litres d'eau par kg de textile (empreinte eau production évitée)
EAU_PAR_MATIERE = {
    'coton':        15000,
    'lin':           6000,
    'laine':        15000,
    'soie':          8000,
    'viscose':       5000,
    'bambou':        2000,
    'modal':         5000,
    'velours':      12000,
    'satin':         8000,
    'denim':        15000,
    'polyester':      500,
    'nylon':          500,
    'acrylique':      500,
    'elasthanne':     500,
    'cachemire':    20000,
    'cuir':         17000,
}

# Grammage moyen par type de vêtement (g/m²), pour convertir surface en masse
GRAMMAGE_PAR_TYPE = {
    'tshirt':   170,
    'jean':     380,
    'hoodie':   320,
    'robe':     130,
    'jupe':     150,
    'manteau':  420,
}

def calculer_co2_vetement(vetement):
    """Calcule le CO₂ évité (kg) pour un vêtement upcyclé, basé sur sa matière et son type."""
    grammage = GRAMMAGE_PAR_TYPE.get(vetement.typeVetement, 200)
    masse_kg = vetement.surfaceExploitable * grammage / 1000

    if not vetement.matiere:
        return masse_kg * 1.3

    co2 = 0.0
    for part in vetement.matiere.split(','):
        if ':' in part:
            nom, pct = part.strip().split(':', 1)
            facteur = CO2_PAR_MATIERE.get(nom.strip().lower(), 1.3)
            co2 += masse_kg * (float(pct) / 100) * facteur

    return co2 if co2 > 0 else masse_kg * 1.3

def calculer_stats_passeport(patron, garments):
    """Retourne (eau_litres, co2_kg) pour un projet terminé, basé sur surfaceMin du patron."""
    surface = patron.surfaceMin
    if not garments:
        masse_kg = surface * GRAMMAGE_PAR_TYPE.get(patron.typeObjet.lower(), 200) / 1000
        return round(masse_kg * 15000), round(masse_kg * 1.3, 2)
    grammages = [GRAMMAGE_PAR_TYPE.get(g.typeVetement, 200) for g in garments]
    masse_kg = surface * (sum(grammages) / len(grammages)) / 1000
    all_mats = {}
    for g in garments:
        dom = get_dominant_material(g.matiere)
        if dom:
            all_mats[dom] = all_mats.get(dom, 0) + 1
    mat = max(all_mats, key=all_mats.get) if all_mats else 'coton'
    return round(masse_kg * EAU_PAR_MATIERE.get(mat, 15000)), round(masse_kg * CO2_PAR_MATIERE.get(mat, 1.3), 2)


MATERIAL_COLORS = {
    'coton': '#D4C5A9', 'polyester': '#93A8B8', 'laine': '#C8A96A', 'lin': '#C9B882',
    'soie': '#C4B0D8', 'viscose': '#7FC9CF', 'nylon': '#F4A06A', 'elasthanne': '#8DC89A',
    'acrylique': '#F4A0B4', 'cachemire': '#C4AFA9', 'bambou': '#9DBE94', 'velours': '#9A80C8',
    'denim': '#5B8BB4', 'cuir': '#8D6E63', 'satin': '#F0B0C8', 'modal': '#80C4BE',
}


def get_dominant_material(matiere_str):
    """Retourne la matière dominante depuis 'coton:70,polyester:30'."""
    if not matiere_str:
        return None
    best_name, best_pct = None, -1
    for part in matiere_str.split(','):
        part = part.strip()
        if ':' in part:
            name, pct_str = part.rsplit(':', 1)
            try:
                pct = int(pct_str)
                if pct > best_pct:
                    best_pct, best_name = pct, name.strip().lower()
            except ValueError:
                pass
        elif best_name is None:
            best_name = part.lower()
    return best_name


def _compatibilite(surface_user, surface_min):
    if surface_min and surface_min > 0 and surface_user > 0:
        return min(100, round((surface_user / surface_min) * 100))
    return 0


@login_required
def patrons(request):
    surface_user = (
        Vetement.objects
        .filter(utilisateur=request.user)
        .aggregate(total=Sum('surfaceExploitable'))['total'] or 0.0
    )

    liked_ids = set(
        PatronLike.objects.filter(utilisateur=request.user).values_list('patron_id', flat=True)
    )

    progressions_qs = (
        ProgressionProjet.objects
        .filter(utilisateur=request.user, termine=False)
        .select_related('patron')
    )
    en_cours_patron_ids = {p.patron_id for p in progressions_qs}

    patrons_list = []
    for p in Patron.objects.all().order_by('difficulte'):
        patrons_list.append({
            'id': p.pk,
            'titre': p.titre,
            'image': p.photo.url if p.photo else None,
            'compatibilite': _compatibilite(surface_user, p.surfaceMin),
            'tissu': p.typeObjet,
            'difficulte_label': DIFFICULTE_LABELS.get(p.difficulte, str(p.difficulte)),
            'duree': p.duree or '?',
            'est_premium': p.estPremium,
            'est_liked': p.pk in liked_ids,
            'en_cours': p.pk in en_cours_patron_ids,
        })

    projets_en_cours = []
    for prog in progressions_qs:
        p = prog.patron
        total_etapes = p.etapes.count()
        pct = round((prog.etape_actuelle / total_etapes) * 100) if total_etapes > 0 else 0
        projets_en_cours.append({
            'patron_id': p.pk,
            'titre': p.titre,
            'image': p.photo.url if p.photo else None,
            'etape_actuelle': prog.etape_actuelle,
            'total_etapes': total_etapes,
            'progression_pct': pct,
            'difficulte_label': DIFFICULTE_LABELS.get(p.difficulte, str(p.difficulte)),
        })

    return render(request, 'core/patrons.html', {
        'patrons': patrons_list,
        'projets_en_cours': projets_en_cours,
        'liked_ids_json': list(liked_ids),
    })


@login_required
def patron_detail(request, pk):
    patron = get_object_or_404(Patron, pk=pk)

    # ── POST : enregistrer la sélection de vêtements et démarrer le projet ──
    if request.method == 'POST':
        ids_json = request.POST.get('vetement_ids', '[]')
        try:
            vetement_ids = json.loads(ids_json)
        except (ValueError, TypeError):
            vetement_ids = []

        prog, _ = ProgressionProjet.objects.get_or_create(
            utilisateur=request.user,
            patron=patron,
            defaults={'etape_actuelle': 1},
        )
        garments = Vetement.objects.filter(utilisateur=request.user, id__in=vetement_ids)
        prog.vetements_projet.set(garments)
        return redirect('etape_projet', patron_pk=patron.pk, etape_num=1)

    # ── GET ──
    tutoriels = patron.tutoriels.all()
    surface_user = (
        Vetement.objects
        .filter(utilisateur=request.user)
        .aggregate(total=Sum('surfaceExploitable'))['total'] or 0.0
    )

    etapes = list(patron.etapes.order_by('numero'))
    premiere_etape = etapes[0] if etapes else None

    # Outils nécessaires (materiel du patron + des étapes)
    outils_set = []
    seen = set()
    if patron.materiel:
        for m in patron.materiel.split(','):
            m = m.strip()
            if m and m.lower() not in seen:
                seen.add(m.lower())
                outils_set.append(m)
    for etape in etapes:
        if etape.materiaux_etape:
            for m in etape.materiaux_etape.split(','):
                m = m.strip()
                if m and m.lower() not in seen:
                    seen.add(m.lower())
                    outils_set.append(m)

    # Matières requises pour ce patron
    matieres_requises = []
    if patron.matiere_requise:
        matieres_requises = [m.strip().lower() for m in patron.matiere_requise.split(',') if m.strip()]

    matieres_requises_display = [
        {'key': m, 'label': MATERIAL_LABELS.get(m, m.capitalize()), 'color': MATERIAL_COLORS.get(m, '#BCBAA8')}
        for m in matieres_requises
    ]

    # Vêtements de l'utilisateur + compatibilité
    user_vetements = Vetement.objects.filter(utilisateur=request.user).order_by('-surfaceExploitable')

    # Vêtements déjà sélectionnés pour ce projet (si projet en cours)
    prog_existante = ProgressionProjet.objects.filter(
        utilisateur=request.user, patron=patron, termine=False
    ).first()
    selected_ids = set()
    if prog_existante:
        selected_ids = set(prog_existante.vetements_projet.values_list('id', flat=True))

    vetements_compatibles = []
    for v in user_vetements:
        surface_ok = v.surfaceExploitable >= patron.surfaceMin
        dominant = get_dominant_material(v.matiere)
        if matieres_requises:
            matiere_ok = bool(dominant and dominant in matieres_requises)
        else:
            matiere_ok = True  # pas de contrainte matière
        vetements_compatibles.append({
            'vetement': v,
            'surface_ok': surface_ok,
            'matiere_ok': matiere_ok,
            'compatible': surface_ok and matiere_ok,
            'dominant_material': dominant,
            'dominant_label': MATERIAL_LABELS.get(dominant, dominant.capitalize()) if dominant else None,
            'dominant_color': MATERIAL_COLORS.get(dominant, '#BCBAA8') if dominant else '#BCBAA8',
            'selected': v.id in selected_ids,
        })

    context = {
        'patron': patron,
        'tutoriels': tutoriels,
        'etapes': etapes,
        'premiere_etape': premiere_etape,
        'difficulte_label': DIFFICULTE_LABELS.get(patron.difficulte, str(patron.difficulte)),
        'compatibilite': _compatibilite(surface_user, patron.surfaceMin),
        'materiel_list': outils_set,
        'matieres_requises_display': matieres_requises_display,
        'vetements_compatibles': vetements_compatibles,
        'has_compatible': any(v['compatible'] for v in vetements_compatibles),
    }
    return render(request, 'core/patron_detail.html', context)


@login_required
def etape_projet(request, patron_pk, etape_num):
    patron = get_object_or_404(Patron, pk=patron_pk)
    etapes = list(patron.etapes.order_by('numero'))

    if not etapes:
        return redirect('patron_detail', pk=patron_pk)

    if etape_num < 1 or etape_num > len(etapes):
        return redirect('patron_detail', pk=patron_pk)

    etape_index = etape_num - 1
    etape_actuelle = etapes[etape_index]
    total = len(etapes)

    progression = round((etape_num / total) * 100)

    etape_precedente = etapes[etape_index - 1] if etape_index > 0 else None
    etape_suivante = etapes[etape_index + 1] if etape_index < total - 1 else None

    materiaux_list = (
        [m.strip() for m in etape_actuelle.materiaux_etape.split(',') if m.strip()]
        if etape_actuelle.materiaux_etape else []
    )

    video_embed_id = None
    if etape_actuelle.video_url:
        match = re.search(r'(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})', etape_actuelle.video_url)
        if match:
            video_embed_id = match.group(1)

    # Sauvegarde / mise à jour de la progression
    prog, created = ProgressionProjet.objects.get_or_create(
        utilisateur=request.user,
        patron=patron,
        defaults={'etape_actuelle': etape_num},
    )
    if not created and etape_num > prog.etape_actuelle:
        prog.etape_actuelle = etape_num
        prog.save()

    context = {
        'patron': patron,
        'etape': etape_actuelle,
        'etape_num': etape_num,
        'total_etapes': total,
        'progression': progression,
        'etape_precedente_num': etape_num - 1 if etape_precedente else None,
        'etape_suivante_num': etape_num + 1 if etape_suivante else None,
        'materiaux_list': materiaux_list,
        'video_embed_id': video_embed_id,
        'est_derniere': etape_suivante is None,
    }
    return render(request, 'core/etape_projet.html', context)


@login_required
def terminer_projet(request, pk):
    patron = get_object_or_404(Patron, pk=pk)
    prog = ProgressionProjet.objects.filter(utilisateur=request.user, patron=patron, termine=False).first()
    if prog:
        garments = list(prog.vetements_projet.all())
        if garments and patron.surfaceMin > 0:
            total_available = sum(g.surfaceExploitable for g in garments if g.surfaceExploitable > 0)
            if total_available > 0:
                for g in garments:
                    if g.surfaceExploitable > 0:
                        ratio = g.surfaceExploitable / total_available
                        to_deduct = min(g.surfaceExploitable, patron.surfaceMin * ratio)
                        g.surfaceExploitable = round(max(0.0, g.surfaceExploitable - to_deduct), 4)
                        g.save()
        prog.termine = True
        prog.save()
        request.user.soldePieces += 20
        request.user.save()
        check_and_award_badges(request.user)
    return redirect('passeport_circulaire', pk=patron.pk)


@login_required
def passeport_circulaire(request, pk):
    patron = get_object_or_404(Patron, pk=pk)
    prog = (
        ProgressionProjet.objects
        .filter(utilisateur=request.user, patron=patron, termine=True)
        .order_by('-date_derniere_activite')
        .first()
    )
    if not prog:
        return redirect('patrons')

    garments = list(prog.vetements_projet.all())
    eau_litres, co2_kg = calculer_stats_passeport(patron, garments)
    noms_tissus = [g.nomVetement for g in garments]

    return render(request, 'core/passeport_circulaire.html', {
        'patron': patron,
        'garments': garments,
        'noms_tissus_str': ', '.join(noms_tissus) if noms_tissus else 'Tissu recyclé',
        'eau_litres': eau_litres,
        'co2_economise': co2_kg,
        'total_etapes': patron.etapes.count(),
        'date_creation': prog.date_derniere_activite,
        'coins_gagnes': 20,
    })


def qrcode_view(request):
    url = request.GET.get('url', '')
    if not url:
        return HttpResponse(status=400)
    qr = qrcode_lib.QRCode(
        version=None,
        error_correction=qrcode_lib.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=(35, 115, 41), back_color=(255, 251, 255))
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return HttpResponse(buf.read(), content_type='image/png')


def passeport_public(request, patron_pk, user_pk):
    patron = get_object_or_404(Patron, pk=patron_pk)
    utilisateur = get_object_or_404(Utilisateur, pk=user_pk)
    prog = (
        ProgressionProjet.objects
        .filter(utilisateur=utilisateur, patron=patron, termine=True)
        .order_by('-date_derniere_activite')
        .first()
    )
    if not prog:
        return redirect('home')

    garments = list(prog.vetements_projet.all())
    eau_litres, co2_kg = calculer_stats_passeport(patron, garments)
    noms_tissus = [g.nomVetement for g in garments]
    nom_creation = request.GET.get('nom', patron.titre)

    return render(request, 'core/passeport_public.html', {
        'patron': patron,
        'utilisateur': utilisateur,
        'nom_creation': nom_creation,
        'noms_tissus_str': ', '.join(noms_tissus) if noms_tissus else 'Tissu recyclé',
        'noms_tissus': noms_tissus,
        'eau_litres': eau_litres,
        'co2_economise': co2_kg,
        'total_etapes': patron.etapes.count(),
        'date_creation': prog.date_derniere_activite,
    })


@login_required
def toggle_like(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    patron = get_object_or_404(Patron, pk=pk)
    like, created = PatronLike.objects.get_or_create(utilisateur=request.user, patron=patron)
    if not created:
        like.delete()
        is_liked = False
    else:
        is_liked = True
    return JsonResponse({'liked': is_liked})


COMMUNITY_LEVELS = [
    (0,    100,  'Éco-Curieux',  '🌱'),
    (100,  300,  'Éco-Apprenti', '🌿'),
    (300,  600,  'Éco-Créateur', '🍃'),
    (600,  1000, 'Éco-Mentor',   '🌲'),
    (1000, None, 'Éco-Expert',   '🌳'),
]

def _get_user_level(user):
    nb_posts    = user.posts_communaute.count()
    nb_likes    = LikePost.objects.filter(post__utilisateur=user).count()
    nb_followers = user.followers.count()
    nb_comments = user.commentaires_posts.count()
    points = nb_posts * 10 + nb_likes + nb_followers * 3 + nb_comments * 2
    for min_pts, max_pts, nom, emoji in COMMUNITY_LEVELS:
        if max_pts is None or points < max_pts:
            if points >= min_pts:
                pct = round((points - min_pts) / (max_pts - min_pts) * 100) if max_pts else 100
                return {
                    'nom': nom, 'emoji': emoji, 'points': points,
                    'points_max': max_pts or points + 1,
                    'pourcentage': pct,
                    'restants': max(0, (max_pts or 0) - points),
                }
    last = COMMUNITY_LEVELS[-1]
    return {'nom': last[2], 'emoji': last[3], 'points': points,
            'points_max': points, 'pourcentage': 100, 'restants': 0}


@login_required
def communaute(request):
    q             = request.GET.get('q', '').strip()
    type_filtre   = request.GET.get('type', '')
    niveau_filtre = request.GET.get('niveau', '')
    tri           = request.GET.get('tri', 'nouveautes')
    hashtag_slug  = request.GET.get('hashtag', '')

    posts_qs = PostCommunaute.objects.select_related('utilisateur', 'patron_lie').prefetch_related('likes', 'commentaires', 'hashtags')

    if q:
        posts_qs = posts_qs.filter(Q(titre__icontains=q) | Q(description__icontains=q) | Q(utilisateur__username__icontains=q))
    if type_filtre:
        posts_qs = posts_qs.filter(type_creation=type_filtre)
    if niveau_filtre:
        posts_qs = posts_qs.filter(niveau=niveau_filtre)
    if hashtag_slug:
        posts_qs = posts_qs.filter(hashtags__nom__iexact=hashtag_slug)

    if tri == 'populaires':
        posts_qs = posts_qs.annotate(nl=Count('likes')).order_by('-nl', '-date_creation')
    elif tri == 'tendances':
        depuis = timezone.now() - timedelta(hours=48)
        posts_qs = posts_qs.filter(date_creation__gte=depuis).annotate(nl=Count('likes')).order_by('-nl', '-date_creation')
    else:
        posts_qs = posts_qs.order_by('-date_creation')

    liked_ids = set(LikePost.objects.filter(utilisateur=request.user).values_list('post_id', flat=True))
    saved_ids = set(SauvegardePost.objects.filter(utilisateur=request.user).values_list('post_id', flat=True))

    posts_data = []
    for post in posts_qs[:30]:
        posts_data.append({
            'post': post,
            'is_liked': post.id in liked_ids,
            'is_saved': post.id in saved_ids,
            'nb_likes': post.likes.count(),
            'nb_commentaires': post.commentaires.count(),
            'is_own': post.utilisateur_id == request.user.pk,
        })

    hashtags = Hashtag.objects.annotate(nb=Count('posts')).filter(nb__gt=0).order_by('-nb')[:12]

    une_semaine = timezone.now() - timedelta(days=7)
    creator_of_week = (
        Utilisateur.objects
        .exclude(pk=request.user.pk)
        .annotate(likes_semaine=Count('posts_communaute__likes',
                                      filter=Q(posts_communaute__date_creation__gte=une_semaine)))
        .filter(likes_semaine__gt=0)
        .order_by('-likes_semaine')
        .first()
    )
    is_following_creator = (
        Suivi.objects.filter(suiveur=request.user, suivi=creator_of_week).exists()
        if creator_of_week else False
    )

    return render(request, 'core/communaute.html', {
        'posts_data': posts_data,
        'hashtags': hashtags,
        'creator_of_week': creator_of_week,
        'is_following_creator': is_following_creator,
        'level_info': _get_user_level(request.user),
        'q': q,
        'type_filtre': type_filtre,
        'niveau_filtre': niveau_filtre,
        'tri': tri,
        'hashtag_slug': hashtag_slug,
        'post_types': PostCommunaute.TYPE_CHOICES,
        'post_niveaux': PostCommunaute.NIVEAU_CHOICES,
    })


@login_required
def creer_post(request):
    if request.method == 'POST':
        titre       = request.POST.get('titre', '').strip()
        description = request.POST.get('description', '').strip()
        type_c      = request.POST.get('type_creation', 'fait-main')
        niveau      = request.POST.get('niveau', 'debutant')
        patron_id   = request.POST.get('patron_lie', '')
        tags_raw    = request.POST.get('hashtags', '')

        if not titre or not description:
            return render(request, 'core/creer_post.html', {
                'patrons': Patron.objects.all(),
                'error': 'Le titre et la description sont obligatoires.',
            })

        image_fichier = None
        photo_data = request.POST.get('photo_data', '')
        if photo_data and ';base64,' in photo_data:
            fmt, imgstr = photo_data.split(';base64,', 1)
            ext = fmt.split('/')[-1]
            image_fichier = ContentFile(base64.b64decode(imgstr), name=f'post.{ext}')

        patron_obj = None
        if patron_id:
            patron_obj = Patron.objects.filter(pk=patron_id).first()

        post = PostCommunaute.objects.create(
            utilisateur=request.user,
            titre=titre,
            description=description,
            type_creation=type_c,
            niveau=niveau,
            patron_lie=patron_obj,
            image=image_fichier,
        )

        for tag_nom in [t.strip().lstrip('#').lower() for t in tags_raw.split(',') if t.strip()]:
            if tag_nom:
                hashtag, _ = Hashtag.objects.get_or_create(nom=tag_nom)
                post.hashtags.add(hashtag)

        request.user.soldePieces += 5
        request.user.save()
        check_and_award_badges(request.user)

        return redirect('detail_post', pk=post.pk)

    return render(request, 'core/creer_post.html', {'patrons': Patron.objects.all()})


@login_required
def detail_post(request, pk):
    post = get_object_or_404(PostCommunaute.objects.select_related('utilisateur', 'patron_lie'), pk=pk)

    post.nb_vues += 1
    post.save(update_fields=['nb_vues'])

    commentaires = post.commentaires.select_related('utilisateur').all()
    is_liked = LikePost.objects.filter(utilisateur=request.user, post=post).exists()
    is_saved = SauvegardePost.objects.filter(utilisateur=request.user, post=post).exists()
    is_following = Suivi.objects.filter(suiveur=request.user, suivi=post.utilisateur).exists()

    return render(request, 'core/detail_post.html', {
        'post': post,
        'commentaires': commentaires,
        'is_liked': is_liked,
        'is_saved': is_saved,
        'is_own': post.utilisateur_id == request.user.pk,
        'is_following': is_following,
        'nb_likes': post.likes.count(),
    })


@login_required
def toggle_like_post(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    post = get_object_or_404(PostCommunaute, pk=pk)
    like, created = LikePost.objects.get_or_create(utilisateur=request.user, post=post)
    if not created:
        like.delete()
        is_liked = False
    else:
        is_liked = True
        check_and_award_badges(request.user)
    return JsonResponse({'liked': is_liked, 'nb_likes': post.likes.count()})


@login_required
def toggle_sauvegarde(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    post = get_object_or_404(PostCommunaute, pk=pk)
    save_obj, created = SauvegardePost.objects.get_or_create(utilisateur=request.user, post=post)
    if not created:
        save_obj.delete()
        is_saved = False
    else:
        is_saved = True
    return JsonResponse({'saved': is_saved})


@login_required
def ajouter_commentaire(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    post = get_object_or_404(PostCommunaute, pk=pk)
    try:
        data = json.loads(request.body)
        contenu = data.get('contenu', '').strip()
    except (json.JSONDecodeError, AttributeError):
        contenu = request.POST.get('contenu', '').strip()

    if not contenu:
        return JsonResponse({'error': 'Contenu vide'}, status=400)

    commentaire = CommentairePost.objects.create(utilisateur=request.user, post=post, contenu=contenu)
    check_and_award_badges(request.user)
    return JsonResponse({
        'id': commentaire.id,
        'contenu': commentaire.contenu,
        'auteur': request.user.username,
        'avatar': request.user.avatar_url,
        'date': 'à l\'instant',
        'nb_commentaires': post.commentaires.count(),
    })


@login_required
def supprimer_post(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    post = get_object_or_404(PostCommunaute, pk=pk, utilisateur=request.user)
    post.delete()
    return redirect('communaute')


@login_required
def profil_utilisateur(request, pk):
    profil = get_object_or_404(Utilisateur, pk=pk)
    posts  = PostCommunaute.objects.filter(utilisateur=profil).order_by('-date_creation')

    liked_ids = set(LikePost.objects.filter(utilisateur=request.user).values_list('post_id', flat=True))
    saved_ids = set(SauvegardePost.objects.filter(utilisateur=request.user).values_list('post_id', flat=True))

    posts_data = [{'post': p, 'is_liked': p.id in liked_ids, 'is_saved': p.id in saved_ids,
                   'nb_likes': p.likes.count(), 'nb_commentaires': p.commentaires.count()}
                  for p in posts]

    is_following = False
    if request.user != profil:
        is_following = Suivi.objects.filter(suiveur=request.user, suivi=profil).exists()

    return render(request, 'core/profil_utilisateur.html', {
        'profil': profil,
        'posts_data': posts_data,
        'nb_posts': posts.count(),
        'nb_followers': profil.followers.count(),
        'nb_following': profil.suivis.count(),
        'is_following': is_following,
        'is_own': profil == request.user,
        'level_info': _get_user_level(profil),
    })


@login_required
def toggle_suivi(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    cible = get_object_or_404(Utilisateur, pk=pk)
    if cible == request.user:
        return JsonResponse({'error': 'Vous ne pouvez pas vous suivre vous-même'}, status=400)
    suivi_obj, created = Suivi.objects.get_or_create(suiveur=request.user, suivi=cible)
    if not created:
        suivi_obj.delete()
        is_following = False
    else:
        is_following = True
    return JsonResponse({'following': is_following, 'nb_followers': cible.followers.count()})


@login_required
def mes_posts(request):
    posts = PostCommunaute.objects.filter(utilisateur=request.user).order_by('-date_creation')
    posts_data = [{'post': p, 'nb_likes': p.likes.count(), 'nb_commentaires': p.commentaires.count()} for p in posts]
    return render(request, 'core/mes_posts.html', {
        'posts_data': posts_data,
        'level_info': _get_user_level(request.user),
    })


@login_required
def supprimer_vetements(request):
    if request.method == 'POST':
        ids = request.POST.getlist('vetement_ids[]')
        Vetement.objects.filter(utilisateur=request.user, id__in=ids).delete()
    return redirect('mes_tissus')


@login_required
def mes_tissus(request):
    vetements = Vetement.objects.filter(utilisateur=request.user).order_by('-id')
    total_surface = sum(v.surfaceExploitable for v in vetements)
    total_co2 = round(sum(calculer_co2_vetement(v) for v in vetements), 1)
    objectif = 15.0
    progression_pct = min(100, int((total_surface / objectif) * 100)) if objectif > 0 else 0
    circumference = 251
    stroke_offset = round(circumference * (1 - min(1.0, total_surface / objectif)))

    all_patrons = Patron.objects.all()
    vetements_data = []
    for v in vetements:
        nb_compatibles = sum(1 for p in all_patrons if v.surfaceExploitable >= p.surfaceMin)
        vetements_data.append({'vetement': v, 'nb_compatibles': nb_compatibles})

    context = {
        'vetements_data': vetements_data,
        'total_surface': round(total_surface, 2),
        'total_co2': total_co2,
        'nb_vetements': vetements.count(),
        'progression_pct': progression_pct,
        'stroke_offset': stroke_offset,
        'circumference': circumference,
    }
    return render(request, 'core/mes_tissus.html', context)


@login_required
def mon_profil(request):
    user = request.user
    errors = {}

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        bio = request.POST.get('bio', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        avatar = request.POST.get('avatar', user.avatar)
        niveau_couture = request.POST.get('niveau_couture', user.niveau_couture)
        envies_list = request.POST.getlist('envies_creation')

        if username and username != user.username:
            if Utilisateur.objects.filter(username=username).exclude(pk=user.pk).exists():
                errors['username'] = "Ce pseudo est déjà pris."
            else:
                user.username = username
        elif not username:
            errors['username'] = "Le pseudo ne peut pas être vide."

        if email and email != user.email:
            if Utilisateur.objects.filter(email=email).exclude(pk=user.pk).exists():
                errors['email'] = "Cette adresse e-mail est déjà utilisée."
            else:
                user.email = email

        if not errors:
            user.bio = bio or None
            user.first_name = first_name
            user.last_name = last_name
            if avatar in AVATAR_FILENAMES:
                user.avatar = avatar
            user.niveau_couture = niveau_couture or None
            user.envies_creation = ', '.join(envies_list) if envies_list else None
            user.save()
            return redirect(reverse('mon_profil') + '?saved=1')

    ENVIES_CHOICES = [
        ('sacs', 'Sacs'),
        ('hauts', 'Hauts'),
        ('accessoires', 'Accessoires'),
        ('jeans', 'Jeans'),
        ('manteaux', 'Manteaux'),
        ('decorations', 'Décorations'),
    ]
    current_envies = [e.strip() for e in (user.envies_creation or '').split(',') if e.strip()]
    return render(request, 'core/mon_profil.html', {
        'avatars': AVATAR_FILENAMES,
        'current_envies': current_envies,
        'envies_choices': ENVIES_CHOICES,
        'level_info': _get_user_level(user),
        'errors': errors,
        'saved': request.GET.get('saved') == '1',
    })


def inscription(request):
    if request.method == 'POST':
        # On sauvegarde l'email et le mdp dans la session
        request.session['reg_email'] = request.POST.get('email')
        request.session['reg_password'] = request.POST.get('password')
        return redirect('inscription_etape1')

    return render(request, 'core/inscription.html')

AVATAR_FILENAMES = [f'image {i}.png' for i in range(11, 27)]

def inscription_etape1(request):
    if request.method == 'POST':
        request.session['reg_username'] = request.POST.get('username')
        request.session['reg_avatar'] = request.POST.get('avatar', 'image 11.png')
        return redirect('inscription_etape2')

    return render(request, 'core/inscription_etape1.html', {'avatars': AVATAR_FILENAMES})

def inscription_etape2(request):
    if request.method == 'POST':
        # On sauvegarde le niveau
        request.session['reg_niveau'] = request.POST.get('experience_level')
        return redirect('inscription_etape3')
        
    return render(request, 'core/inscription_etape2.html')

def inscription_etape3(request):
    if request.method == 'POST':
        # 1. On récupère les cases cochées
        cibles_list = request.POST.getlist('target')
        cibles_str = ", ".join(cibles_list)

        # 2. On récupère toutes les infos des étapes précédentes dans la session
        email = request.session.get('reg_email')
        password = request.session.get('reg_password')
        username = request.session.get('reg_username')
        niveau = request.session.get('reg_niveau')
        avatar = request.session.get('reg_avatar', 'image 11.png')

        # 3. On créé le compte dans la session
        nouvel_utilisateur = Utilisateur.objects.create_user(
            username=username,
            email=email,
            password=password,
            niveau_couture=niveau,
            envies_creation=cibles_str,
            avatar=avatar,
        )

        # 4. On nettoie la session
        keys_to_delete = ['reg_email', 'reg_password', 'reg_username', 'reg_niveau', 'reg_avatar']
        for key in keys_to_delete:
            if key in request.session:
                del request.session[key]

        # 5. On connecte l'utilisateur automatiquement et on l'envoie sur l'accueil
        login(request, nouvel_utilisateur)
        return redirect('home')


@login_required
def detail_vetement(request, pk):
    vetement = get_object_or_404(Vetement, pk=pk, utilisateur=request.user)

    if request.method == 'POST':
        vetement.nomVetement = request.POST.get('nom_vetement', vetement.nomVetement).strip() or vetement.nomVetement
        vetement.typeVetement = request.POST.get('clothing_type', vetement.typeVetement)
        vetement.qualite = int(request.POST.get('qualite', vetement.qualite))
        vetement.couleur = request.POST.get('couleur', vetement.couleur)
        vetement.matiere = request.POST.get('material', vetement.matiere)

        photo_data = request.POST.get('photo_data', '')
        if photo_data and ';base64,' in photo_data:
            fmt, imgstr = photo_data.split(';base64,')
            ext = fmt.split('/')[-1]
            vetement.photoURL = ContentFile(base64.b64decode(imgstr), name=f'vetement.{ext}')

        vetement.save()
        return redirect('mes_tissus')

    return render(request, 'core/detail_vetement.html', {'vetement': vetement})
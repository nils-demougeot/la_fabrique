import base64
import binascii
import hashlib
import json
import logging
import re
import threading
import urllib.parse
from io import BytesIO

from django.core.cache import cache

from django.conf import settings as dj_settings

import qrcode as qrcode_lib
from PIL import Image as PILImage

from django.core.files.base import ContentFile
from django.core import signing
from django.core.mail import send_mail
from django.utils.http import url_has_allowed_host_and_scheme
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta
import math

from django.http import HttpResponse, JsonResponse
from core.models import (Vetement, Utilisateur, Patron, EtapePatron, PiecePatron, ProgressionProjet, PatronLike,
                         PostCommunaute, LikePost, SauvegardePost, CommentairePost, Suivi, Hashtag, Badge)

logger = logging.getLogger('core')

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 Mo


def decode_base64_image(photo_data, name_prefix):
    """Décode une image data-URI base64 en validant le format et la taille.

    Renvoie un ContentFile prêt à être stocké, ou None si la donnée est absente
    ou invalide. Vérifie l'extension (liste blanche) et que le contenu est bien
    une image décodable par Pillow — empêche le stockage de fichiers arbitraires
    (ex : SVG/HTML piégé) via le champ photo.
    """
    if not photo_data or ';base64,' not in photo_data:
        return None

    fmt, imgstr = photo_data.split(';base64,', 1)
    ext = fmt.split('/')[-1].lower().strip()
    if ext == 'jpe':
        ext = 'jpg'
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError('Format d\'image non autorisé.')

    try:
        raw = base64.b64decode(imgstr, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('Image base64 invalide.')

    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError('Image vide ou trop volumineuse.')

    try:
        with PILImage.open(BytesIO(raw)) as im:
            im.load()
            compressed = _compress_pil_image(im)
    except Exception:
        raise ValueError('Le fichier fourni n\'est pas une image valide.')

    return ContentFile(compressed, name=f'{name_prefix}.jpg')


def _compress_pil_image(im):
    """Redimensionne à 1200px max et compresse en JPEG q85. Gère la transparence."""
    if im.mode in ('RGBA', 'LA', 'P', 'PA'):
        rgba = im.convert('RGBA')
        bg = PILImage.new('RGB', rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[3])
        im = bg
    elif im.mode != 'RGB':
        im = im.convert('RGB')

    w, h = im.size
    if max(w, h) > 1200:
        ratio = 1200 / max(w, h)
        im = im.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), PILImage.LANCZOS)

    buf = BytesIO()
    im.save(buf, format='JPEG', quality=85, optimize=True)
    return buf.getvalue()


def _compress_uploaded_image(uploaded_file, name_prefix):
    """Compresse un fichier Django UploadedFile avant stockage. Renvoie None si absent."""
    if not uploaded_file:
        return None
    try:
        raw = uploaded_file.read()
        with PILImage.open(BytesIO(raw)) as im:
            im.load()
            compressed = _compress_pil_image(im)
        return ContentFile(compressed, name=f'{name_prefix}.jpg')
    except Exception:
        uploaded_file.seek(0)
        return uploaded_file


_PDF_CACHE_TTL = 60 * 60  # 1 heure


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
    # Le solde de pièces réel est affiché via le header (user.soldePieces) pour les
    # utilisateurs connectés ; pas de valeur factice ici.
    return render(request, 'core/index.html')


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
            'image': p.photo_url,
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

def _polygon_area_px2(px_points):
    """Aire d'un polygone (formule du lacet) à partir de points en pixels."""
    area = 0.0
    n = len(px_points)
    for i in range(n):
        j = (i + 1) % n
        area += px_points[i][0] * px_points[j][1]
        area -= px_points[j][0] * px_points[i][1]
    return abs(area) / 2.0


def _analyser_face(request, prefix):
    """
    Analyse une face (avant / arrière) à partir des données du formulaire.
    Retourne un dict {area_m2, tache_m2, trou_m2, photo_data} ou None si incomplète.

    - polygon_<prefix>      : liste de points normalisés (0-1) du détourage
    - calib_coords_<prefix> : 2 points normalisés du segment d'étalonnage
    - calib_distance_<prefix>: distance réelle (cm) de ce segment
    - img_w_<prefix>, img_h_<prefix> : dimensions de l'image source (px)
    - defects_<prefix>      : liste de cercles {x, y, r, type} (r normalisé / largeur)
    """
    polygon = json.loads(request.POST.get(f'polygon_{prefix}', '[]') or '[]')
    calib = json.loads(request.POST.get(f'calib_coords_{prefix}', '[]') or '[]')
    calib_distance_cm = float(request.POST.get(f'calib_distance_{prefix}', 0) or 0)
    img_w = float(request.POST.get(f'img_w_{prefix}', 0) or 0)
    img_h = float(request.POST.get(f'img_h_{prefix}', 0) or 0)
    defects = json.loads(request.POST.get(f'defects_{prefix}', '[]') or '[]')

    if len(polygon) < 3 or len(calib) != 2 or calib_distance_cm <= 0 or img_w <= 0:
        return None

    c1_x, c1_y = calib[0]['x'] * img_w, calib[0]['y'] * img_h
    c2_x, c2_y = calib[1]['x'] * img_w, calib[1]['y'] * img_h
    distance_px = math.sqrt((c2_x - c1_x) ** 2 + (c2_y - c1_y) ** 2)
    if distance_px == 0:
        return None

    cm_per_px = calib_distance_cm / distance_px

    px_points = [(p['x'] * img_w, p['y'] * img_h) for p in polygon]
    area_cm2 = _polygon_area_px2(px_points) * (cm_per_px ** 2)
    area_m2 = area_cm2 / 10000.0

    tache_m2 = 0.0
    trou_m2 = 0.0
    for d in defects:
        # rayon stocké normalisé par rapport à la largeur de l'image
        r_cm = float(d.get('r', 0)) * img_w * cm_per_px
        circle_m2 = math.pi * r_cm * r_cm / 10000.0
        if d.get('type') == 'tache':
            tache_m2 += circle_m2
        else:
            trou_m2 += circle_m2

    return {
        'area_m2': area_m2,
        'tache_m2': tache_m2,
        'trou_m2': trou_m2,
        'photo_data': request.POST.get(f'photo_data_{prefix}', ''),
        'cm_per_px': cm_per_px,
        'polygon': polygon,
        'defects': defects,
    }


@login_required
def ajout_textile(request):
    context = {'result_ready': False}

    if request.method == 'POST':
        try:
            face_av = _analyser_face(request, 'avant')
            face_ar = _analyser_face(request, 'arriere')

            if face_av is None:
                context['error'] = "Complète au moins la face avant : détourage + étalonnage."
                return render(request, 'core/ajout_textile.html', context)

            if face_ar is not None:
                # Les deux faces sont renseignées : on les additionne.
                surface_totale_m2 = face_av['area_m2'] + face_ar['area_m2']
                tache_m2 = face_av['tache_m2'] + face_ar['tache_m2']
                trou_m2 = face_av['trou_m2'] + face_ar['trou_m2']
            else:
                # Face arrière ignorée : on suppose l'arrière identique à l'avant.
                surface_totale_m2 = face_av['area_m2'] * 2
                tache_m2 = face_av['tache_m2'] * 2
                trou_m2 = face_av['trou_m2'] * 2

            total_defect_area_m2 = tache_m2 + trou_m2
            usable_area_m2 = max(0, surface_totale_m2 - total_defect_area_m2)
            percentage = int((usable_area_m2 / surface_totale_m2) * 100) if surface_totale_m2 > 0 else 0

            # SAUVEGARDE DANS LA BASE DE DONNÉES
            type_vetement = request.POST.get('clothing_type', 'inconnu')
            nom_vetement = request.POST.get('nom_vetement', '').strip() or f"{type_vetement.capitalize()} de {request.user.username}"
            qualite = int(request.POST.get('qualite', 3))
            couleur = request.POST.get('couleur', '')
            matiere_raw = request.POST.get('material', 'coton:100').strip() or 'coton:100'

            photo_fichier = decode_base64_image(face_av['photo_data'], 'vetement')

            Vetement.objects.create(
                utilisateur=request.user,
                nomVetement=nom_vetement,
                photoURL=photo_fichier,
                typeVetement=type_vetement,
                largeur=0,
                hauteur=0,
                surfaceTotale=surface_totale_m2,
                surfaceTaches=tache_m2,
                surfaceTrous=trou_m2,
                surfaceExploitable=usable_area_m2,
                etat="À transformer",
                qualite=qualite,
                couleur=couleur,
                matiere=matiere_raw,
                echelle_cm_px=face_av['cm_per_px'],
                detourage=json.dumps(face_av['polygon']),
                defauts=json.dumps(face_av['defects']),
            )

            coins_earned = 3
            request.user.soldePieces += coins_earned
            request.user.save()

            context.update({
                'result_ready': True,
                'usable_area': round(usable_area_m2, 2),
                'percentage': percentage,
                'coins_earned': coins_earned,
            })

        except (ValueError, json.JSONDecodeError, ZeroDivisionError):
            context['error'] = "Erreur dans le calcul de la surface. Recommence le détourage."

    return render(request, 'core/ajout_textile.html', context)


DIFFICULTE_LABELS = {1: 'Débutant', 2: 'Intermédiaire', 3: 'Avancé'}

MATERIAL_LABELS = {
    'coton': 'Coton', 'polyester': 'Polyester', 'laine': 'Laine', 'lin': 'Lin',
    'soie': 'Soie', 'viscose': 'Viscose', 'nylon': 'Nylon', 'elasthanne': 'Élasthanne',
    'acrylique': 'Acrylique', 'cachemire': 'Cachemire', 'bambou': 'Bambou', 'velours': 'Velours',
    'denim': 'Denim', 'cuir': 'Cuir', 'satin': 'Satin', 'modal': 'Modal',
}

# kg CO₂eq évités par kg de textile upcyclé
# = émissions de production évitées : quand on réutilise un vêtement, on évite l'achat d'un tissu neuf.
# Sources : Higg Materials Sustainability Index (MSI), ADEME Base Carbone, Quantis "Measuring Fashion" 2018.
CO2_PAR_MATIERE = {
    'coton':        5.5,   # Higg MSI ~7, ADEME ~4 → moyenne (culture intensive, teinture, filature)
    'lin':          3.5,   # Peu de pesticides, rouissage naturel — impact plus faible
    'viscose':      5.0,   # Procédé chimique de dissolution de cellulose
    'bambou':       4.0,   # Moins transformé que la viscose classique
    'modal':        5.0,   # Similaire viscose, procédé légèrement amélioré
    'laine':       25.0,   # Méthane entérique des moutons + terres agricoles (Higg MSI)
    'cachemire':   80.0,   # Rendement très faible (150g/chèvre/an) + dégradation des sols d'Asie centrale
    'soie':        12.0,   # Élevage intensif des vers à soie, chauffage des cocons
    'velours':      5.5,   # Base coton tissé en double nappe
    'satin':        5.5,   # Base coton ou soie → valeur intermédiaire
    'denim':        5.5,   # Coton + teinture indigo + traitements (délavage...)
    'polyester':    9.0,   # Higg MSI polyester vierge (dérivé pétrochimique)
    'nylon':       14.0,   # Higg MSI nylon 6 (protoxyde d'azote émis lors de la synthèse)
    'acrylique':    8.0,   # Dérivé pétrochimique, procédé énergivore
    'elasthanne':  12.0,   # Polyuréthane synthétique, production très intensive
    'cuir':        18.0,   # Élevage bovin (méthane) + tannage chimique au chrome
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

CO2_DEFAUT = 5.5  # coton, fibre la plus répandue

def calculer_co2_vetement(vetement):
    """Calcule le CO₂ évité (kg) pour un vêtement upcyclé — émissions de production évitées."""
    grammage = GRAMMAGE_PAR_TYPE.get(vetement.typeVetement, 200)
    masse_kg = vetement.surfaceExploitable * grammage / 1000

    if not vetement.matiere:
        return masse_kg * CO2_DEFAUT

    co2 = 0.0
    for part in vetement.matiere.split(','):
        if ':' in part:
            nom, pct = part.strip().split(':', 1)
            facteur = CO2_PAR_MATIERE.get(nom.strip().lower(), CO2_DEFAUT)
            co2 += masse_kg * (float(pct) / 100) * facteur

    return co2 if co2 > 0 else masse_kg * CO2_DEFAUT

def calculer_stats_passeport(patron, garments):
    """Retourne (eau_litres, co2_kg) pour un projet terminé, basé sur surfaceMin du patron."""
    surface = patron.surfaceMin
    if not garments:
        masse_kg = surface * GRAMMAGE_PAR_TYPE.get(patron.typeObjet.lower(), 200) / 1000
        return round(masse_kg * 15000), round(masse_kg * CO2_DEFAUT, 2)
    grammages = [GRAMMAGE_PAR_TYPE.get(g.typeVetement, 200) for g in garments]
    masse_kg = surface * (sum(grammages) / len(grammages)) / 1000
    all_mats = {}
    for g in garments:
        dom = get_dominant_material(g.matiere)
        if dom:
            all_mats[dom] = all_mats.get(dom, 0) + 1
    mat = max(all_mats, key=all_mats.get) if all_mats else 'coton'
    return round(masse_kg * EAU_PAR_MATIERE.get(mat, 15000)), round(masse_kg * CO2_PAR_MATIERE.get(mat, CO2_DEFAUT), 2)


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
            'image': p.photo_url,
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
            'image': p.photo_url,
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
def creer_patron(request):
    """Espace de création de patron réservé au staff (hors admin Django)."""
    if not request.user.is_staff:
        return redirect('patrons')

    TYPE_CHOICES = ['Haut', 'Bas', 'Robe', 'Accessoire', 'Sac', 'Déco', 'Enfant', 'Autre']

    if request.method == 'POST':
        titre = request.POST.get('titre', '').strip()
        description = request.POST.get('description', '').strip()
        type_objet = request.POST.get('type_objet', '').strip() or 'Autre'

        def _f(name, default=0.0):
            try:
                return float(request.POST.get(name, '') or default)
            except (ValueError, TypeError):
                return default

        def _i(name, default=1):
            try:
                return int(request.POST.get(name, '') or default)
            except (ValueError, TypeError):
                return default

        surface_min = _f('surface_min', 0.0)
        surface_max = _f('surface_max', 0.0)
        difficulte = max(1, min(3, _i('difficulte', 1)))
        duree = request.POST.get('duree', '').strip()
        materiel = request.POST.get('materiel', '').strip()
        matiere_requise = request.POST.get('matiere_requise', '').strip()
        est_premium = request.POST.get('est_premium') == '1'

        if not titre:
            return render(request, 'core/creer_patron.html', {
                'type_choices': TYPE_CHOICES,
                'error': "Le titre du patron est obligatoire.",
            })

        patron = Patron.objects.create(
            titre=titre,
            description=description,
            typeObjet=type_objet,
            surfaceMin=surface_min,
            surfaceMax=surface_max if surface_max > 0 else surface_min,
            estPremium=est_premium,
            difficulte=difficulte,
            photo=_compress_uploaded_image(request.FILES.get('cover_image'), 'patron'),
            duree=duree or None,
            materiel=materiel or None,
            matiere_requise=matiere_requise or None,
            createur=request.user,
        )

        # ── Étapes ──
        nb_etapes = _i('nb_etapes', 0)
        numero = 1
        for i in range(nb_etapes):
            e_titre = request.POST.get(f'etape_{i}_titre', '').strip()
            e_desc = request.POST.get(f'etape_{i}_description', '').strip()
            if not e_titre and not e_desc:
                continue
            EtapePatron.objects.create(
                patron=patron,
                numero=numero,
                titre=e_titre or f"Étape {numero}",
                description=e_desc,
                video_url=request.POST.get(f'etape_{i}_video', '').strip() or None,
                conseil=request.POST.get(f'etape_{i}_conseil', '').strip() or None,
                materiaux_etape=request.POST.get(f'etape_{i}_materiaux', '').strip() or None,
                image=_compress_uploaded_image(request.FILES.get(f'etape_{i}_image'), f'etape_{i}'),
            )
            numero += 1

        # ── Pièces à découper (SVG) ──
        nb_pieces = _i('nb_pieces', 0)
        ordre = 0
        for j in range(nb_pieces):
            p_nom = request.POST.get(f'piece_{j}_nom', '').strip()
            svg_file = request.FILES.get(f'piece_{j}_svg')
            if not p_nom and not svg_file:
                continue
            # On n'accepte que des fichiers .svg
            if svg_file and not svg_file.name.lower().endswith('.svg'):
                svg_file = None
            PiecePatron.objects.create(
                patron=patron,
                nom=p_nom or f"Pièce {ordre + 1}",
                quantite=max(1, _i(f'piece_{j}_quantite', 1)),
                largeur_cm=_f(f'piece_{j}_largeur', 0.0) or None,
                hauteur_cm=_f(f'piece_{j}_hauteur', 0.0) or None,
                svg=svg_file,
                ordre=ordre,
            )
            ordre += 1

        return redirect('patron_detail', pk=patron.pk)

    return render(request, 'core/creer_patron.html', {'type_choices': TYPE_CHOICES})


@login_required
def patron_detail(request, pk):
    patron = get_object_or_404(Patron, pk=pk)

    # ── POST : enregistrer la sélection de vêtements et démarrer le projet ──
    if request.method == 'POST':
        # Vérification souple : démarrer un projet exige un e-mail vérifié.
        if not request.user.email_verifie:
            return redirect(reverse('patron_detail', kwargs={'pk': patron.pk}) + '?verif_requise=1')

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
        'email_verifie': request.user.email_verifie,
        'verif_requise': request.GET.get('verif_requise') == '1',
    }
    return render(request, 'core/patron_detail.html', context)


@login_required
def faisabilite_patron(request, pk):
    """Outil de vérification de faisabilité : placer les pièces (SVG, à l'échelle réelle)
    sur la photo détourée d'un vêtement de l'utilisateur."""
    patron = get_object_or_404(Patron, pk=pk)

    pieces = []
    for pc in patron.pieces.all():
        pieces.append({
            'nom': pc.nom,
            'quantite': pc.quantite or 1,
            'largeur_cm': pc.largeur_cm,
            'hauteur_cm': pc.hauteur_cm,
            'svg_url': pc.svg_url,
        })

    # Ne proposer que les tissus choisis sur la fiche (param ?vetements=1,2,3).
    # Sans paramètre : on retombe sur tous les vêtements mesurés.
    sel_ids = set()
    sel_raw = request.GET.get('vetements', '').strip()
    if sel_raw:
        for part in sel_raw.split(','):
            part = part.strip()
            if part.isdigit():
                sel_ids.add(int(part))

    garments = []
    qs = (Vetement.objects
          .filter(utilisateur=request.user, echelle_cm_px__isnull=False)
          .order_by('-surfaceExploitable'))
    if sel_ids:
        qs = qs.filter(id__in=sel_ids)
    for v in qs:
        if not v.photo_url or not v.echelle_cm_px:
            continue
        try:
            detour = json.loads(v.detourage) if v.detourage else []
        except (ValueError, TypeError):
            detour = []
        try:
            defs = json.loads(v.defauts) if v.defauts else []
        except (ValueError, TypeError):
            defs = []
        if len(detour) < 3:
            continue
        garments.append({
            'id': v.id,
            'nom': v.nomVetement,
            'photo': v.photo_url,
            'echelle_cm_px': v.echelle_cm_px,
            'detourage': detour,
            'defauts': defs,
            'surface': round(v.surfaceExploitable, 2),
        })

    return render(request, 'core/faisabilite_patron.html', {
        'patron': patron,
        'fz_data': {'pieces': pieces, 'garments': garments},
        'has_pieces': len(pieces) > 0,
        'has_garments': len(garments) > 0,
    })


@login_required
def patron_pdf(request, pk):
    """Génère à la volée le PDF des pièces du patron, à taille réelle, réparties
    sur des feuilles A4 à imprimer puis assembler."""
    patron = get_object_or_404(Patron, pk=pk)
    pieces = list(patron.pieces.all())
    if not pieces:
        return HttpResponse(
            "Ce patron n'a pas encore de pièces enregistrées.",
            status=404, content_type='text/plain; charset=utf-8',
        )

    cache_key = f'pdf_patron_pieces_{pk}'
    pdf_bytes = cache.get(cache_key)
    if pdf_bytes is None:
        from core.pdf_patron import build_patron_pdf
        pdf_bytes = build_patron_pdf(patron, pieces)
        cache.set(cache_key, pdf_bytes, _PDF_CACHE_TTL)

    slug = re.sub(r'[^a-z0-9]+', '-', (patron.titre or 'patron').lower()).strip('-') or 'patron'
    disposition = 'attachment' if request.GET.get('download') == '1' else 'inline'
    resp = HttpResponse(pdf_bytes, content_type='application/pdf')
    resp['Content-Disposition'] = f'{disposition}; filename="patron-{slug}.pdf"'
    return resp


def _patron_slug(patron):
    slug = re.sub(r'[^a-z0-9]+', '-', (patron.titre or 'patron').lower()).strip('-')
    return slug or 'patron'


@login_required
def patron_instructions_pdf(request, pk):
    """PDF imprimable et mis en forme du déroulé du projet (toutes les étapes)."""
    patron = get_object_or_404(Patron, pk=pk)
    etapes = list(patron.etapes.order_by('numero'))

    # Outils nécessaires : matériel du patron + matériaux des étapes (dédupliqués)
    materiel_list, seen = [], set()
    sources = [patron.materiel] + [e.materiaux_etape for e in etapes]
    for src in sources:
        if not src:
            continue
        for m in src.split(','):
            m = m.strip()
            if m and m.lower() not in seen:
                seen.add(m.lower())
                materiel_list.append(m)

    cache_key = f'pdf_patron_instructions_{pk}'
    pdf_bytes = cache.get(cache_key)
    if pdf_bytes is None:
        from core.pdf_patron import build_instructions_pdf
        pdf_bytes = build_instructions_pdf(patron, etapes, materiel_list)
        cache.set(cache_key, pdf_bytes, _PDF_CACHE_TTL)

    disposition = 'attachment' if request.GET.get('download') == '1' else 'inline'
    resp = HttpResponse(pdf_bytes, content_type='application/pdf')
    resp['Content-Disposition'] = f'{disposition}; filename="instructions-{_patron_slug(patron)}.pdf"'
    return resp


@login_required
def patron_export(request, pk):
    """Exporte un patron au format JSON (sauvegarde / réimport dans le formulaire).

    Le SVG des pièces (texte) est embarqué dans le fichier pour que les formes
    soient restaurées à l'import ; les images (photo, photos d'étapes) ne sont
    référencées que par leur URL."""
    patron = get_object_or_404(Patron, pk=pk)

    def _read_svg(piece):
        if not getattr(piece, 'svg', None):
            return None
        try:
            piece.svg.open('rb')
            try:
                return piece.svg.read().decode('utf-8', 'ignore')
            finally:
                piece.svg.close()
        except Exception:
            return None

    data = {
        'format': 'la-fabrique/patron',
        'version': 1,
        'patron': {
            'titre': patron.titre,
            'description': patron.description or '',
            'type_objet': patron.typeObjet or '',
            'difficulte': patron.difficulte,
            'duree': patron.duree or '',
            'est_premium': bool(patron.estPremium),
            'surface_min': patron.surfaceMin,
            'surface_max': patron.surfaceMax,
            'materiel': patron.materiel or '',
            'matiere_requise': patron.matiere_requise or '',
            'photo_url': patron.photo_url,
        },
        'etapes': [
            {
                'numero': e.numero,
                'titre': e.titre,
                'description': e.description or '',
                'video_url': e.video_url or '',
                'conseil': e.conseil or '',
                'materiaux_etape': e.materiaux_etape or '',
                'image_url': e.image_url,
            }
            for e in patron.etapes.order_by('numero')
        ],
        'pieces': [
            {
                'nom': p.nom,
                'quantite': p.quantite,
                'largeur_cm': p.largeur_cm,
                'hauteur_cm': p.hauteur_cm,
                'svg': _read_svg(p),
            }
            for p in patron.pieces.all()
        ],
    }

    payload = json.dumps(data, ensure_ascii=False, indent=2)
    resp = HttpResponse(payload, content_type='application/json; charset=utf-8')
    resp['Content-Disposition'] = f'attachment; filename="patron-{_patron_slug(patron)}.json"'
    return resp


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

    # Vérification souple : on ne peut pas démarrer un nouveau projet sans e-mail
    # vérifié. Un projet déjà commencé reste accessible.
    projet_existant = ProgressionProjet.objects.filter(utilisateur=request.user, patron=patron).exists()
    if not projet_existant and not request.user.email_verifie:
        return redirect(reverse('patron_detail', kwargs={'pk': patron_pk}) + '?verif_requise=1')

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

    cache_key = f'qrcode_{hashlib.md5(url.encode()).hexdigest()}'
    png_bytes = cache.get(cache_key)
    if png_bytes is None:
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
        png_bytes = buf.getvalue()
        cache.set(cache_key, png_bytes, 60 * 60 * 24 * 7)  # 7 jours

    return HttpResponse(png_bytes, content_type='image/png')


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


def communaute_active_requise(view_func):
    """Bloque l'accès à une vue tant que la communauté est désactivée (bêta test).
    Le code des vues reste intact ; il suffit de remettre COMMUNAUTE_ACTIVE=True
    pour tout réactiver. Répond en JSON pour les appels AJAX, en page sinon."""
    from functools import wraps
    from django.conf import settings as dj_settings

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if getattr(dj_settings, 'COMMUNAUTE_ACTIVE', True):
            return view_func(request, *args, **kwargs)
        is_ajax = (
            request.headers.get('x-requested-with') == 'XMLHttpRequest'
            or 'application/json' in request.headers.get('accept', '')
        )
        if is_ajax:
            return JsonResponse(
                {'error': 'La communauté est désactivée pendant la phase de bêta test.'},
                status=403,
            )
        return render(request, 'core/communaute_desactivee.html', status=403)

    return _wrapped


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

        try:
            image_fichier = decode_base64_image(request.POST.get('photo_data', ''), 'post')
        except ValueError:
            return render(request, 'core/creer_post.html', {
                'patrons': Patron.objects.all(),
                'error': "L'image fournie est invalide. Choisis une photo (PNG/JPG/WEBP).",
            })

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

    # Nombre de patrons compatibles par tissu (surfaceExploitable >= surfaceMin).
    # On trie les surfaces minimales une seule fois, puis bisect compte en O(log n)
    # par tissu au lieu d'une boucle imbriquée patrons × tissus.
    import bisect
    surfaces_min = sorted(Patron.objects.values_list('surfaceMin', flat=True))
    vetements_data = []
    for v in vetements:
        nb_compatibles = bisect.bisect_right(surfaces_min, v.surfaceExploitable)
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
        email = (request.POST.get('email') or '').strip()
        password = request.POST.get('password') or ''

        if not email or not password:
            return render(request, 'core/inscription.html', {
                'error': "L'adresse e-mail et le mot de passe sont obligatoires.",
                'email': email,
            })

        if Utilisateur.objects.filter(email__iexact=email).exists():
            return render(request, 'core/inscription.html', {
                'error': "Un compte existe déjà avec cette adresse e-mail.",
                'email': email,
            })

        # Validation du mot de passe selon les règles Django (longueur, robustesse…).
        try:
            validate_password(password)
        except DjangoValidationError as e:
            return render(request, 'core/inscription.html', {
                'error': ' '.join(e.messages),
                'email': email,
            })

        # On sauvegarde l'email et le mdp dans la session
        request.session['reg_email'] = email
        request.session['reg_password'] = password
        return redirect('inscription_etape1')

    return render(request, 'core/inscription.html')

AVATAR_FILENAMES = [f'image {i}.png' for i in range(11, 27)]

def inscription_etape1(request):
    # Garde : si l'étape 0 n'a pas été faite (session expirée, accès direct),
    # on renvoie au début plutôt que de crasher plus loin.
    if not request.session.get('reg_email'):
        return redirect('inscription')

    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        avatar = request.POST.get('avatar', 'image 11.png')

        context = {'avatars': AVATAR_FILENAMES, 'username': username}

        if not username:
            context['error'] = "Choisis un nom d'utilisateur."
            return render(request, 'core/inscription_etape1.html', context)

        if Utilisateur.objects.filter(username__iexact=username).exists():
            context['error'] = "Ce nom d'utilisateur est déjà pris."
            return render(request, 'core/inscription_etape1.html', context)

        request.session['reg_username'] = username
        request.session['reg_avatar'] = avatar
        return redirect('inscription_etape2')

    return render(request, 'core/inscription_etape1.html', {'avatars': AVATAR_FILENAMES})

def inscription_etape2(request):
    # Garde : étapes précédentes obligatoires.
    if not request.session.get('reg_email') or not request.session.get('reg_username'):
        return redirect('inscription')

    if request.method == 'POST':
        # On sauvegarde le niveau
        request.session['reg_niveau'] = request.POST.get('experience_level')
        return redirect('inscription_etape3')

    return render(request, 'core/inscription_etape2.html')

def inscription_etape3(request):
    # 1. On récupère toutes les infos des étapes précédentes dans la session
    email = request.session.get('reg_email')
    password = request.session.get('reg_password')
    username = request.session.get('reg_username')

    # Garde : si la session a expiré ou si l'on accède directement à cette URL,
    # les données essentielles manquent → on recommence proprement (évite un 500).
    if not email or not password or not username:
        return redirect('inscription')

    if request.method == 'POST':
        niveau = request.session.get('reg_niveau')
        avatar = request.session.get('reg_avatar', 'image 11.png')

        # 2. On récupère les cases cochées
        cibles_list = request.POST.getlist('target')
        cibles_str = ", ".join(cibles_list)

        # 3. Consentement RGPD obligatoire : sans acceptation explicite, pas de compte.
        consentement = request.POST.get('consentement_rgpd') == 'on'
        if not consentement:
            return render(request, 'core/inscription_etape3.html', {
                'error': "Vous devez accepter la politique de confidentialité pour créer votre compte.",
            })

        # 4. Revalidation anti-collision juste avant la création : un autre compte
        # a pu prendre ce pseudo / cet e-mail entre l'étape 1 et maintenant → évite un 500.
        if (Utilisateur.objects.filter(username__iexact=username).exists()
                or Utilisateur.objects.filter(email__iexact=email).exists()):
            return render(request, 'core/inscription.html',
                          {'error': "Ce compte existe déjà. Essayez de vous connecter."})

        # 5. On crée le compte (avec preuve horodatée du consentement RGPD)
        nouvel_utilisateur = Utilisateur.objects.create_user(
            username=username,
            email=email,
            password=password,
            niveau_couture=niveau,
            envies_creation=cibles_str,
            avatar=avatar,
            consentementRGPD=True,
            dateConsentementRGPD=timezone.now(),
        )

        # 6. On nettoie la session
        keys_to_delete = ['reg_email', 'reg_password', 'reg_username', 'reg_niveau', 'reg_avatar']
        for key in keys_to_delete:
            if key in request.session:
                del request.session[key]

        # 7. On envoie l'e-mail de vérification (vérification souple)
        _envoyer_email_verification(request, nouvel_utilisateur)

        # 8. On connecte l'utilisateur automatiquement et on l'envoie sur l'accueil
        login(request, nouvel_utilisateur)
        return redirect('home')

    return render(request, 'core/inscription_etape3.html')


# ── RGPD : page légale, export et suppression des données ───────────────────

def politique_confidentialite(request):
    """Politique de confidentialité (page publique, accessible sans connexion)."""
    return render(request, 'core/politique_confidentialite.html')


@login_required
def exporter_donnees(request):
    """Droit d'accès et à la portabilité (RGPD art. 15 & 20) :
    renvoie l'ensemble des données personnelles de l'utilisateur au format JSON."""
    user = request.user

    def _dt(value):
        return value.isoformat() if value else None

    data = {
        'compte': {
            'pseudo': user.username,
            'email': user.email,
            'prenom': user.first_name,
            'nom': user.last_name,
            'bio': user.bio,
            'avatar': user.avatar,
            'niveau_couture': user.niveau_couture,
            'envies_creation': user.envies_creation,
            'solde_pieces': user.soldePieces,
            'date_inscription': _dt(user.date_joined),
            'derniere_connexion': _dt(user.last_login),
            'consentement_rgpd': user.consentementRGPD,
            'date_consentement_rgpd': _dt(user.dateConsentementRGPD),
        },
        'tissus': [
            {
                'nom': v.nomVetement,
                'type': v.typeVetement,
                'surface_totale_m2': v.surfaceTotale,
                'surface_exploitable_m2': v.surfaceExploitable,
                'etat': v.etat,
                'qualite': v.qualite,
                'couleur': v.couleur,
                'matiere': v.matiere,
            }
            for v in Vetement.objects.filter(utilisateur=user)
        ],
        'projets': [
            {
                'patron': prog.patron.titre,
                'etape_actuelle': prog.etape_actuelle,
                'termine': prog.termine,
                'date_debut': _dt(prog.date_debut),
                'date_derniere_activite': _dt(prog.date_derniere_activite),
            }
            for prog in ProgressionProjet.objects.filter(utilisateur=user).select_related('patron')
        ],
        'patrons_crees': [
            {'titre': p.titre, 'type': p.typeObjet, 'difficulte': p.difficulte}
            for p in Patron.objects.filter(createur=user)
        ],
        'posts_communaute': [
            {
                'titre': post.titre,
                'description': post.description,
                'type_creation': post.type_creation,
                'niveau': post.niveau,
                'date_creation': _dt(post.date_creation),
                'nb_vues': post.nb_vues,
            }
            for post in PostCommunaute.objects.filter(utilisateur=user)
        ],
        'commentaires': [
            {'post': c.post.titre, 'contenu': c.contenu, 'date': _dt(c.date_creation)}
            for c in CommentairePost.objects.filter(utilisateur=user).select_related('post')
        ],
        'likes_donnes': [
            {'post': lp.post.titre, 'date': _dt(lp.date_like)}
            for lp in LikePost.objects.filter(utilisateur=user).select_related('post')
        ],
        'abonnements': [s.suivi.username for s in Suivi.objects.filter(suiveur=user).select_related('suivi')],
        'badges': [
            {'nom': b.nom, 'date_obtention': _dt(b.date_obtention)}
            for b in Badge.objects.filter(utilisateur=user)
        ],
    }

    payload = json.dumps(data, ensure_ascii=False, indent=2)
    response = HttpResponse(payload, content_type='application/json; charset=utf-8')
    filename = f'mes-donnees-lafabrique-{user.username}.json'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def supprimer_compte(request):
    """Droit à l'effacement (RGPD art. 17) : supprime définitivement le compte
    et toutes les données liées (cascade), après confirmation du mot de passe."""
    if request.method == 'POST':
        password = request.POST.get('password', '')
        if not request.user.check_password(password):
            return render(request, 'core/supprimer_compte.html', {
                'error': "Mot de passe incorrect. Suppression annulée.",
            })
        user = request.user
        logout(request)
        user.delete()
        return redirect('home')

    return render(request, 'core/supprimer_compte.html')


# ── Vérification d'e-mail (souple) ──────────────────────────────────────────

EMAIL_VERIF_SALT = 'email-verification'
EMAIL_VERIF_MAX_AGE = 60 * 60 * 24 * 7  # 7 jours


def _smtp_configure():
    """Vrai si l'envoi d'e-mails peut réellement aboutir (backend non-SMTP, ou SMTP avec hôte)."""
    backend = getattr(dj_settings, 'EMAIL_BACKEND', '')
    if 'smtp' not in backend:
        return True  # console / locmem / autre : pas de réseau, toujours OK
    return bool(getattr(dj_settings, 'EMAIL_HOST', ''))


def _envoyer_email_verification(request, user):
    """Envoie un e-mail de vérification avec un lien signé.

    L'envoi se fait dans un thread d'arrière-plan : la requête ne doit JAMAIS
    bloquer ni planter à cause de l'e-mail (un SMTP lent/indisponible tuerait
    sinon le worker → 500). Toute erreur est journalisée dans la console serveur.
    """
    if not user.email:
        return

    if not _smtp_configure():
        logger.warning(
            "SMTP non configuré (EMAIL_HOST vide) : e-mail de vérification NON envoyé à %s. "
            "Définir les variables EMAIL_HOST/EMAIL_HOST_USER/EMAIL_HOST_PASSWORD en production.",
            user.email,
        )
        return

    token = signing.dumps({'uid': user.pk}, salt=EMAIL_VERIF_SALT)
    lien = request.build_absolute_uri(reverse('verifier_email', args=[token]))
    sujet = "Confirmez votre adresse e-mail — La Fabrique"
    message = (
        f"Bonjour {user.username},\n\n"
        "Bienvenue dans l'atelier ! Confirmez votre adresse e-mail en cliquant "
        "sur le lien ci-dessous :\n\n"
        f"{lien}\n\n"
        "Ce lien est valable 7 jours. Si vous n'êtes pas à l'origine de cette "
        "inscription, ignorez cet e-mail.\n\n"
        "L'équipe La Fabrique"
    )
    destinataire = user.email

    def _tache_envoi():
        try:
            send_mail(sujet, message, None, [destinataire], fail_silently=False)
            logger.info("E-mail de vérification envoyé à %s", destinataire)
        except Exception:
            logger.exception("Échec de l'envoi de l'e-mail de vérification à %s", destinataire)

    threading.Thread(target=_tache_envoi, daemon=True).start()


def verifier_email(request, token):
    """Page publique atteinte via le lien e-mail : valide le token et marque l'adresse vérifiée."""
    try:
        data = signing.loads(token, salt=EMAIL_VERIF_SALT, max_age=EMAIL_VERIF_MAX_AGE)
        user = Utilisateur.objects.get(pk=data['uid'])
    except (signing.BadSignature, signing.SignatureExpired, Utilisateur.DoesNotExist, KeyError, TypeError):
        return render(request, 'core/email_verifie.html', {'success': False})

    if not user.email_verifie:
        user.email_verifie = True
        user.save(update_fields=['email_verifie'])
    return render(request, 'core/email_verifie.html', {'success': True})


@login_required
def renvoyer_verification(request):
    """Renvoie l'e-mail de vérification (depuis le bandeau). POST uniquement."""
    if request.method != 'POST':
        return redirect('dashboard')
    if not request.user.email_verifie:
        _envoyer_email_verification(request, request.user)
    # On revient sur la page d'origine en signalant l'envoi (next validé = pas d'open redirect).
    next_url = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse('dashboard')
    sep = '&' if '?' in next_url else '?'
    return redirect(f'{next_url}{sep}email_renvoye=1')


@login_required
def diagnostic_email(request):
    """Page de diagnostic e-mail réservée au superadmin (utile quand le shell
    Render n'est pas disponible). Usage : /diagnostic-email/?to=mon@email.com

    Affiche la config chargée + teste connexion et envoi, en texte brut.
    """
    if not request.user.is_superuser:
        from django.http import Http404
        raise Http404()

    from django.core.mail import get_connection, EmailMessage

    def _mask(v):
        if not v:
            return '(vide)'
        return v[:2] + '…' + v[-2:] if len(v) > 4 else '••••'

    dest = request.GET.get('to', '').strip()
    lignes = []
    lignes.append("=== Configuration e-mail chargée ===")
    lignes.append(f"DEBUG               = {dj_settings.DEBUG}")
    lignes.append(f"EMAIL_BACKEND       = {dj_settings.EMAIL_BACKEND}")
    lignes.append(f"BREVO_API_KEY       = {_mask(getattr(dj_settings, 'BREVO_API_KEY', ''))} "
                  f"{'(API HTTP active ✓)' if getattr(dj_settings, 'BREVO_API_KEY', '') else '(non définie → SMTP)'}")
    lignes.append(f"EMAIL_HOST          = {dj_settings.EMAIL_HOST or '(vide)'}")
    lignes.append(f"EMAIL_PORT          = {dj_settings.EMAIL_PORT}")
    lignes.append(f"EMAIL_USE_TLS       = {dj_settings.EMAIL_USE_TLS}")
    lignes.append(f"EMAIL_USE_SSL       = {getattr(dj_settings, 'EMAIL_USE_SSL', False)}")
    lignes.append(f"EMAIL_HOST_USER     = {dj_settings.EMAIL_HOST_USER or '(vide)'}")
    lignes.append(f"EMAIL_HOST_PASSWORD = {_mask(dj_settings.EMAIL_HOST_PASSWORD)}")
    lignes.append(f"EMAIL_TIMEOUT       = {getattr(dj_settings, 'EMAIL_TIMEOUT', None)}")
    lignes.append(f"DEFAULT_FROM_EMAIL  = {dj_settings.DEFAULT_FROM_EMAIL}")

    if 'console' in dj_settings.EMAIL_BACKEND:
        lignes.append("\n⚠ Backend = console : aucun e-mail réel n'est envoyé (DEBUG=True).")
    elif not dj_settings.EMAIL_HOST:
        lignes.append("\n✗ Backend SMTP mais EMAIL_HOST vide → variables non chargées "
                      "(vérifier les noms sur Render puis REDÉPLOYER).")

    if not dest:
        lignes.append("\nAjoute ?to=ton@email.com à l'URL pour tester un envoi réel.")
        return HttpResponse('\n'.join(lignes), content_type='text/plain; charset=utf-8')

    lignes.append("\n=== Test de connexion SMTP ===")
    try:
        conn = get_connection(fail_silently=False)
        conn.open()
        conn.close()
        lignes.append("✓ Connexion au serveur SMTP réussie.")
    except Exception as e:
        lignes.append(f"✗ Échec de connexion : {type(e).__name__}: {e}")
        lignes.append("Causes : mauvais host/port, identifiants incorrects, port bloqué (essayer 2525), TLS/SSL.")
        return HttpResponse('\n'.join(lignes), content_type='text/plain; charset=utf-8')

    lignes.append(f"\n=== Envoi de test à {dest} ===")
    try:
        n = EmailMessage(subject="Test d'envoi — La Fabrique",
                         body="Si vous lisez ceci, l'envoi fonctionne. 🎉",
                         to=[dest]).send(fail_silently=False)
        if n:
            lignes.append(f"✓ E-mail accepté par le serveur ({n}). Vérifie réception ET spams.")
        else:
            lignes.append("✗ 0 message envoyé (refus silencieux).")
    except Exception as e:
        lignes.append(f"✗ Échec de l'envoi : {type(e).__name__}: {e}")
        lignes.append(f"Probable : l'expéditeur ({dj_settings.DEFAULT_FROM_EMAIL}) n'est pas "
                      "une adresse VÉRIFIÉE chez ton fournisseur (Brevo/Mailjet).")

    return HttpResponse('\n'.join(lignes), content_type='text/plain; charset=utf-8')


@login_required
def detail_vetement(request, pk):
    vetement = get_object_or_404(Vetement, pk=pk, utilisateur=request.user)

    if request.method == 'POST':
        vetement.nomVetement = request.POST.get('nom_vetement', vetement.nomVetement).strip() or vetement.nomVetement
        vetement.typeVetement = request.POST.get('clothing_type', vetement.typeVetement)
        try:
            vetement.qualite = int(request.POST.get('qualite', vetement.qualite))
        except (ValueError, TypeError):
            pass
        vetement.couleur = request.POST.get('couleur', vetement.couleur)
        vetement.matiere = request.POST.get('material', vetement.matiere)

        try:
            nouvelle_photo = decode_base64_image(request.POST.get('photo_data', ''), 'vetement')
        except ValueError:
            return render(request, 'core/detail_vetement.html', {
                'vetement': vetement,
                'error': "L'image fournie est invalide.",
            })
        if nouvelle_photo:
            vetement.photoURL = nouvelle_photo

        vetement.save()
        return redirect('mes_tissus')

    return render(request, 'core/detail_vetement.html', {'vetement': vetement})
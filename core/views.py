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
from django.core.validators import validate_email
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


# Une teinte par badge, pour que les médaillons du tableau de bord ne soient
# pas tous de la même couleur. arc = anneau de progression + libellé,
# c1/c2 = dégradé de la pastille, bg/border = fond de la carte.
BADGE_COLORS = {
    'Premier Projet':    {'arc': '#C98600', 'c1': '#FFDC5E', 'c2': '#F0A800', 'bg': '#FFFAE6', 'border': '#F5E3AF'},
    '5 Projets':         {'arc': '#D1591F', 'c1': '#FF9F45', 'c2': '#F2622A', 'bg': '#FFF3EC', 'border': '#F7DDCD'},
    '10 Projets':        {'arc': '#8A5A12', 'c1': '#D9A441', 'c2': '#8A5A12', 'bg': '#F8F1E4', 'border': '#E6D6B8'},
    '1er com':           {'arc': '#2E6FB0', 'c1': '#6FB6F2', 'c2': '#2E6FB0', 'bg': '#EEF6FF', 'border': '#D3E6F8'},
    '5 com':             {'arc': '#0E7F7A', 'c1': '#5BD9D4', 'c2': '#12857F', 'bg': '#ECFAF8', 'border': '#CDEDEA'},
    'Premier Like':      {'arc': '#C2405A', 'c1': '#FF8FA8', 'c2': '#D4365A', 'bg': '#FFF0F3', 'border': '#F7D6DD'},
    '10 Likes':          {'arc': '#C2361B', 'c1': '#FF7A45', 'c2': '#D93E12', 'bg': '#FFF1EC', 'border': '#F8D6C9'},
    'Première Création': {'arc': '#6B45F5', 'c1': '#9C84FF', 'c2': '#6B45F5', 'bg': '#F6F3FF', 'border': '#E1D9FB'},
    'Artiste':           {'arc': '#9A3FA8', 'c1': '#D07BE0', 'c2': '#8E31A0', 'bg': '#FBF0FD', 'border': '#EEDAF3'},
    'Éco Warrior':       {'arc': '#128F4A', 'c1': '#5BD98A', 'c2': '#128F4A', 'bg': '#F3FAF5', 'border': '#D8EEE1'},
}

BADGE_DEFINITIONS = [
    {'famille': 'projets',    'nom': 'Premier Projet',    'emoji': '🏆', 'description': '1er projet terminé',        'condition': 'Terminer 1 projet'},
    {'famille': 'projets',    'nom': '5 Projets',         'emoji': '⭐', 'description': 'Créateur confirmé',           'condition': 'Terminer 5 projets'},
    {'famille': 'projets',    'nom': '10 Projets',        'emoji': '🥇', 'description': 'Grand créateur',             'condition': 'Terminer 10 projets'},
    {'famille': 'echanges',   'nom': '1er com',           'emoji': '💬', 'description': 'Actif dans la communauté',   'condition': 'Poster 1 commentaire'},
    {'famille': 'echanges',   'nom': '5 com',            'emoji': '🗣️', 'description': 'Très bavard !',             'condition': 'Poster 5 commentaires'},
    {'famille': 'soutien',    'nom': 'Premier Like',      'emoji': '❤️', 'description': 'Soutien de la communauté',  'condition': 'Donner 1 like'},
    {'famille': 'soutien',    'nom': '10 Likes',          'emoji': '🔥', 'description': 'Fan de la première heure',   'condition': 'Donner 10 likes'},
    {'famille': 'creations',  'nom': 'Première Création', 'emoji': '✨', 'description': 'Première création partagée', 'condition': 'Partager 1 création'},
    {'famille': 'creations',  'nom': 'Artiste',           'emoji': '🎨', 'description': 'Créateur prolifique',        'condition': 'Partager 5 créations'},
    {'famille': 'boutique',   'nom': 'Éco Warrior',       'emoji': '🌿', 'description': 'Badge exclusif',             'condition': 'Acheter dans la boutique'},
]

BADGE_COLOR_DEFAUT = {'arc': '#6B45F5', 'c1': '#9C84FF', 'c2': '#6B45F5', 'bg': '#F6F3FF', 'border': '#E1D9FB'}


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


def service_worker(request):
    """Sert le service worker depuis la racine du domaine.

    Le scope d'un service worker est limité au dossier qui le sert : servi
    depuis /static/..., il ne pourrait contrôler que /static/. On le lit donc
    depuis le disque et on le renvoie sur l'URL racine /service-worker.js,
    avec un en-tête Service-Worker-Allowed explicite et sans cache — un SW
    obsolète en cache empêcherait les mises à jour de se propager.
    """
    sw_path = dj_settings.BASE_DIR / 'core' / 'static' / 'core' / 'js' / 'service-worker.js'
    with open(sw_path, 'rb') as f:
        content = f.read()
    response = HttpResponse(content, content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'
    return response


# Paliers de l'atelier affichés sur le tableau de bord : (points requis, nom).
ATELIER_LEVELS = [
    (0,    'Première aiguille'),
    (120,  'Fil conducteur'),
    (320,  'Main sûre'),
    (620,  'Belle ouvrage'),
    (1000, 'Artisan du textile'),
    (1500, "Maître d'atelier"),
]


def _niveau_atelier(nb_vetements, nb_etapes, nb_projets):
    """Palier d'atelier calculé sur l'activité réelle : tissus scannés, étapes
    de couture réalisées et projets menés à terme."""
    points = nb_vetements * 20 + nb_etapes * 10 + nb_projets * 60

    index = 0
    for i, (seuil, _) in enumerate(ATELIER_LEVELS):
        if points >= seuil:
            index = i

    seuil_courant, nom = ATELIER_LEVELS[index]
    if index + 1 < len(ATELIER_LEVELS):
        seuil_suivant = ATELIER_LEVELS[index + 1][0]
        pourcentage = round((points - seuil_courant) / (seuil_suivant - seuil_courant) * 100)
        restants = seuil_suivant - points
        niveau_suivant = index + 2
    else:
        pourcentage, restants, niveau_suivant = 100, 0, None

    return {
        'numero': index + 1,
        'nom': nom,
        'points': points,
        'pourcentage': pourcentage,
        'points_restants': restants,
        'niveau_suivant': niveau_suivant,
    }


# Couleurs de tissu saisies au scan → pastille affichée sur le tableau de bord.
COULEUR_HEX = {
    'ivoire': '#F2EDD7', 'beige': '#D4B896', 'camel': '#C19A6B',
    'terracotta': '#C2694F', 'rouge': '#CC2936', 'bordeaux': '#7B0C0C',
    'rose': '#F4A0B0', 'mauve': '#967BB6', 'lavande': '#B57EDC',
    'marine': '#1F305C', 'bleu ciel': '#89CFF0', 'vert sauge': '#9CAF88',
    'vert forêt': '#228B22', 'moutarde': '#C8A415', 'gris ardoise': '#708090',
    'noir': '#1A1A1A', 'blanc': '#F0EEE8', 'gris': '#A0A09A',
}


def _couleur_hex(couleur):
    if not couleur:
        return '#EDE4D6'
    return COULEUR_HEX.get(couleur.split(',')[0].strip().lower(), '#EDE4D6')


def _couleur_claire(hex_couleur):
    """Vrai si un texte sombre est plus lisible que du blanc sur cet aplat.

    Luminance perçue (ITU-R BT.601) : les tissus clairs (ivoire, beige…)
    reçoivent une étiquette encre, les foncés (marine, noir…) une blanche.
    """
    try:
        r, g, b = (int(hex_couleur[i:i + 2], 16) for i in (1, 3, 5))
    except (ValueError, IndexError):
        return True
    return (r * 299 + g * 587 + b * 114) / 1000 > 150


@login_required
def dashboard(request):
    user = request.user
    OBJECTIF_M2 = 15.0

    # ── Banque de tissus ────────────────────────────────────────────────
    vetements_user = list(Vetement.objects.filter(utilisateur=user).order_by('-id'))
    nb_vetements = len(vetements_user)
    surface_totale = round(sum(v.surfaceExploitable for v in vetements_user), 2)
    co2_economise = round(sum(calculer_co2_vetement(v) for v in vetements_user), 1)

    surface_pourcentage = min(100, round((surface_totale / OBJECTIF_M2) * 100))
    surface_restante = round(max(0, OBJECTIF_M2 - surface_totale), 1)
    # Défi « banque de tissus » : 5 segments de 20 % chacun.
    defi_segments = [surface_pourcentage >= (i + 1) * 20 for i in range(5)]

    apercu_tissus = [
        {'photo': v.photo_url, 'hex': _couleur_hex(v.couleur)}
        for v in vetements_user[:3]
    ]
    reste_tissus = max(0, nb_vetements - len(apercu_tissus))

    # ── Projets (en cours + terminés) ───────────────────────────────────
    progressions = (
        ProgressionProjet.objects
        .filter(utilisateur=user)
        .select_related('patron')
        .annotate(nb_etapes=Count('patron__etapes'))
        .order_by('-date_derniere_activite')
    )

    projet_en_cours = None
    patrons_engages = set()
    nb_projets_termines = 0
    nb_etapes_realisees = 0

    for prog in progressions:
        p = prog.patron
        patrons_engages.add(p.pk)

        if prog.termine:
            nb_projets_termines += 1
            nb_etapes_realisees += prog.nb_etapes
            continue

        # Étapes déjà validées d'un projet en cours = étape courante − 1.
        nb_etapes_realisees += max(0, prog.etape_actuelle - 1)
        if projet_en_cours is None:  # le plus récemment travaillé
            etape = p.etapes.filter(numero=prog.etape_actuelle).first()
            projet_en_cours = {
                'patron_id': p.pk,
                'titre': p.titre,
                'image': p.photo_url,
                'etape_actuelle': prog.etape_actuelle,
                'total_etapes': prog.nb_etapes,
                'etape_titre': etape.titre if etape else 'Reprendre là où tu en étais',
                'progression_pct': (
                    round((prog.etape_actuelle - 1) / prog.nb_etapes * 100)
                    if prog.nb_etapes else 0
                ),
            }

    # ── Patrons réalisables avec les tissus disponibles ─────────────────
    patrons_all = list(Patron.objects.all())
    nb_patrons_total = len(patrons_all)
    realisables = [p for p in patrons_all if p.surfaceMin and p.surfaceMin <= surface_totale]
    nb_patrons_realisables = len(realisables)
    patrons_pourcentage = (
        round(nb_patrons_realisables / nb_patrons_total * 100) if nb_patrons_total else 0
    )

    patrons_suggeres = [
        {
            'id': p.pk,
            'titre': p.titre,
            'image': p.photo_url,
            'duree': p.duree or '?',
            'surface': p.surfaceMin,
        }
        for p in sorted(
            (p for p in realisables if p.pk not in patrons_engages),
            key=lambda p: p.surfaceMin,
        )[:6]
    ]

    # ── Badges ──────────────────────────────────────────────────────────
    badges_earned = {b.nom: b for b in Badge.objects.filter(utilisateur=user)}
    has_eco_warrior = 'Éco Warrior' in badges_earned

    nb_projets_badge      = nb_projets_termines
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
            'famille': bd['famille'],
            'emoji': bd['emoji'],
            'couleur': BADGE_COLORS.get(bd['nom'], BADGE_COLOR_DEFAUT),
            'description': bd['description'],
            'condition': bd['condition'],
            'earned': earned is not None,
            'date_obtention': earned.date_obtention if earned else None,
            'progress_current': current,
            'progress_max': max_val,
            'progress_pct': pct,
        })

    # Les 3 badges les plus proches d'être décrochés (complétés par les acquis).
    # À progression égale on évite de montrer trois badges de la même famille :
    # sinon un compte neuf n'affiche que les trois badges « projets ».
    candidats = (
        sorted((b for b in badges_display if not b['earned']),
               key=lambda b: -b['progress_pct'])
        + [b for b in badges_display if b['earned']]
    )
    badges_a_portee, familles_vues = [], set()
    for passe in (1, 2):  # 1re passe : une famille au plus ; 2e : on complète
        for b in candidats:
            if len(badges_a_portee) == 3:
                break
            if b in badges_a_portee:
                continue
            if passe == 1 and b['famille'] in familles_vues:
                continue
            badges_a_portee.append(b)
            familles_vues.add(b['famille'])

    context = {
        'aujourd_hui': timezone.localdate(),
        'surface_totale': surface_totale,
        'surface_objectif': OBJECTIF_M2,
        'surface_pourcentage': surface_pourcentage,
        'surface_restante': surface_restante,
        'defi_segments': defi_segments,
        'nb_vetements': nb_vetements,
        'apercu_tissus': apercu_tissus,
        'reste_tissus': reste_tissus,
        'credits': user.soldePieces,
        'co2_economise': co2_economise,
        'niveau': _niveau_atelier(nb_vetements, nb_etapes_realisees, nb_projets_termines),
        'projet_en_cours': projet_en_cours,
        'nb_projets_termines': nb_projets_termines,
        'nb_etapes_realisees': nb_etapes_realisees,
        'nb_patrons_total': nb_patrons_total,
        'nb_patrons_realisables': nb_patrons_realisables,
        'patrons_pourcentage': patrons_pourcentage,
        'patrons_suggeres': patrons_suggeres,
        'badges_display': badges_display,
        'badges_a_portee': badges_a_portee,
        'nb_badges_obtenus': len(badges_earned),
        'nb_badges_total': len(BADGE_DEFINITIONS),
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


# Types de défauts posés dans l'éditeur (le modèle n'en stocke que deux
# surfaces, cf. _analyser_face ; ces libellés servent au ticket de fin).
DEFAUT_LABELS = {
    'tache':  'Tache',
    'trou':   'Trou',
    'usure':  'Usure',
    'ourlet': 'Ourlet',
    'autre':  'Autre',
}
FACE_LABELS = {'avant': 'Face avant', 'arriere': 'Face arrière'}

# Part de la surface détourée perdue en coutures, ourlets et bords non
# exploitables. Constante volontairement prudente : c'est une estimation,
# pas une mesure — elle est déduite de la surface exploitable et affichée
# telle quelle sur le ticket de fin.
CHUTES_BORDS_RATIO = 0.08


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
    lignes = []
    for d in defects:
        # rayon stocké normalisé par rapport à la largeur de l'image
        r_cm = float(d.get('r', 0)) * img_w * cm_per_px
        circle_m2 = math.pi * r_cm * r_cm / 10000.0
        # Le modèle ne connaît que deux surfaces perdues : les trous d'un côté,
        # tout le reste (tache, usure, ourlet, autre) de l'autre. Le type précis
        # reste stocké dans le JSON `defauts` pour l'affichage.
        if d.get('type') == 'trou':
            trou_m2 += circle_m2
        else:
            tache_m2 += circle_m2
        lignes.append({
            'type': d.get('type', 'tache'),
            'libelle': DEFAUT_LABELS.get(d.get('type'), 'Défaut'),
            'face': FACE_LABELS.get(prefix, prefix),
            'taille_cm': round(r_cm * 2),
            'perte_m2': circle_m2,
        })

    return {
        'area_m2': area_m2,
        'tache_m2': tache_m2,
        'trou_m2': trou_m2,
        'photo_data': request.POST.get(f'photo_data_{prefix}', ''),
        'cm_per_px': cm_per_px,
        'polygon': polygon,
        'defects': defects,
        'lignes': lignes,
    }


@login_required
def ajout_textile(request):
    context = {'result_ready': False, 'rembg_enabled': dj_settings.REMBG_DETOURAGE_ENABLED}

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
                lignes_defauts = face_av['lignes'] + face_ar['lignes']
            else:
                # Face arrière ignorée : on suppose l'arrière identique à l'avant.
                surface_totale_m2 = face_av['area_m2'] * 2
                tache_m2 = face_av['tache_m2'] * 2
                trou_m2 = face_av['trou_m2'] * 2
                lignes_defauts = face_av['lignes']

            total_defect_area_m2 = tache_m2 + trou_m2
            chutes_m2 = surface_totale_m2 * CHUTES_BORDS_RATIO
            usable_area_m2 = max(0, surface_totale_m2 - total_defect_area_m2 - chutes_m2)
            percentage = int((usable_area_m2 / surface_totale_m2) * 100) if surface_totale_m2 > 0 else 0

            # SAUVEGARDE DANS LA BASE DE DONNÉES
            type_vetement = request.POST.get('clothing_type', 'inconnu')
            nom_vetement = request.POST.get('nom_vetement', '').strip() or f"{type_vetement.capitalize()} de {request.user.username}"
            qualite = int(request.POST.get('qualite', 3))
            couleur = request.POST.get('couleur', '')
            matiere_raw = request.POST.get('material', 'coton:100').strip() or 'coton:100'
            numero_identite = request.POST.get('numero_identite', '').strip()

            photo_fichier = decode_base64_image(face_av['photo_data'], 'vetement')

            vetement = Vetement.objects.create(
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
                numeroIdentite=numero_identite or None,
                echelle_cm_px=face_av['cm_per_px'],
                detourage=json.dumps(face_av['polygon']),
                defauts=json.dumps(face_av['defects']),
            )

            coins_earned = 3
            request.user.soldePieces += coins_earned
            request.user.save()

            # ── Ticket de fin ──
            matieres_txt = ' · '.join(
                f"{MATERIAL_LABELS.get(n.strip().lower(), n.strip().capitalize())} {p} %"
                for n, p in (part.split(':', 1) for part in matiere_raw.split(',') if ':' in part)
            )
            couleurs_txt = ' · '.join(c.strip() for c in couleur.split(',') if c.strip())
            nb_patrons = Patron.objects.filter(surfaceMin__lte=usable_area_m2).count()

            context.update({
                'result_ready': True,
                'usable_area': round(usable_area_m2, 2),
                'percentage': percentage,
                'coins_earned': coins_earned,
                'ticket': {
                    'ref': f'{vetement.pk:06d}',
                    'date': timezone.localdate().strftime('%d.%m.%y'),
                    'nom': nom_vetement,
                    'matieres': matieres_txt,
                    'couleurs': couleurs_txt,
                    'surface_totale': round(surface_totale_m2, 2),
                    'lignes': lignes_defauts,
                    'chutes': round(chutes_m2, 2),
                    'nb_patrons': nb_patrons,
                },
            })

        except (ValueError, json.JSONDecodeError, ZeroDivisionError):
            context['error'] = "Erreur dans le calcul de la surface. Recommence le détourage."

    return render(request, 'core/ajout_textile.html', context)


@login_required
def detourage_auto(request):
    """Détourage automatique côté serveur par segmentation IA (rembg).

    Appelée en AJAX depuis l'éditeur de photo ; en cas d'échec, de
    désactivation (REMBG_DETOURAGE_ENABLED=False) ou d'erreur quelconque,
    le JS retombe automatiquement sur l'ancien algorithme côté client
    (autoDetectPolygon dans ajout_textile.html).
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'method_not_allowed'}, status=405)

    if not dj_settings.REMBG_DETOURAGE_ENABLED:
        return JsonResponse({'success': False, 'error': 'disabled'}, status=503)

    try:
        photo_fichier = decode_base64_image(request.POST.get('photo_data', ''), 'detourage_tmp')
    except ValueError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    if photo_fichier is None:
        return JsonResponse({'success': False, 'error': 'image manquante'}, status=400)

    try:
        from core.detourage import auto_polygon_rembg
        polygon = auto_polygon_rembg(photo_fichier.read())
    except Exception:
        logger.exception('Échec du détourage automatique (rembg)')
        return JsonResponse({'success': False, 'error': 'echec_traitement'}, status=500)

    if not polygon:
        return JsonResponse({'success': False, 'error': 'aucun_contour'})

    return JsonResponse({'success': True, 'polygon': polygon})


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


# Types produits par le scanner (ajout_textile) → libellé affiché.
TYPE_VETEMENT_LABELS = {
    'tshirt': 'T-shirt', 'jean': 'Jean', 'hoodie': 'Hoodie', 'robe': 'Robe',
    'jupe': 'Jupe', 'manteau': 'Manteau', 'veste': 'Veste', 'blazer': 'Blazer',
    'pull': 'Pull', 'chemise': 'Chemise', 'short': 'Short', 'gilet': 'Gilet',
    'debardeur': 'Débardeur', 'combinaison': 'Combinaison', 'pyjama': 'Pyjama',
    'accessoire': 'Accessoire', 'autre': 'Autre',
}

MATIERE_HEX_DEFAUT = '#C7BCA8'

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


def _duree_minutes(duree):
    """Convertit une durée libre (« 1 h 30 », « 45 min », « 2h ») en minutes."""
    if not duree:
        return None
    txt = str(duree).lower().replace(' ', ' ')
    heures = re.search(r'(\d+(?:[.,]\d+)?)\s*h', txt)
    minutes = re.search(r'(\d+)\s*(?:min|m\b)', txt)
    total = 0.0
    if heures:
        total += float(heures.group(1).replace(',', '.')) * 60
        reste = re.search(r'h\s*(\d{1,2})\b', txt)
        if reste and not minutes:
            total += float(reste.group(1))
    if minutes:
        total += float(minutes.group(1))
    if total <= 0 and not heures and not minutes:
        return None
    return int(total)


def _pieces_gagnees(difficulte):
    """Pièces gagnées à la réalisation d'un patron, dérivées de sa difficulté."""
    return {1: 20, 2: 45, 3: 60}.get(difficulte, 20)


@login_required
def cours(request):
    """Onglet « Cours » de la barre de navigation — page encore vide."""
    return render(request, 'core/cours.html')


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
            'description': p.description or '',
            'image': p.photo_url,
            'compatibilite': _compatibilite(surface_user, p.surfaceMin),
            'tissu': p.typeObjet,
            'difficulte': p.difficulte,
            'difficulte_label': DIFFICULTE_LABELS.get(p.difficulte, str(p.difficulte)),
            'duree': p.duree or '?',
            'duree_min': _duree_minutes(p.duree),
            'surface_min': round(p.surfaceMin, 2),
            'pieces': _pieces_gagnees(p.difficulte),
            'est_premium': p.estPremium,
            'est_liked': p.pk in liked_ids,
            'en_cours': p.pk in en_cours_patron_ids,
        })

    projets_en_cours = []
    for prog in progressions_qs:
        p = prog.patron
        etapes = list(p.etapes.all().order_by('numero'))
        total_etapes = len(etapes)
        pct = round((prog.etape_actuelle / total_etapes) * 100) if total_etapes > 0 else 0
        etape_courante = next(
            (e for e in etapes if e.numero == prog.etape_actuelle), None
        )
        projets_en_cours.append({
            'patron_id': p.pk,
            'titre': p.titre,
            'image': p.photo_url,
            'etape_actuelle': prog.etape_actuelle,
            'etape_titre': etape_courante.titre if etape_courante else '',
            'etapes_range': range(total_etapes),
            'total_etapes': total_etapes,
            'progression_pct': pct,
            'date_derniere_activite': prog.date_derniere_activite,
            'difficulte_label': DIFFICULTE_LABELS.get(p.difficulte, str(p.difficulte)),
        })

    projets_termines_qs = (
        ProgressionProjet.objects
        .filter(utilisateur=request.user, termine=True)
        .select_related('patron')
        .order_by('-date_derniere_activite')
    )
    projets_termines = [
        {
            'patron_id': prog.patron_id,
            'titre': prog.patron.titre,
            'image': prog.patron.photo_url,
            'date_derniere_activite': prog.date_derniere_activite,
        }
        for prog in projets_termines_qs
    ]
    surface_sauvee = round(
        sum(prog.patron.surfaceMin for prog in projets_termines_qs), 2
    )

    nb_realisables = sum(1 for p in patrons_list if p['compatibilite'] >= 100)
    patron_vedette = max(patrons_list, key=lambda p: p['compatibilite']) if patrons_list else None

    # ── « Une heure ou moins » : patrons courts, les faisables d'abord ──
    patrons_rapides = sorted(
        [p for p in patrons_list if p['duree_min'] is not None and p['duree_min'] <= 60],
        key=lambda p: (-p['compatibilite'], p['duree_min']),
    )[:8]

    # ── « Pour ton <tissu> » : le vêtement le plus grand de la penderie ──
    plus_grand = (
        Vetement.objects
        .filter(utilisateur=request.user)
        .order_by('-surfaceExploitable')
        .first()
    )
    tissu_focus = None
    if plus_grand:
        matiere = get_dominant_material(plus_grand.matiere)
        surface_dispo = round(plus_grand.surfaceExploitable, 2)
        # Les patrons que ce tissu couvre d'abord, du plus ajusté au plus petit.
        suggestions = sorted(
            patrons_list,
            key=lambda p: (p['surface_min'] > surface_dispo,
                           abs(p['surface_min'] - surface_dispo)),
        )[:6]
        tissu_focus = {
            'nom': matiere or plus_grand.nomVetement,
            'surface': surface_dispo,
            'patrons': [
                dict(p, faisable_ici=p['surface_min'] <= surface_dispo)
                for p in suggestions
            ],
        }

    # ── Progression de couture : 100 XP par projet terminé, 500 XP par niveau ──
    xp_total = len(projets_termines) * 100
    niveau = xp_total // 500 + 1
    xp_niveau = xp_total % 500
    NIVEAU_TITRES = {1: 'Apprenti·e', 2: 'Aiguille agile', 3: 'Couturier·ère', 4: 'Artisan·e'}

    return render(request, 'core/patrons.html', {
        'patrons': patrons_list,
        'patrons_rapides': patrons_rapides,
        'tissu_focus': tissu_focus,
        'projets_en_cours': projets_en_cours,
        'projets_termines': projets_termines,
        'nb_termines': len(projets_termines),
        'surface_sauvee': surface_sauvee,
        'liked_ids_json': list(liked_ids),
        'nb_realisables': nb_realisables,
        'patron_vedette': patron_vedette,
        'surface_user': round(surface_user, 2),
        'niveau': niveau,
        'niveau_titre': NIVEAU_TITRES.get(niveau, 'Maître couturier·ère'),
        'xp_niveau': xp_niveau,
        'xp_palier': 500,
        'xp_pct': round(xp_niveau / 500 * 100),
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

    # Retour de l'outil de faisabilité (core.views.faisabilite_patron) : ids
    # des tissus sur lesquels toutes les pièces ont été placées avec succès.
    # Revalidés contre les tissus de l'utilisateur (le paramètre vient d'une
    # simple query string) avant d'être affichés comme « vérifiés ».
    verif_ids = set()
    if request.GET.get('verifie') == '1':
        for part in request.GET.get('vetements', '').split(','):
            part = part.strip()
            if part.isdigit():
                verif_ids.add(int(part))
    verif_vetements = [v for v in user_vetements if v.id in verif_ids] if verif_ids else []
    if verif_vetements:
        selected_ids |= {v.id for v in verif_vetements}

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
        'pieces_gagnees': _pieces_gagnees(patron.difficulte),
        'faisabilite_ok': bool(verif_vetements),
        'faisabilite_vetements': verif_vetements,
        'faisabilite_ids_csv': ','.join(str(v.id) for v in verif_vetements),
    }
    return render(request, 'core/patron_detail.html', context)


# Dimensions de repli (cm) d'une pièce dont le patron ne renseigne pas la
# taille réelle : sans elles le placement à l'échelle 1:1 n'aurait aucun sens,
# on préfère une pièce carrée « moyenne » signalée comme estimée côté client.
PIECE_DIM_DEFAUT_CM = 20.0


@login_required
def faisabilite_patron(request, pk):
    """Outil de vérification de faisabilité : plan de coupe interactif.

    L'utilisateur voit ses tissus détourés (photo rognée sur le polygone de
    détourage, défauts compris) et y glisse les pièces du patron, à l'échelle
    réelle. Toute la géométrie est exprimée en centimètres côté client : les
    dimensions du tissu se déduisent de `echelle_cm_px` (cm par pixel de la
    photo) et celles des pièces de `largeur_cm`/`hauteur_cm`.
    """
    patron = get_object_or_404(Patron, pk=pk)

    pieces = []
    total_pieces = 0
    for pc in patron.pieces.all():
        quantite = max(1, pc.quantite or 1)
        total_pieces += quantite
        pieces.append({
            'id': pc.id,
            'nom': pc.nom,
            'quantite': quantite,
            'largeur_cm': pc.largeur_cm or PIECE_DIM_DEFAUT_CM,
            'hauteur_cm': pc.hauteur_cm or PIECE_DIM_DEFAUT_CM,
            # Dimensions manquantes : le client affiche un avertissement.
            'estimee': not (pc.largeur_cm and pc.hauteur_cm),
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
        'total_pieces': total_pieces,
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
        return render(request, 'core/communaute_desactivee.html')

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
    """Banque de tissus — inventaire, répartition par matière, mosaïque/liste."""
    vetements = list(Vetement.objects.filter(utilisateur=request.user).order_by('-id'))
    total_surface = sum(v.surfaceExploitable for v in vetements)

    # Surfaces minimales des patrons, triées : le socle de sélection s'en sert
    # pour annoncer combien de patrons la sélection courante permet de couper,
    # sans aller-retour serveur à chaque case cochée.
    surfaces_patrons = sorted(Patron.objects.values_list('surfaceMin', flat=True))

    vetements_data = []
    surface_par_matiere = {}
    nb_par_type = {}
    for v in vetements:
        matiere = get_dominant_material(v.matiere) or 'coton'
        surface_par_matiere[matiere] = surface_par_matiere.get(matiere, 0.0) + v.surfaceExploitable
        nb_par_type[v.typeVetement] = nb_par_type.get(v.typeVetement, 0) + 1

        # « État » de la pièce : part de sa surface encore exploitable une fois
        # les taches et les trous retirés.
        etat_pct = round(v.surfaceExploitable / v.surfaceTotale * 100) if v.surfaceTotale else 100

        try:
            defauts = json.loads(v.defauts) if v.defauts else []
        except (ValueError, TypeError):
            defauts = []
        nb_taches = sum(1 for d in defauts if d.get('type') == 'tache')

        couleur_hex = _couleur_hex(v.couleur)
        vetements_data.append({
            'vetement': v,
            'matiere_label': MATERIAL_LABELS.get(matiere, matiere.capitalize()),
            'couleur_hex': couleur_hex,
            'couleur_claire': _couleur_claire(couleur_hex),
            'etat_pct': min(100, max(0, etat_pct)),
            'nb_taches': nb_taches,
            'nb_trous': len(defauts) - nb_taches,
        })

    # Répartition par matière : les 4 plus présentes, le reste regroupé.
    classement = sorted(surface_par_matiere.items(), key=lambda kv: kv[1], reverse=True)
    repartition = [
        {
            'nom': MATERIAL_LABELS.get(nom, nom.capitalize()),
            'hex': MATERIAL_COLORS.get(nom, MATIERE_HEX_DEFAUT),
            'surface': round(surface, 1),
            'pct': round(surface / total_surface * 100) if total_surface else 0,
        }
        for nom, surface in classement[:4]
    ]
    if len(classement) > 4:
        surface_reste = sum(s for _, s in classement[4:])
        repartition.append({
            'nom': 'Autres',
            'hex': MATIERE_HEX_DEFAUT,
            'surface': round(surface_reste, 1),
            'pct': round(surface_reste / total_surface * 100) if total_surface else 0,
        })

    # Chips de filtre : uniquement les types réellement présents dans la banque.
    types_presents = [
        {'slug': slug, 'label': TYPE_VETEMENT_LABELS.get(slug, slug.capitalize()), 'nb': nb}
        for slug, nb in sorted(nb_par_type.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    return render(request, 'core/mes_tissus.html', {
        'vetements_data': vetements_data,
        'total_surface': round(total_surface, 2),
        'nb_vetements': len(vetements),
        'nb_matieres': len(surface_par_matiere),
        'repartition': repartition,
        'types_presents': types_presents,
        'surfaces_patrons': surfaces_patrons,
    })


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
    """Étape 1/4 du parcours d'inscription : l'adresse e-mail."""
    if request.method == 'POST':
        email = (request.POST.get('email') or '').strip()

        if not email:
            return render(request, 'core/inscription.html', {
                'error': "L'adresse e-mail est obligatoire.",
            })

        try:
            validate_email(email)
        except DjangoValidationError:
            return render(request, 'core/inscription.html', {
                'error': "Cette adresse e-mail n'a pas l'air valide.",
                'email': email,
            })

        if Utilisateur.objects.filter(email__iexact=email).exists():
            return render(request, 'core/inscription.html', {
                'error': "Un compte existe déjà avec cette adresse e-mail.",
                'email': email,
            })

        request.session['reg_email'] = email
        return redirect('inscription_etape1')

    return render(request, 'core/inscription.html', {
        'email': request.session.get('reg_email', ''),
    })


AVATAR_FILENAMES = [f'image {i}.png' for i in range(11, 27)]

NIVEAUX_COUTURE = {
    'debutant': 'Débutant·e',
    'intermediaire': 'Intermédiaire',
    'avance': 'Confirmé·e',
}


def inscription_etape1(request):
    """Étape 2/4 : le prénom, qui sert de nom d'utilisateur."""
    # Garde : si l'étape 1 n'a pas été faite (session expirée, accès direct),
    # on renvoie au début plutôt que de crasher plus loin.
    if not request.session.get('reg_email'):
        return redirect('inscription')

    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        context = {'username': username}

        if not username:
            context['error'] = "Indique un prénom pour ton profil."
            return render(request, 'core/inscription_etape1.html', context)

        if Utilisateur.objects.filter(username__iexact=username).exists():
            context['error'] = "Ce nom est déjà pris. Ajoute une initiale, par exemple."
            return render(request, 'core/inscription_etape1.html', context)

        request.session['reg_username'] = username
        return redirect('inscription_etape2')

    return render(request, 'core/inscription_etape1.html', {
        'username': request.session.get('reg_username', ''),
    })


def inscription_etape2(request):
    """Étape 3/4 : le mot de passe."""
    # Garde : étapes précédentes obligatoires.
    if not request.session.get('reg_email') or not request.session.get('reg_username'):
        return redirect('inscription')

    if request.method == 'POST':
        password = request.POST.get('password') or ''

        if not password:
            return render(request, 'core/inscription_etape2.html', {
                'error': "Le mot de passe est obligatoire.",
            })

        # Validation selon les règles Django (longueur, robustesse…).
        try:
            validate_password(password)
        except DjangoValidationError as e:
            return render(request, 'core/inscription_etape2.html', {
                'error': ' '.join(e.messages),
            })

        request.session['reg_password'] = password
        return redirect('inscription_etape3')

    return render(request, 'core/inscription_etape2.html')


def inscription_etape3(request):
    """Étape 4/4 : niveau de couture, consentement RGPD et création du compte."""
    # 1. On récupère toutes les infos des étapes précédentes dans la session
    email = request.session.get('reg_email')
    username = request.session.get('reg_username')
    password = request.session.get('reg_password')

    # Garde : si la session a expiré ou si l'on accède directement à cette URL,
    # les données essentielles manquent → on recommence proprement (évite un 500).
    if not email or not username or not password:
        return redirect('inscription')

    if request.method == 'POST':
        niveau = request.POST.get('experience_level') or 'debutant'
        if niveau not in NIVEAUX_COUTURE:
            niveau = 'debutant'

        # 2. Consentement RGPD obligatoire : sans acceptation explicite, pas de compte.
        if request.POST.get('consentement_rgpd') != 'on':
            return render(request, 'core/inscription_etape3.html', {
                'error': "Vous devez accepter la politique de confidentialité pour créer votre compte.",
                'niveau': niveau,
            })

        # 3. Revalidation anti-collision juste avant la création : un autre compte
        # a pu prendre ce pseudo / cet e-mail entre l'étape 2 et maintenant → évite un 500.
        if (Utilisateur.objects.filter(username__iexact=username).exists()
                or Utilisateur.objects.filter(email__iexact=email).exists()):
            return render(request, 'core/inscription.html',
                          {'error': "Ce compte existe déjà. Essayez de vous connecter."})

        # 4. On crée le compte (avec preuve horodatée du consentement RGPD)
        nouvel_utilisateur = Utilisateur.objects.create_user(
            username=username,
            email=email,
            password=password,
            niveau_couture=niveau,
            avatar=AVATAR_FILENAMES[0],
            consentementRGPD=True,
            dateConsentementRGPD=timezone.now(),
        )

        # 5. On nettoie la session
        for key in ('reg_email', 'reg_username', 'reg_password'):
            request.session.pop(key, None)

        # 6. On envoie l'e-mail de vérification (vérification souple)
        _envoyer_email_verification(request, nouvel_utilisateur)

        # 7. On connecte l'utilisateur et on lui montre sa carte d'atelier
        login(request, nouvel_utilisateur)
        return redirect('inscription_bienvenue')

    return render(request, 'core/inscription_etape3.html', {'niveau': 'debutant'})


@login_required
def inscription_bienvenue(request):
    """Écran de fin d'inscription : la carte d'atelier du nouveau membre.

    Accepte aussi le changement d'avatar depuis la carte (bouton crayon)."""
    if request.method == 'POST':
        avatar = request.POST.get('avatar', '')
        if avatar in AVATAR_FILENAMES:
            request.user.avatar = avatar
            request.user.save(update_fields=['avatar'])
        return redirect('inscription_bienvenue')

    return render(request, 'core/inscription_bienvenue.html', {
        'avatars': AVATAR_FILENAMES,
        'numero_atelier': f'{12400 + request.user.pk:,}'.replace(',', ' '),
        'nb_membres': f'{Utilisateur.objects.count():,}'.replace(',', ' '),
        'niveau_label': NIVEAUX_COUTURE.get(request.user.niveau_couture, 'Débutant·e'),
    })


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
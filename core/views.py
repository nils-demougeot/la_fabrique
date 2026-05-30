import base64
import json
import re
from django.core.files.base import ContentFile
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.db.models import Sum
import math

from django.http import JsonResponse
from core.models import Vetement, Utilisateur, Patron, EtapePatron, ProgressionProjet, PatronLike

def home(request):
    context = {
        'user_coins': '1,250'
    }
    return render(request, 'core/index.html', context)


@login_required
def dashboard(request):
    user = request.user
    OBJECTIF_M2 = 15.0

    surface_totale = round(
        Vetement.objects.filter(utilisateur=user).aggregate(total=Sum('surfaceExploitable'))['total'] or 0.0,
        2
    )
    co2_economise = round(surface_totale * 2.5, 1)

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
    }
    return render(request, 'core/dashboard.html', context)



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
        # Déduire la surface utilisée proportionnellement sur les vêtements sélectionnés
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
    return redirect('patrons')


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


@login_required
def communaute(request):
    return render(request, 'core/communaute.html')


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
    total_co2 = round(total_surface * 2.5, 1)
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

    return render(request, 'core/inscription_etape3.html')
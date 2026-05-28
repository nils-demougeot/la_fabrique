import json
import re
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.db.models import Sum
import math

from core.models import Vetement, Utilisateur, Patron, EtapePatron

def home(request):
    context = {
        'user_coins': '1,250'
    }
    return render(request, 'core/index.html', context)


@login_required
def dashboard(request):
    user = request.user
    OBJECTIF_M2 = 15.0

    # TODO: remplacer par Vetement.objects.filter(utilisateur=user).aggregate(total=Sum('surfaceExploitable'))
    surface_totale = 12.4
    # TODO: remplacer par surface_totale * facteur_CO2 (ex: 1 m² ≈ 1.13 kg CO2 économisé)
    co2_economise = 14

    surface_pourcentage = round((surface_totale / OBJECTIF_M2) * 100)
    surface_restante = round(OBJECTIF_M2 - surface_totale, 1)

    context = {
        'surface_totale': surface_totale,
        'surface_objectif': OBJECTIF_M2,
        'surface_pourcentage': surface_pourcentage,
        'surface_restante': surface_restante,
        'credits': user.soldePieces,
        'co2_economise': co2_economise,
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
                photo_fichier = request.FILES.get('photo')

                nouveau_vetement = Vetement.objects.create(
                    utilisateur=request.user,
                    nomVetement=f"{type_vetement.capitalize()} de {request.user.username}",
                    photoURL=photo_fichier,
                    typeVetement=type_vetement,
                    largeur=largeur_cm,
                    hauteur=hauteur_cm,
                    surfaceTotale=polygon_area_m2,
                    surfaceTaches=total_defect_area_m2,
                    surfaceTrous=0.0,
                    surfaceExploitable=usable_area_m2,
                    etat="À transformer"
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
        })

    return render(request, 'core/patrons.html', {'patrons': patrons_list})


@login_required
def patron_detail(request, pk):
    patron = get_object_or_404(Patron, pk=pk)
    tutoriels = patron.tutoriels.all()

    surface_user = (
        Vetement.objects
        .filter(utilisateur=request.user)
        .aggregate(total=Sum('surfaceExploitable'))['total'] or 0.0
    )

    etapes = list(patron.etapes.order_by('numero'))
    premiere_etape = etapes[0] if etapes else None

    all_materiel_set = []
    seen = set()
    if patron.materiel:
        for m in patron.materiel.split(','):
            m = m.strip()
            if m and m.lower() not in seen:
                seen.add(m.lower())
                all_materiel_set.append(m)
    for etape in etapes:
        if etape.materiaux_etape:
            for m in etape.materiaux_etape.split(','):
                m = m.strip()
                if m and m.lower() not in seen:
                    seen.add(m.lower())
                    all_materiel_set.append(m)

    context = {
        'patron': patron,
        'tutoriels': tutoriels,
        'etapes': etapes,
        'premiere_etape': premiere_etape,
        'difficulte_label': DIFFICULTE_LABELS.get(patron.difficulte, str(patron.difficulte)),
        'compatibilite': _compatibilite(surface_user, patron.surfaceMin),
        'materiel_list': all_materiel_set,
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
def communaute(request):
    return render(request, 'core/communaute.html')


def camera_demo(request):
    return render(request, 'core/camera_demo.html')


def inscription(request):
    if request.method == 'POST':
        # On sauvegarde l'email et le mdp dans la session
        request.session['reg_email'] = request.POST.get('email')
        request.session['reg_password'] = request.POST.get('password')
        return redirect('inscription_etape1')
    
    return render(request, 'core/inscription.html')

def inscription_etape1(request):
    if request.method == 'POST':
        # On sauvegarde le pseudo
        request.session['reg_username'] = request.POST.get('username')
        return redirect('inscription_etape2')
        
    return render(request, 'core/inscription_etape1.html')

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

        # 3. On créé le compte dans la session
        nouvel_utilisateur = Utilisateur.objects.create_user(
            username=username,
            email=email,
            password=password,
            niveau_couture=niveau,
            envies_creation=cibles_str
        )

        # 4. On nettoie la session
        keys_to_delete = ['reg_email', 'reg_password', 'reg_username', 'reg_niveau']
        for key in keys_to_delete:
            if key in request.session:
                del request.session[key]

        # 5. On connecte l'utilisateur automatiquement et on l'envoie sur l'accueil
        login(request, nouvel_utilisateur)
        return redirect('home')

    return render(request, 'core/inscription_etape3.html')
from django.shortcuts import render

def home(request):
    # On passe notre donnée de pièces virtuelles pour l'injecter dans la maquette
    context = {
        'user_coins': '1,250'
    }
    return render(request, 'core/index.html', context)


import json
from django.shortcuts import render

def calculate_polygon_area(points, width_cm, height_cm):
    """
    Calcule l'aire d'un polygone avec la formule du lacet (Shoelace formula).
    Les points sont des coordonnées relatives (0 à 1).
    """
    if len(points) < 3:
        return 0.0

    # Conversion des points relatifs en centimètres réels
    # Exemple: x=0.5 avec une largeur de 50cm donne x=25cm
    real_points = []
    for p in points:
        real_points.append((p['x'] * width_cm, p['y'] * height_cm))

    # Formule du lacet (Shoelace algorithm)
    area = 0.0
    n = len(real_points)
    for i in range(n):
        j = (i + 1) % n
        area += real_points[i][0] * real_points[j][1]
        area -= real_points[j][0] * real_points[i][1]
        
    # Retourne la valeur absolue divisée par 2 (en cm²)
    return abs(area) / 2.0

def new_material(request):
    context = {'result_ready': False}

    if request.method == 'POST':
        try:
            # Récupération des données du formulaire HTML
            damage_size_cm = float(request.POST.get('damage_size', 0))
            
            # Les données de l'image et du canvas
            coords_str = request.POST.get('polygon_coords', '[]')
            polygon_points = json.loads(coords_str)
            
            calib_str = request.POST.get('calibration_coords', '[]')
            calib_points = json.loads(calib_str)
            
            calib_distance_cm = float(request.POST.get('calibration_distance', 0))
            img_w = float(request.POST.get('image_width', 1))
            img_h = float(request.POST.get('image_height', 1))

            defect_area_m2 = (damage_size_cm * damage_size_cm) / 10000.0

            # Vérifie si l'utilisateur a complété l'étalonnage
            if len(polygon_points) >= 3 and len(calib_points) == 2 and calib_distance_cm > 0:
                
                # 1. ÉTALONNAGE : Convertir les 2 points d'étalonnage en vrais pixels
                c1_x, c1_y = calib_points[0]['x'] * img_w, calib_points[0]['y'] * img_h
                c2_x, c2_y = calib_points[1]['x'] * img_w, calib_points[1]['y'] * img_h
                
                # Calcul de la distance en pixels (Théorème de Pythagore)
                distance_px = math.sqrt((c2_x - c1_x)**2 + (c2_y - c1_y)**2)
                
                if distance_px == 0:
                    raise ValueError("Points d'étalonnage confondus.")
                
                # Ratio : centimètres par pixel
                cm_per_px = calib_distance_cm / distance_px
                
                # 2. POLYGONE : Convertir en vrais pixels
                px_points = [(p['x'] * img_w, p['y'] * img_h) for p in polygon_points]
                
                # Algorithme du lacet pour l'aire en pixels carrés
                area_px2 = 0.0
                n = len(px_points)
                for i in range(n):
                    j = (i + 1) % n
                    area_px2 += px_points[i][0] * px_points[j][1]
                    area_px2 -= px_points[j][0] * px_points[i][1]
                area_px2 = abs(area_px2) / 2.0
                
                # 3. CONVERSION : Pixels² -> cm² -> m²
                polygon_area_cm2 = area_px2 * (cm_per_px ** 2)
                polygon_area_m2 = polygon_area_cm2 / 10000.0
                
                # Résultat final
                usable_area_m2 = max(0, polygon_area_m2 - defect_area_m2)
                
                # Si tu as retiré les inputs "width" et "height", 
                # la zone tracée EST la totalité du vêtement moins les défauts.
                percentage = int((usable_area_m2 / polygon_area_m2) * 100) if polygon_area_m2 > 0 else 0
                
                context.update({
                    'result_ready': True,
                    'usable_area': round(usable_area_m2, 2),
                    'percentage': percentage,
                    'coins_earned': 3, # Jackpot de gamification !
                })
            else:
                context['error'] = "Veuillez compléter le tracé et l'étalonnage de la photo."

        except (ValueError, json.JSONDecodeError, ZeroDivisionError):
            context['error'] = "Erreur dans le calcul de la surface. Recommencez le tracé."

    return render(request, 'core/new_material.html', context)
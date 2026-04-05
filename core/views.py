from django.shortcuts import render

def home(request):
    # On passe notre donnée de pièces virtuelles pour l'injecter dans la maquette
    context = {
        'user_coins': '1,250'
    }
    return render(request, 'core/index.html', context)


def new_material(request):
    # Par défaut, on n'affiche pas la carte de résultat
    context = {'result_ready': False}

    if request.method == 'POST':
        try:
            # Récupération des données du formulaire HTML
            width_cm = float(request.POST.get('width', 0))
            height_cm = float(request.POST.get('height', 0))
            damage_size_cm = float(request.POST.get('damage_size', 0))
            
            # Calculs : conversion en m² (1 m² = 10 000 cm²)
            total_area_m2 = (width_cm * height_cm) / 10000.0
            
            # On estime que le dégât est un carré (côté * côté)
            defect_area_m2 = (damage_size_cm * damage_size_cm) / 10000.0
            
            # La zone réutilisable est la zone totale moins le dégât (on ne descend pas sous 0)
            usable_area_m2 = max(0, total_area_m2 - defect_area_m2)

            # Calcul du pourcentage pour la barre de progression
            if total_area_m2 > 0:
                percentage = int((usable_area_m2 / total_area_m2) * 100)
            else:
                percentage = 0

            # On met à jour le contexte pour dire au template d'afficher les résultats
            context.update({
                'result_ready': True,          # Déclenche le {% if result_ready %} du HTML
                'usable_area': round(usable_area_m2, 2), # Arrondi à 2 décimales
                'percentage': percentage,
                'coins_earned': 1,             # Gamification
            })

        except ValueError:
            # Si l'utilisateur a réussi à envoyer du texte au lieu de nombres
            context['error'] = "Les dimensions saisies sont invalides."

    # On renvoie la page avec les variables (soit vides, soit avec les résultats si POST)
    return render(request, 'core/new_material.html', context)
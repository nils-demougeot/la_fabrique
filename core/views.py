from django.shortcuts import render

def home(request):
    # On passe notre donnée de pièces virtuelles pour l'injecter dans la maquette
    context = {
        'user_coins': '1,250'
    }
    return render(request, 'core/index.html', context)

from django.shortcuts import render

def new_material(request):
    # Dictionnaire de contexte envoyé au template
    context = {
        'result_ready': False
    }

    if request.method == 'POST':
        try:
            # 1. Récupération des données saisies par l'utilisateur
            width_cm = float(request.POST.get('width', 0))
            height_cm = float(request.POST.get('height', 0))
            damage_size_cm = float(request.POST.get('damage_size', 0))
            
            # L'image importée est stockée ici pour tes futurs traitements (enregistrement en BDD)
            uploaded_image = request.FILES.get('image')

            # 2. Algorithme de calcul de la quantité de tissu
            # Conversion de la surface totale en m² (1 m² = 10 000 cm²)
            total_area_m2 = (width_cm * height_cm) / 10000.0

            # Approximation de la surface du dégât (tache ou trou) en m².
            # On considère le dégât comme un carré de côté "damage_size_cm" pour simplifier.
            defect_area_m2 = (damage_size_cm * damage_size_cm) / 10000.0

            # Soustraction exacte des défauts 
            usable_area_m2 = total_area_m2 - defect_area_m2

            # Sécurité pour éviter une surface négative si le dégât renseigné est plus grand que le vêtement
            if usable_area_m2 < 0:
                usable_area_m2 = 0

            # 3. Calcul des statistiques pour l'affichage
            percentage = 0
            if total_area_m2 > 0:
                percentage = int((usable_area_m2 / total_area_m2) * 100)
            
            # Application de la règle de gamification : 1 pièce gagnée à chaque utilisation 
            coins_earned = 1 

            # 4. Envoi des résultats au template
            context.update({
                'result_ready': True,
                'usable_area': round(usable_area_m2, 2),
                'percentage': percentage,
                'coins_earned': coins_earned,
            })

        except ValueError:
            # Gestion basique des erreurs si l'utilisateur entre du texte à la place des chiffres
            context['error'] = "Veuillez entrer des dimensions valides."

    return render(request, 'core/new_material.html', context)
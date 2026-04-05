from django.shortcuts import render

def home(request):
    # On passe notre donnée de pièces virtuelles pour l'injecter dans la maquette
    context = {
        'user_coins': '1,250'
    }
    return render(request, 'core/index.html', context)
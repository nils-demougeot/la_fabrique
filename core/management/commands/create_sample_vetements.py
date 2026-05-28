from django.core.management.base import BaseCommand
from core.models import Vetement, Utilisateur

class Command(BaseCommand):
    help = 'Crée des vêtements exemples pour le superutilisateur'

    def handle(self, *args, **options):
        user = Utilisateur.objects.filter(is_superuser=True).first()
        if not user:
            self.stdout.write('Aucun superutilisateur trouvé.')
            return
        if Vetement.objects.filter(utilisateur=user).exists():
            self.stdout.write('Vêtements déjà présents, création ignorée.')
            return
        samples = [
            dict(nomVetement="Vieux jean délavé",    typeVetement="jean",    largeur=70,  hauteur=110, surfaceTotale=0.55, surfaceTaches=0.04, surfaceTrous=0.01, surfaceExploitable=0.50, etat="À transformer", qualite=4),
            dict(nomVetement="T-shirt blanc usé",    typeVetement="tshirt",  largeur=55,  hauteur=72,  surfaceTotale=0.40, surfaceTaches=0.06, surfaceTrous=0.00, surfaceExploitable=0.34, etat="À transformer", qualite=2),
            dict(nomVetement="Hoodie gris chiné",    typeVetement="hoodie",  largeur=65,  hauteur=80,  surfaceTotale=0.52, surfaceTaches=0.02, surfaceTrous=0.00, surfaceExploitable=0.50, etat="À transformer", qualite=5),
            dict(nomVetement="Robe fleurie d'été",   typeVetement="robe",    largeur=55,  hauteur=120, surfaceTotale=0.66, surfaceTaches=0.10, surfaceTrous=0.00, surfaceExploitable=0.56, etat="À transformer", qualite=3),
            dict(nomVetement="Manteau laine beige",  typeVetement="manteau", largeur=80,  hauteur=130, surfaceTotale=1.04, surfaceTaches=0.00, surfaceTrous=0.00, surfaceExploitable=1.04, etat="À transformer", qualite=5),
        ]
        for s in samples:
            Vetement.objects.create(utilisateur=user, photoURL='', **s)
        self.stdout.write(f'{len(samples)} vêtements créés pour {user.username}.')

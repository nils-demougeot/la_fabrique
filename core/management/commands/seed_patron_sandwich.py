"""Ajoute le patron « Protège-sandwich en tissu » (et ses pièces) s'il manque.

Volontairement séparé de populate_demo_patrons : celle-ci ne fait rien dès
que des patrons existent déjà (cas du serveur), et dans d'autres cas les
supprime tous pour les recréer. Cette commande-ci est idempotente : elle
crée le patron une seule fois, sans jamais toucher aux autres.

Calcul du carré : pain de mie de 11 × 11 cm. Chaque rabat couvre ¾ du côté,
d'où 11 + 2 × (¾ × 11) = 27,5 cm, arrondi à 27 cm, + 1 cm d'ourlet de chaque
côté = carré de 29 × 29 cm à découper.

Usage :
    python manage.py seed_patron_sandwich
"""
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import EtapePatron, Patron, PiecePatron

TITRE = 'Protège-sandwich en tissu'

PATRON = {
    'titre': TITRE,
    'description': (
        'Un emballage lavable pour remplacer l\'aluminium et le film plastique : un carré de tissu '
        'qui se replie autour d\'un sandwich de pain de mie et se ferme avec un bouton. '
        'Projet idéal pour débuter et pour recycler un vieux vêtement en coton. '
        'Pas besoin de machine à coudre : la pièce est petite, tout se coud facilement à la main.'
    ),
    'typeObjet': 'Cuisine',
    'surfaceMin': 0.09,
    'surfaceMax': 0.12,
    'estPremium': False,
    'difficulte': 1,
    'duree': '1h',
    # L'onglet « Outils » découpe cette liste (et celles des étapes) sur les
    # virgules : aucun outil ne doit en contenir, et les étapes reprennent
    # exactement ces libellés pour être fusionnées sans doublon.
    'materiel': (
        'Ciseaux de couture, Aiguille à coudre (ou machine à coudre), Fil, Épingles, '
        '1 bouton, Règle, Fer à repasser'
    ),
    # Contact alimentaire : fibres naturelles, lavables à 60 °C.
    'matiere_requise': 'coton,lin',
}

ETAPES = [
    {
        'titre': 'Tracer et découper le tissu',
        'description': (
            'Pour un pain de mie classique (11 cm × 11 cm) : tracez un carré de 29 × 29 cm. '
            'Prévoyez aussi une petite bande de 4 × 12 cm pour la languette de fermeture.'
        ),
        'conseil': (
            'Votre pain est plus grand ? Utilisez la formule : côté du pain × 2,5, plus 2 cm pour l\'ourlet. '
            'Pour un pain de 13 cm : 13 × 2,5 + 2 ≈ 35 cm.'
        ),
        'materiaux_etape': 'Règle, Ciseaux de couture',
    },
    {
        'titre': 'Coudre la bordure tout autour',
        'description': (
            'Sur l\'envers du tissu, repliez chaque bord de 0,5 cm, puis encore de 0,5 cm pour enfermer '
            'le bord coupé : vous obtenez une bordure de 0,5 cm qui ne s\'effilochera pas. '
            'Repassez au fur et à mesure et maintenez avec des épingles. '
            'Cousez tout autour, au ras du pli intérieur.'
        ),
        'conseil': '',
        'materiaux_etape': 'Aiguille à coudre (ou machine à coudre), Fil, Épingles, Fer à repasser',
    },
    {
        'titre': 'Coudre la languette',
        'description': (
            'Pour la languette, faites comme pour l\'étape 2 : rabattez deux fois les côtés de 0,5 cm, '
            'puis cousez. Repassez entre chaque rabat pour plus de facilité à coudre.'
        ),
        'conseil': '',
        'materiaux_etape': 'Aiguille à coudre (ou machine à coudre), Fil, Fer à repasser',
    },
    {
        'titre': 'Faire le trou de la languette',
        'description': (
            'Faites un trou à un des bords de la languette pour y faire rentrer le bouton.'
        ),
        'conseil': '',
        'materiaux_etape': 'Ciseaux de couture',
    },
    {
        'titre': 'Fixer la languette',
        'description': (
            'Cousez la languette à un des bords du tissu qui couvrira le sandwich.'
        ),
        'conseil': '',
        'materiaux_etape': 'Aiguille à coudre (ou machine à coudre), Fil, Épingles',
    },
    {
        'titre': 'Repérer l\'emplacement du bouton',
        'description': (
            'Mettez une tranche de pain au milieu de votre tissu, rabattez les bords et dessinez '
            'l\'emplacement du bouton : il correspond à l\'endroit où tombe le trou de la languette.'
        ),
        'conseil': '',
        'materiaux_etape': '',
    },
    {
        'titre': 'Coudre le bouton',
        'description': (
            'Cousez le bouton en passant 4 à 5 fois dans chaque trou. Avant le dernier passage, enroulez '
            'le fil 3 fois sous le bouton pour former une petite tige : la boucle passera plus facilement.'
        ),
        'conseil': '',
        'materiaux_etape': 'Aiguille à coudre (ou machine à coudre), Fil, 1 bouton',
    },
]

# Photo d'illustration, versionnée avec le code.
PHOTO = Path(__file__).resolve().parents[2] / 'fixtures' / 'patron_protege_sandwich.jpg'

# (nom, quantité, largeur_cm, hauteur_cm, fill, stroke)
PIECES = [
    ('Carré principal', 1, 29, 29, '#FBE7D3', '#C2603F'),
    ('Languette de fermeture', 1, 4, 12, '#E7D3BE', '#8D6E63'),
]


def _svg_rect(w_cm, h_cm, fill, stroke):
    """SVG d'un rectangle arrondi aux proportions réelles (cf. seed_totebag_pieces)."""
    w, h = round(w_cm * 10), round(h_cm * 10)
    rx = round(min(w, h) * 0.08)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">'
        f'<rect x="6" y="6" width="{w - 12}" height="{h - 12}" rx="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="6"/>'
        f'</svg>'
    )


class Command(BaseCommand):
    help = 'Ajoute le patron « Protège-sandwich en tissu » s\'il n\'existe pas encore.'

    def handle(self, *args, **options):
        if Patron.objects.filter(titre=TITRE).exists():
            self.stdout.write(self.style.SUCCESS(f'« {TITRE} » existe déjà — skip.'))
            return

        with transaction.atomic():
            patron = Patron.objects.create(**PATRON)
            for numero, etape in enumerate(ETAPES, 1):
                EtapePatron.objects.create(patron=patron, numero=numero, **etape)

        # La photo peut échouer si le stockage média n'est pas disponible.
        try:
            patron.photo.save(PHOTO.name, ContentFile(PHOTO.read_bytes()), save=True)
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f'  Photo non enregistrée ({exc.__class__.__name__})'))

        for ordre, (nom, qte, lcm, hcm, fill, stroke) in enumerate(PIECES):
            piece = PiecePatron.objects.create(
                patron=patron, nom=nom, quantite=qte,
                largeur_cm=lcm, hauteur_cm=hcm, ordre=ordre,
            )
            # Le SVG peut échouer si le stockage média n'est pas disponible.
            try:
                svg = _svg_rect(lcm, hcm, fill, stroke).encode('utf-8')
                piece.svg.save(f'sandwich-{ordre}.svg', ContentFile(svg), save=True)
            except Exception as exc:
                self.stdout.write(self.style.WARNING(
                    f'  SVG non enregistré pour « {nom} » ({exc.__class__.__name__})'
                ))

        self.stdout.write(self.style.SUCCESS(
            f'« {TITRE} » (#{patron.id}) créé : {len(ETAPES)} étapes, {len(PIECES)} pièces.'
        ))

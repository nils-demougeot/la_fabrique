"""Peuple des pièces factices mais logiques pour le patron « Tote bag XXL ».

Tailles volontairement modestes pour être faciles à placer dans l'outil de faisabilité.

Usage :
    python manage.py seed_totebag_pieces
"""
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from core.models import Patron, PiecePatron


def _svg_rect(w_cm, h_cm, fill, stroke):
    """SVG d'un rectangle arrondi dont le viewBox respecte les proportions réelles."""
    w = round(w_cm * 10)
    h = round(h_cm * 10)
    rx = round(min(w, h) * 0.08)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">'
        f'<rect x="6" y="6" width="{w - 12}" height="{h - 12}" rx="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="6"/>'
        f'</svg>'
    )


# (nom, quantité, largeur_cm, hauteur_cm, fill, stroke)
PIECES = [
    ("Panneau avant", 1, 20, 24, "#D2F4D1", "#237329"),
    ("Panneau arrière", 1, 20, 24, "#D2F4D1", "#237329"),
    ("Anse",            2,  4, 28, "#E7D3BE", "#8D6E63"),
    ("Poche",           1, 12, 12, "#CFE0F7", "#3B5FC0"),
]


class Command(BaseCommand):
    help = "Crée des pièces factices pour le patron Tote bag XXL."

    def handle(self, *args, **options):
        patron = (Patron.objects.filter(titre__icontains="tote bag xxl").first()
                  or Patron.objects.filter(titre__icontains="tote").first())
        if not patron:
            self.stderr.write(self.style.ERROR("Patron « Tote bag XXL » introuvable."))
            return

        # On repart d'une base propre (idempotent)
        deleted = patron.pieces.count()
        patron.pieces.all().delete()

        created, with_svg = 0, 0
        for ordre, (nom, qte, lcm, hcm, fill, stroke) in enumerate(PIECES):
            piece = PiecePatron.objects.create(
                patron=patron, nom=nom, quantite=qte,
                largeur_cm=lcm, hauteur_cm=hcm, ordre=ordre,
            )
            # Tentative d'attache du SVG (peut échouer si le stockage média n'est pas dispo)
            try:
                svg_bytes = _svg_rect(lcm, hcm, fill, stroke).encode("utf-8")
                slug = nom.lower().replace(" ", "-").replace("é", "e").replace("è", "e")
                piece.svg.save(f"totebag-{ordre}-{slug}.svg", ContentFile(svg_bytes), save=True)
                with_svg += 1
            except Exception as exc:  # stockage indispo (ex: Cloudinary mal configuré)
                self.stdout.write(self.style.WARNING(f"  SVG non enregistré pour « {nom} » ({exc.__class__.__name__})"))
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Patron « {patron.titre} » (#{patron.id}) : {deleted} pièce(s) supprimée(s), "
            f"{created} créée(s), {with_svg} avec SVG."
        ))

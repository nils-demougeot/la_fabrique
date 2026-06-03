"""
Uploade les photos de patrons locales directement sur Cloudinary via le SDK,
puis met a jour la BDD avec l'URL Cloudinary securisee.

Usage :
    python manage.py sync_patron_photos
"""
import os
import cloudinary.uploader
from django.conf import settings
from django.core.management.base import BaseCommand
from core.models import Patron


class Command(BaseCommand):
    help = 'Uploade les photos de patrons vers Cloudinary et met a jour la BDD'

    def handle(self, *args, **options):
        import cloudinary
        cfg = cloudinary.config()
        if not cfg.cloud_name:
            self.stdout.write(self.style.ERROR(
                'Cloudinary non configure. Ajoutez CLOUDINARY_URL dans votre .env'
            ))
            return

        self.stdout.write(f'Cloudinary cloud : {cfg.cloud_name}')
        media_dir = os.path.join(settings.MEDIA_ROOT, 'patrons')

        if not os.path.isdir(media_dir):
            self.stdout.write(self.style.ERROR(f'Dossier introuvable : {media_dir}'))
            return

        patrons = Patron.objects.all()
        if not patrons.exists():
            self.stdout.write(self.style.WARNING(
                "Aucun patron. Lancez d'abord : python manage.py populate_demo_patrons"
            ))
            return

        updated = missing = errors = 0

        for patron in patrons:
            if not patron.photo:
                self.stdout.write(self.style.WARNING(f'  [SANS IMAGE] {patron.titre}'))
                missing += 1
                continue

            fname = os.path.basename(patron.photo.name)
            local_path = os.path.join(media_dir, fname)

            if not os.path.isfile(local_path):
                self.stdout.write(self.style.WARNING(f'  [MANQUANT]   {fname}'))
                missing += 1
                continue

            # public_id sans extension (convention Cloudinary)
            name_no_ext = os.path.splitext(fname)[0]
            public_id = f'patrons/{name_no_ext}'

            self.stdout.write(f'  [UPLOAD]  {fname}')
            try:
                result = cloudinary.uploader.upload(
                    local_path,
                    public_id=public_id,
                    overwrite=True,
                    invalidate=True,
                    resource_type='image',
                )
                cloudinary_url = result['secure_url']

                # Stocke l'URL HTTPS Cloudinary directement dans le champ photo
                patron.photo.name = cloudinary_url
                patron.save(update_fields=['photo'])

                self.stdout.write(self.style.SUCCESS(f'    OK  {cloudinary_url}'))
                updated += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'    ERREUR : {e}'))
                errors += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Termine : {updated} uploades, {missing} fichiers manquants, {errors} erreurs.'
        ))

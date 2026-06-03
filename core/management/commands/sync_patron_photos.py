"""
Resynchronise les photos de patrons locales vers le storage actif (Cloudinary en prod).
Utile quand les fichiers de media/patrons/ ont été remplacés manuellement
mais que Cloudinary (et son cache CDN) sert toujours les anciennes versions.

Usage :
    python manage.py sync_patron_photos           # tous les patrons
    python manage.py sync_patron_photos --force   # supprime+recharge même si l'image n'a pas changé
"""
import os
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from core.models import Patron


class Command(BaseCommand):
    help = 'Re-uploade les photos de patrons locales vers Cloudinary (invalide le cache CDN)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force le re-upload même si une photo est déjà enregistrée en BDD',
        )

    def handle(self, *args, **options):
        force = options['force']
        media_dir = os.path.join(settings.MEDIA_ROOT, 'patrons')

        if not os.path.isdir(media_dir):
            self.stdout.write(self.style.ERROR(
                f'Dossier introuvable : {media_dir}\n'
                'Vérifiez que MEDIA_ROOT est correctement défini dans settings.py.'
            ))
            return

        patrons = Patron.objects.all()
        if not patrons.exists():
            self.stdout.write(self.style.WARNING(
                'Aucun patron en base de données. '
                'Lancez d\'abord : python manage.py populate_demo_patrons'
            ))
            return

        updated = skipped = missing = 0

        for patron in patrons:
            if not patron.photo:
                self.stdout.write(self.style.WARNING(f'  [SANS IMAGE] {patron.titre}'))
                missing += 1
                continue

            fname = os.path.basename(patron.photo.name)
            local_path = os.path.join(media_dir, fname)

            if not os.path.isfile(local_path):
                self.stdout.write(self.style.WARNING(
                    f'  [MANQUANT]  {fname} — {patron.titre}'
                ))
                missing += 1
                continue

            if not force:
                # Vérification rapide : si l'URL cloudinary contient déjà le bon nom, on peut sauter
                # mais on uploade quand même pour garantir la fraîcheur du CDN
                pass

            self.stdout.write(f'  [UPLOAD]    {fname}  →  "{patron.titre}"')
            try:
                with open(local_path, 'rb') as fh:
                    img_data = fh.read()

                # Supprimer l'ancienne entrée Cloudinary (invalide automatiquement le cache CDN)
                try:
                    patron.photo.delete(save=False)
                except Exception as del_err:
                    self.stdout.write(self.style.WARNING(f'    (suppression ancienne photo : {del_err})'))

                # Re-sauvegarder — Django-Cloudinary re-publie avec invalidation
                patron.photo.save(fname, ContentFile(img_data), save=True)
                self.stdout.write(self.style.SUCCESS(f'    OK  →  {patron.photo.url}'))
                updated += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'    ERREUR : {e}'))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Synchronisation terminée : {updated} mis à jour, '
            f'{skipped} ignorés, {missing} fichiers locaux manquants.'
        ))
        if missing:
            self.stdout.write(self.style.WARNING(
                'Pour les patrons manquants, relancez populate_demo_patrons '
                'puis replacez vos images dans media/patrons/ et relancez cette commande.'
            ))

"""
Commande de déploiement complète : peuple la BDD du serveur depuis zéro.

Ordre d'exécution :
  1. populate_demo_patrons  — crée les 9 patrons + télécharge images depuis Unsplash
  2. loaddata seed_data     — injecte utilisateurs fictifs, posts, commentaires, etc.
  3. sync_patron_photos     — re-uploade les images locales vers Cloudinary (si fichiers présents)

Usage :
    python manage.py deploy_seed
    python manage.py deploy_seed --skip-photos   (ignore sync_patron_photos)
    python manage.py deploy_seed --reset         (supprime les données communauté existantes)
"""
from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Peuple le serveur : patrons + seed_data fixture + sync photos Cloudinary'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-photos',
            action='store_true',
            help='Ignore l\'étape sync_patron_photos (utile si les fichiers locaux ne sont pas disponibles)',
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Passe --reset à populate_communaute (supprime les données communauté avant)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('\n=== DEPLOY SEED ===\n'))

        # 1. Patrons
        self.stdout.write(self.style.MIGRATE_HEADING('Étape 1/3 — Patrons de démonstration'))
        call_command('populate_demo_patrons')

        # 2. Fixture seed_data (utilisateurs fictifs + posts + hashtags + ...)
        self.stdout.write(self.style.MIGRATE_HEADING('\nÉtape 2/3 — Injection du fixture seed_data'))
        try:
            call_command('loaddata', 'seed_data')
            self.stdout.write(self.style.SUCCESS('  Fixture chargé avec succès.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  Erreur fixture : {e}'))
            self.stdout.write(self.style.WARNING(
                '  Conseil : si des conflits existent, lancez populate_communaute --reset '
                'puis relancez deploy_seed --skip-photos.'
            ))

        # 3. Sync photos (optionnel)
        if not options['skip_photos']:
            self.stdout.write(self.style.MIGRATE_HEADING('\nÉtape 3/3 — Synchronisation photos → Cloudinary'))
            call_command('sync_patron_photos')
        else:
            self.stdout.write(self.style.WARNING('\nÉtape 3/3 ignorée (--skip-photos).'))
            self.stdout.write('  Pour synchroniser les photos plus tard :')
            self.stdout.write('    python manage.py sync_patron_photos')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=== Déploiement terminé ==='))
        self.stdout.write('')
        self.stdout.write('Résumé des comptes fictifs (mot de passe : motdepasse123) :')
        for username in [
            'sophie_couture', 'marc_denim', 'camille_vert', 'theo_reparation',
            'lea_faitmain', 'hugo_zero_dechet', 'emma_patron', 'lucas_lin',
        ]:
            self.stdout.write(f'  - {username}')

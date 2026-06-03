#!/usr/bin/env bash
set -e

pip install -r requirements.txt
python manage.py migrate --no-input

# Supprime les patrons existants avant de recharger le seed pour éviter les
# doublons de titre qui feraient échouer la vérification Cloudinary ensuite.
python manage.py shell -c "
from core.models import Patron
count = Patron.objects.count()
Patron.objects.all().delete()
print(f'{count} patron(s) supprime(s) avant rechargement seed')
" || true

# Charge les données : patrons (avec photos Cloudinary) + communauté fictive
python manage.py loaddata seed_data || true

# Remet les séquences PostgreSQL à jour après loaddata
python manage.py shell -c "
from django.db import connection
from django.core.management import call_command
from io import StringIO
buf = StringIO()
call_command('sqlsequencereset', 'core', stdout=buf, no_color=True)
sql = buf.getvalue()
if sql:
    with connection.cursor() as cursor:
        cursor.execute(sql)
"

# Fallback : si les patrons n'ont pas de photo Cloudinary, les recréer depuis Unsplash
python manage.py populate_demo_patrons

python manage.py create_superuser_if_none
python manage.py create_sample_vetements
python manage.py populate_communaute
python manage.py collectstatic --no-input

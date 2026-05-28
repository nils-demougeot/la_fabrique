#!/usr/bin/env bash
set -e

pip install -r requirements.txt
python manage.py migrate --no-input

# Charge les données initiales uniquement si la base est vide
python manage.py shell -c "
from core.models import Patron
if not Patron.objects.exists():
    from django.core.management import call_command
    from django.db import connection
    from io import StringIO

    call_command('loaddata', 'initial_data')

    # Réinitialise les séquences PostgreSQL pour éviter les conflits de clés
    buf = StringIO()
    call_command('sqlsequencereset', 'core', stdout=buf, no_color=True)
    sql = buf.getvalue()
    if sql:
        with connection.cursor() as cursor:
            cursor.execute(sql)

    print('Fixtures et séquences initialisés.')
else:
    print('Données déjà présentes, chargement ignoré.')
"

python manage.py create_superuser_if_none
python manage.py collectstatic --no-input

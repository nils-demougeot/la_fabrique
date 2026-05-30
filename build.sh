#!/usr/bin/env bash
set -e

pip install -r requirements.txt
python manage.py migrate --no-input
python manage.py loaddata initial_data

# Réinitialise les séquences PostgreSQL pour éviter les conflits de clés après loaddata
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

python manage.py create_superuser_if_none
python manage.py create_sample_vetements
python manage.py populate_demo_patrons
python manage.py collectstatic --no-input

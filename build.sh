#!/usr/bin/env bash
set -e

pip install -r requirements.txt
python manage.py migrate --no-input

python manage.py populate_demo_patrons
python manage.py create_superuser_if_none
python manage.py create_sample_vetements
python manage.py populate_communaute
python manage.py collectstatic --no-input

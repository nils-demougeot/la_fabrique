#!/usr/bin/env bash
set -e

pip install -r requirements.txt
python manage.py migrate --no-input

python manage.py populate_demo_patrons
python manage.py seed_totebag_pieces
python manage.py create_superuser_if_none
python manage.py create_sample_vetements
python manage.py populate_communaute

# Communauté « atelier » : monde de démonstration (saison, ligue, voisins,
# salons, duels, agenda, entraide, troc) rattaché à TOUS les comptes réels.
# Idempotent et sans --reset : relancé à chaque déploiement, il complète la
# base sans jamais effacer les vraies conversations.
python manage.py seed_communaute --tous

python manage.py collectstatic --no-input --clear

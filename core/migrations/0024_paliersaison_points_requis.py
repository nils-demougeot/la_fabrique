"""Le seuil d'un palier de saison s'exprime désormais en CP d'atelier.

Le sentier de la saison se lisait en XP de saison, une unité distincte de
celle de la barre de progression. Les deux sont réunifiées sur les CP
(tissus, étapes, projets) : `xp_requis` devient donc `points_requis`.

Renommage explicite plutôt que suppression + création : les paliers déjà
configurés en base gardent leur valeur.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0023_alter_annoncetroc_options_quete_cta_libelle_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='paliersaison',
            old_name='xp_requis',
            new_name='points_requis',
        ),
        migrations.AlterField(
            model_name='paliersaison',
            name='points_requis',
            field=models.PositiveIntegerField(
                help_text="CP d'atelier nécessaires pour débloquer ce palier."
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_vetement_matiere_patron_matiere_requise_progression_vetements'),
    ]

    operations = [
        migrations.AddField(
            model_name='utilisateur',
            name='avatar',
            field=models.CharField(blank=True, default='image 11.png', max_length=50),
        ),
    ]

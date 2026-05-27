from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_utilisateur_envies_creation_and_more'),
    ]

    operations = [
        # Patron: nouveaux champs
        migrations.AddField(
            model_name='patron',
            name='photo',
            field=models.ImageField(blank=True, null=True, upload_to='patrons/'),
        ),
        migrations.AddField(
            model_name='patron',
            name='duree',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        # Patron: agrandissement des champs existants
        migrations.AlterField(
            model_name='patron',
            name='titre',
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name='patron',
            name='description',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='patron',
            name='typeObjet',
            field=models.CharField(max_length=50),
        ),
        # Tutoriel: agrandissement des champs
        migrations.AlterField(
            model_name='tutoriel',
            name='titre',
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name='tutoriel',
            name='urlVideoOuArticle',
            field=models.CharField(max_length=500),
        ),
        migrations.AlterField(
            model_name='tutoriel',
            name='source',
            field=models.CharField(max_length=100),
        ),
    ]

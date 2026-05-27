from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_patron_photo_duree_extend_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='patron',
            name='materiel',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='tutoriel',
            name='description',
            field=models.TextField(blank=True, null=True),
        ),
    ]

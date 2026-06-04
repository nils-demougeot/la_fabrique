from django.db import migrations

POST_IMAGES = {
    'Tote bag en denim recyclé':           'posts/real-upcycling.jpg',
    'Réparation sashiko visible':           'posts/real-reparation.jpg',
    'Patron chemise oversize':                   'posts/real-patron.jpg',
    'Veste en lin naturel':                      'posts/real-fait-main.jpg',
}

TEINTURE_IMAGE = 'posts/real-teinture.jpg'


def assign_images(apps, schema_editor):
    PostCommunaute = apps.get_model('core', 'PostCommunaute')
    for titre, path in POST_IMAGES.items():
        PostCommunaute.objects.filter(titre=titre, image='').update(image=path)
    # Les deux posts de teinture partagent la même photo
    PostCommunaute.objects.filter(type_creation='teinture', image='').update(image=TEINTURE_IMAGE)


def remove_images(apps, schema_editor):
    PostCommunaute = apps.get_model('core', 'PostCommunaute')
    paths = list(POST_IMAGES.values()) + [TEINTURE_IMAGE]
    for path in paths:
        PostCommunaute.objects.filter(image=path).update(image='')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_add_badge_model'),
    ]

    operations = [
        migrations.RunPython(assign_images, reverse_code=remove_images),
    ]

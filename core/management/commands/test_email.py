"""
Diagnostic de l'envoi d'e-mails.

Usage :
    python manage.py test_email destinataire@exemple.com

Affiche la configuration e-mail réellement chargée (variables d'environnement),
puis tente un envoi RÉEL en remontant l'erreur exacte (sans fail_silently).
À lancer en local ou dans le shell Render pour diagnostiquer.
"""
from django.conf import settings
from django.core.mail import get_connection, EmailMessage
from django.core.management.base import BaseCommand


def _mask(value):
    if not value:
        return '(vide)'
    return value[:2] + '…' + value[-2:] if len(value) > 4 else '••••'


class Command(BaseCommand):
    help = "Teste la configuration et l'envoi d'e-mails."

    def add_arguments(self, parser):
        parser.add_argument('destinataire', help="Adresse e-mail qui recevra le test.")

    def handle(self, *args, **options):
        dest = options['destinataire']

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Configuration e-mail chargée ==="))
        self.stdout.write(f"DEBUG               = {settings.DEBUG}")
        self.stdout.write(f"EMAIL_BACKEND       = {settings.EMAIL_BACKEND}")
        self.stdout.write(f"EMAIL_HOST          = {settings.EMAIL_HOST or '(vide)'}")
        self.stdout.write(f"EMAIL_PORT          = {settings.EMAIL_PORT}")
        self.stdout.write(f"EMAIL_USE_TLS       = {settings.EMAIL_USE_TLS}")
        self.stdout.write(f"EMAIL_USE_SSL       = {getattr(settings, 'EMAIL_USE_SSL', False)}")
        self.stdout.write(f"EMAIL_HOST_USER     = {settings.EMAIL_HOST_USER or '(vide)'}")
        self.stdout.write(f"EMAIL_HOST_PASSWORD = {_mask(settings.EMAIL_HOST_PASSWORD)}")
        self.stdout.write(f"EMAIL_TIMEOUT       = {getattr(settings, 'EMAIL_TIMEOUT', None)}")
        self.stdout.write(f"DEFAULT_FROM_EMAIL  = {settings.DEFAULT_FROM_EMAIL}")

        if 'console' in settings.EMAIL_BACKEND:
            self.stdout.write(self.style.WARNING(
                "\n⚠ Backend = console : aucun e-mail n'est réellement envoyé "
                "(il s'affiche ci-dessous). Pour un vrai envoi, il faut DEBUG=False "
                "ou DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend."
            ))

        if 'smtp' in settings.EMAIL_BACKEND and not settings.EMAIL_HOST:
            self.stdout.write(self.style.ERROR(
                "\n✗ Backend SMTP mais EMAIL_HOST est vide → les variables ne sont "
                "pas chargées. Vérifie qu'elles sont bien définies dans l'environnement."
            ))
            return

        # 1) Test de connexion seule
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Test de connexion SMTP ==="))
        try:
            conn = get_connection(fail_silently=False)
            conn.open()
            self.stdout.write(self.style.SUCCESS("✓ Connexion au serveur SMTP réussie."))
            conn.close()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Échec de connexion : {type(e).__name__}: {e}"))
            self.stdout.write(self.style.WARNING(
                "Causes fréquentes : mauvais EMAIL_HOST/port, identifiants incorrects, "
                "port bloqué (essayer 2525), TLS/SSL mal réglé."
            ))
            return

        # 2) Envoi réel
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== Envoi d'un e-mail de test à {dest} ==="))
        try:
            msg = EmailMessage(
                subject="Test d'envoi — La Fabrique",
                body="Si vous lisez ceci, la configuration e-mail fonctionne. 🎉",
                to=[dest],
                # from_email = DEFAULT_FROM_EMAIL par défaut
            )
            envoyes = msg.send(fail_silently=False)
            if envoyes:
                self.stdout.write(self.style.SUCCESS(
                    f"✓ E-mail accepté par le serveur ({envoyes} message). "
                    "Vérifie ta boîte de réception ET tes spams."
                ))
            else:
                self.stdout.write(self.style.ERROR("✗ 0 message envoyé (refus silencieux)."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Échec de l'envoi : {type(e).__name__}: {e}"))
            self.stdout.write(self.style.WARNING(
                "Si la connexion a réussi mais pas l'envoi : l'expéditeur "
                f"({settings.DEFAULT_FROM_EMAIL}) n'est probablement pas une adresse "
                "VÉRIFIÉE chez ton fournisseur (Brevo/Mailjet)."
            ))

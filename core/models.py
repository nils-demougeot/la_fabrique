from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.core.files.storage import default_storage


def raw_media_storage():
    """Stockage pour les fichiers bruts (PDF, SVG) : Cloudinary 'raw' si configuré,
    sinon le stockage par défaut (système de fichiers en local)."""
    if getattr(settings, 'CLOUDINARY_URL', None):
        from cloudinary_storage.storage import RawMediaCloudinaryStorage
        return RawMediaCloudinaryStorage()
    return default_storage


def video_media_storage():
    """Stockage pour les vidéos de geste : Cloudinary 'video' si configuré,
    sinon le stockage par défaut (système de fichiers en local)."""
    if getattr(settings, 'CLOUDINARY_URL', None):
        from cloudinary_storage.storage import VideoMediaCloudinaryStorage
        return VideoMediaCloudinaryStorage()
    return default_storage

class Utilisateur(AbstractUser):
    consentementRGPD = models.BooleanField(default=False)
    # Date à laquelle l'utilisateur a accepté la politique de confidentialité (preuve RGPD).
    dateConsentementRGPD = models.DateTimeField(null=True, blank=True)
    # Vérification souple de l'adresse e-mail (bandeau + accès restreint tant que False).
    email_verifie = models.BooleanField(default=False)
    soldePieces = models.IntegerField(default=0)

    niveau_couture = models.CharField(max_length=30, blank=True, null=True)
    envies_creation = models.CharField(max_length=255, blank=True, null=True)
    avatar = models.CharField(max_length=50, default='image 11.png', blank=True)
    bio = models.TextField(blank=True, null=True, max_length=300)

    @property
    def avatar_url(self):
        return f'core/images/avatars/{self.avatar or "image 11.png"}'

    def save(self, *args, **kwargs):
        # Les comptes administrateurs (root et autres superutilisateurs) n'ont
        # pas de boucle de vérification d'e-mail : ils sont vérifiés d'office.
        if self.is_superuser:
            self.email_verifie = True
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username

class Vetement(models.Model):
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='vetements')
    nomVetement = models.CharField(max_length=30)
    photoURL = models.ImageField(upload_to='vetements/')
    typeVetement = models.CharField(max_length=30)
    largeur = models.FloatField()
    hauteur = models.FloatField()
    surfaceTotale = models.FloatField()
    surfaceTaches = models.FloatField(default=0.0)
    surfaceTrous = models.FloatField(default=0.0)
    surfaceExploitable = models.FloatField()
    etat = models.CharField(max_length=30)
    qualite = models.IntegerField(default=3)
    couleur = models.CharField(max_length=30, blank=True, null=True)
    matiere = models.CharField(max_length=200, blank=True, null=True)  # ex: "coton:70,polyester:30"
    numeroIdentite = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="Numéro d'identité facultatif, saisi si le tissu a déjà été suivi ailleurs sur l'app."
    )

    # Données d'échelle/forme de la face avant (photoURL), pour le placement des pièces.
    echelle_cm_px = models.FloatField(null=True, blank=True)            # cm par pixel de la photo
    detourage = models.TextField(null=True, blank=True)                # polygone normalisé [{x,y},…]
    defauts = models.TextField(null=True, blank=True)                  # cercles [{x,y,r,type},…] normalisés

    def __str__(self):
        return f"{self.nomVetement} - {self.utilisateur.username}"

    @property
    def photo_url(self):
        if not self.photoURL:
            return None
        name = self.photoURL.name or ''
        if name.startswith('http'):
            return name
        try:
            return self.photoURL.url
        except (ValueError, AttributeError):
            return None

class Patron(models.Model):
    titre = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    typeObjet = models.CharField(max_length=50)
    surfaceMin = models.FloatField()
    surfaceMax = models.FloatField()
    estPremium = models.BooleanField(default=False)
    difficulte = models.IntegerField()
    photo = models.ImageField(upload_to='patrons/', null=True, blank=True)
    duree = models.CharField(max_length=20, blank=True, null=True)
    materiel = models.TextField(blank=True, null=True)
    matiere_requise = models.TextField(
        blank=True, null=True,
        help_text="Matières acceptées, séparées par des virgules (ex: coton,lin,viscose). Laisser vide = toute matière acceptée."
    )
    createur = models.ForeignKey(
        'Utilisateur', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='patrons_crees'
    )
    pdf_patron = models.FileField(
        upload_to='patrons/pdf/', null=True, blank=True,
        storage=raw_media_storage,
        help_text="PDF des planches de patron à imprimer / découper."
    )

    @property
    def photo_url(self):
        if not self.photo:
            return None
        name = self.photo.name or ''
        # URL Cloudinary stockée directement → la retourner telle quelle
        if name.startswith('http'):
            return name
        # Chemin local → construire l'URL normalement
        try:
            return self.photo.url
        except (ValueError, AttributeError):
            return None

    @property
    def pdf_url(self):
        if not self.pdf_patron:
            return None
        name = self.pdf_patron.name or ''
        if name.startswith('http'):
            return name
        try:
            return self.pdf_patron.url
        except (ValueError, AttributeError):
            return None

    def __str__(self):
        return self.titre

class Tutoriel(models.Model):
    patron = models.ForeignKey(Patron, on_delete=models.CASCADE, related_name='tutoriels')
    titre = models.CharField(max_length=100)
    typeTutoriel = models.CharField(max_length=30)
    urlVideoOuArticle = models.CharField(max_length=500)
    source = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.titre

class Projet(models.Model):
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='projets')
    vetements = models.ManyToManyField(Vetement)
    surfaceCalculee = models.FloatField()
    dateCreation = models.DateField(auto_now_add=True)
    statut = models.CharField(max_length=30, default='En cours')

    def __str__(self):
        return f"Projet #{self.id} de {self.utilisateur.username}"

class Recommandation(models.Model):
    projet = models.ForeignKey(Projet, on_delete=models.CASCADE, related_name='recommandations')
    patron = models.ForeignKey(Patron, on_delete=models.CASCADE)
    ordreProposition = models.IntegerField()
    estSelectionnerParUtilisateur = models.BooleanField(default=False)

class AchatPatron(models.Model):
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE)
    patron = models.ForeignKey(Patron, on_delete=models.CASCADE)
    dateAchat = models.DateField(auto_now_add=True)
    typePayement = models.CharField(max_length=30)
    nombrePieceUtilisees = models.IntegerField(default=0)
    montantEuro = models.FloatField(default=0.0)
    #coucouuu

class EtapePatron(models.Model):
    patron = models.ForeignKey(Patron, on_delete=models.CASCADE, related_name='etapes')
    numero = models.IntegerField()
    titre = models.CharField(max_length=200)
    description = models.TextField()
    conseil = models.TextField(blank=True, null=True)
    materiaux_etape = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='patrons/etapes/', null=True, blank=True)

    class Meta:
        ordering = ['numero']

    def __str__(self):
        return f"Étape {self.numero} - {self.titre} ({self.patron.titre})"

    @property
    def image_url(self):
        if not self.image:
            return None
        name = self.image.name or ''
        if name.startswith('http'):
            return name
        try:
            return self.image.url
        except (ValueError, AttributeError):
            return None

    @property
    def has_video(self):
        return self.gestes.exclude(video='').exists()


class PiecePatron(models.Model):
    """Une pièce à découper du patron (forme SVG + dimensions réelles).
    Les dimensions servent au placement futur des pièces sur le tissu."""
    patron = models.ForeignKey(Patron, on_delete=models.CASCADE, related_name='pieces')
    nom = models.CharField(max_length=100)
    quantite = models.PositiveIntegerField(default=1)
    largeur_cm = models.FloatField(null=True, blank=True)
    hauteur_cm = models.FloatField(null=True, blank=True)
    svg = models.FileField(
        upload_to='patrons/pieces/', null=True, blank=True,
        storage=raw_media_storage,
        help_text="Fichier SVG de la forme à découper."
    )
    ordre = models.IntegerField(default=0)

    class Meta:
        ordering = ['ordre', 'id']

    def __str__(self):
        return f"{self.nom} ×{self.quantite} ({self.patron.titre})"

    @property
    def svg_url(self):
        if not self.svg:
            return None
        name = self.svg.name or ''
        if name.startswith('http'):
            return name
        try:
            return self.svg.url
        except (ValueError, AttributeError):
            return None


class GestePatron(models.Model):
    """Un geste : sous-étape d'une EtapePatron. Une étape peut être découpée
    en plusieurs gestes, chacun avec sa propre vidéo et ses propres pièces
    utilisées. À la fin du dernier geste d'une étape, on passe à l'étape
    suivante."""
    etape = models.ForeignKey(EtapePatron, on_delete=models.CASCADE, related_name='gestes')
    numero = models.IntegerField()
    titre = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    video = models.FileField(
        upload_to='patrons/gestes/videos/', null=True, blank=True,
        storage=video_media_storage,
        help_text="Vidéo du geste, jouée en fond d'écran pendant l'étape."
    )
    pieces = models.ManyToManyField(PiecePatron, blank=True, related_name='gestes')

    class Meta:
        ordering = ['numero']

    def __str__(self):
        return f"Geste {self.numero} - {self.etape.titre} ({self.etape.patron.titre})"

    @property
    def video_url(self):
        if not self.video:
            return None
        name = self.video.name or ''
        if name.startswith('http'):
            return name
        try:
            return self.video.url
        except (ValueError, AttributeError):
            return None


class PlanDeCoupe(models.Model):
    """Placement figé des pièces sur le(s) tissu(s), validé lors de la
    vérification de faisabilité (faisabilite_patron). Sert à réafficher, en
    lecture seule, le plan de coupe choisi par l'utilisateur (page « Plan »
    de l'étape en cours) sans avoir à tout replacer.

    donnees = {
        "garment_ids": [id, ...],
        "pieces": [{"piece_id": int, "gid": int, "x": float, "y": float, "rot": float}, ...],
    }
    x/y = centre de la pièce en cm, dans le repère du tissu (gid) ; rot en degrés.
    """
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='plans_coupe')
    patron = models.ForeignKey(Patron, on_delete=models.CASCADE, related_name='plans_coupe')
    donnees = models.JSONField(default=dict, blank=True)
    date_maj = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('utilisateur', 'patron')

    def __str__(self):
        return f"Plan de coupe – {self.utilisateur.username} – {self.patron.titre}"


class ProgressionProjet(models.Model):
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='progressions')
    patron = models.ForeignKey(Patron, on_delete=models.CASCADE, related_name='progressions')
    etape_actuelle = models.IntegerField(default=1)
    geste_actuelle = models.IntegerField(default=1)
    date_debut = models.DateTimeField(auto_now_add=True)
    date_derniere_activite = models.DateTimeField(auto_now=True)
    termine = models.BooleanField(default=False)
    vetements_projet = models.ManyToManyField('Vetement', blank=True, related_name='progressions_projet')

    class Meta:
        unique_together = ('utilisateur', 'patron')

    def __str__(self):
        return f"{self.utilisateur.username} – {self.patron.titre} (étape {self.etape_actuelle})"


class PatronLike(models.Model):
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='patron_likes')
    patron = models.ForeignKey(Patron, on_delete=models.CASCADE, related_name='likes')
    date_like = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('utilisateur', 'patron')

    def __str__(self):
        return f"{self.utilisateur.username} aime {self.patron.titre}"


# ── Modèles Communauté ──────────────────────────────────────────────────────

class Hashtag(models.Model):
    nom = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return f"#{self.nom}"


class PostCommunaute(models.Model):
    TYPE_CHOICES = [
        ('fait-main', 'Fait main'),
        ('upcycling', 'Upcycling'),
        ('teinture', 'Teinture naturelle'),
        ('patron', 'Patron'),
        ('reparation', 'Réparation'),
    ]
    NIVEAU_CHOICES = [
        ('debutant', 'Débutant'),
        ('intermediaire', 'Intermédiaire'),
        ('confirme', 'Confirmé'),
    ]

    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='posts_communaute')
    titre = models.CharField(max_length=200)
    description = models.TextField()
    image = models.ImageField(upload_to='posts/', null=True, blank=True)
    type_creation = models.CharField(max_length=30, choices=TYPE_CHOICES, default='fait-main')
    niveau = models.CharField(max_length=30, choices=NIVEAU_CHOICES, default='debutant')
    patron_lie = models.ForeignKey(Patron, on_delete=models.SET_NULL, null=True, blank=True, related_name='posts_communaute')
    date_creation = models.DateTimeField(auto_now_add=True)
    nb_vues = models.PositiveIntegerField(default=0)
    hashtags = models.ManyToManyField(Hashtag, blank=True, related_name='posts')

    class Meta:
        ordering = ['-date_creation']

    def __str__(self):
        return f"{self.titre} par {self.utilisateur.username}"

    @property
    def display_image_url(self):
        """URL de l'image, en résolvant les images statiques de démo sans passer par Cloudinary."""
        if not self.image:
            return None
        name = self.image.name or ''
        # Images de démo stockées en static (évite Cloudinary pour les fichiers locaux)
        if name.startswith('posts/real-'):
            from django.templatetags.static import static
            filename = name.split('/')[-1]
            return static(f'core/images/communaute/posts/{filename}')
        try:
            return self.image.url
        except Exception:
            return None

    @property
    def nb_likes(self):
        return self.likes.count()

    @property
    def nb_commentaires(self):
        return self.commentaires.count()


class LikePost(models.Model):
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='post_likes')
    post = models.ForeignKey(PostCommunaute, on_delete=models.CASCADE, related_name='likes')
    date_like = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('utilisateur', 'post')

    def __str__(self):
        return f"{self.utilisateur.username} aime {self.post.titre}"


class SauvegardePost(models.Model):
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='sauvegardes')
    post = models.ForeignKey(PostCommunaute, on_delete=models.CASCADE, related_name='sauvegardes')
    date_sauvegarde = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('utilisateur', 'post')

    def __str__(self):
        return f"{self.utilisateur.username} a sauvegardé {self.post.titre}"


class CommentairePost(models.Model):
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='commentaires_posts')
    post = models.ForeignKey(PostCommunaute, on_delete=models.CASCADE, related_name='commentaires')
    contenu = models.TextField()
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date_creation']

    def __str__(self):
        return f"Commentaire de {self.utilisateur.username} sur {self.post.titre}"


class Suivi(models.Model):
    suiveur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='suivis')
    suivi = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='followers')
    date_suivi = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('suiveur', 'suivi')

    def __str__(self):
        return f"{self.suiveur.username} suit {self.suivi.username}"


class Badge(models.Model):
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='badges')
    nom = models.CharField(max_length=100)
    emoji = models.CharField(max_length=10, default='🌿')
    description = models.CharField(max_length=255, blank=True)
    date_obtention = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('utilisateur', 'nom')

    def __str__(self):
        return f"{self.emoji} {self.nom} – {self.utilisateur.username}"


# ── Communauté « atelier » (onglet Partage) ─────────────────────────────────
# Les modèles du jeu (profil, saisons, ligues, écussons, duels, salons,
# événements, quêtes, troc, entraide) vivent dans un module dédié pour ne pas
# alourdir celui-ci. L'import en fin de fichier suffit à ce que Django les
# rattache à l'application `core`.
from .models_communaute import *  # noqa: E402,F401,F403
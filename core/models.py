from django.db import models
from django.contrib.auth.models import AbstractUser

class Utilisateur(AbstractUser):
    consentementRGPD = models.BooleanField(default=False)
    soldePieces = models.IntegerField(default=0)

    niveau_couture = models.CharField(max_length=30, blank=True, null=True)
    envies_creation = models.CharField(max_length=255, blank=True, null=True)

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

    def __str__(self):
        return f"{self.nomVetement} - {self.utilisateur.username}"

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
    video_url = models.CharField(max_length=500, blank=True, null=True)
    conseil = models.TextField(blank=True, null=True)
    materiaux_etape = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['numero']

    def __str__(self):
        return f"Étape {self.numero} - {self.titre} ({self.patron.titre})"


class ProgressionProjet(models.Model):
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='progressions')
    patron = models.ForeignKey(Patron, on_delete=models.CASCADE, related_name='progressions')
    etape_actuelle = models.IntegerField(default=1)
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
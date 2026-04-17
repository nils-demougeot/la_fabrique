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

    def __str__(self):
        return f"{self.nomVetement} - {self.utilisateur.username}"

class Patron(models.Model):
    titre = models.CharField(max_length=30)
    description = models.CharField(max_length=100)
    typeObjet = models.CharField(max_length=30)
    surfaceMin = models.FloatField()
    surfaceMax = models.FloatField()
    estPremium = models.BooleanField(default=False)
    difficulte = models.IntegerField()

    def __str__(self):
        return self.titre

class Tutoriel(models.Model):
    patron = models.ForeignKey(Patron, on_delete=models.CASCADE, related_name='tutoriels')
    titre = models.CharField(max_length=30)
    typeTutoriel = models.CharField(max_length=30)
    urlVideoOuArticle = models.CharField(max_length=100)
    source = models.CharField(max_length=30)

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
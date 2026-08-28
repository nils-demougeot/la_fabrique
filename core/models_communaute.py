"""Modèles de l'onglet Partage (communauté « atelier »).

Tout l'onglet Partage — écrans 37a / 46a / 46b et leurs sous-pages 45a→45j —
s'appuie sur les modèles ci-dessous. La logique métier (calcul de niveau,
série de jours, classement, quêtes…) vit dans ``core/gamification.py`` : les
modèles ne portent que le stockage et les accès directs.

Ce module est importé en fin de ``core/models.py`` pour que Django découvre
les modèles dans l'application ``core``.
"""

from django.db import models

from .models import Utilisateur, Patron


class ProfilJeu(models.Model):
    """État de jeu d'une couturière : XP, série de jours, gels, quartier.

    Créé à la volée par ``gamification.profil_de(user)`` — ne jamais supposer
    qu'il existe déjà pour un utilisateur donné.
    """
    utilisateur = models.OneToOneField(Utilisateur, on_delete=models.CASCADE, related_name='profil_jeu')

    xp_total = models.PositiveIntegerField(default=0)

    # Série : nombre de jours d'atelier consécutifs. `derniere_activite` est la
    # date (pas l'instant) du dernier jour compté, ce qui permet de décider si
    # la série continue, dort, ou doit être cassée.
    serie_actuelle = models.PositiveIntegerField(default=0)
    serie_record = models.PositiveIntegerField(default=0)
    derniere_activite = models.DateField(null=True, blank=True)
    gels = models.PositiveIntegerField(default=2)

    ville = models.CharField(max_length=60, default='Lyon', blank=True)
    quartier = models.CharField(max_length=60, default='Croix-Rousse', blank=True)
    arrondissement = models.CharField(max_length=20, blank=True, default='Lyon 4ᵉ')

    # Teinte du jeton rond (initiales) : la même couleur suit la couturière
    # d'un écran à l'autre. Vide = teinte déduite de la clé du compte.
    TEINTES = [
        ('t-or', 'Or'),
        ('t-vert', 'Vert'),
        ('t-violet', 'Violet'),
        ('t-corail', 'Corail'),
    ]
    teinte = models.CharField(max_length=12, choices=TEINTES, blank=True, default='')

    # Code de parrainage affiché dans l'onglet Amis (« TON CODE D'ATELIER »).
    code_atelier = models.CharField(max_length=16, unique=True, null=True, blank=True)
    parraine_par = models.ForeignKey(
        Utilisateur, on_delete=models.SET_NULL, null=True, blank=True, related_name='filleules'
    )

    # Jours de la semaine en cours déjà travaillés, sérialisés « 0,1,3,4 »
    # (lundi = 0). Alimente le calendrier hebdomadaire de l'écran 45b.
    jours_semaine = models.CharField(max_length=20, blank=True, default='')
    semaine_cle = models.CharField(max_length=16, blank=True, default='')

    # Jours de la semaine en cours où un gel a réellement protégé la série
    # (même sérialisation que `jours_semaine`). Sans cette trace, l'écran de
    # série ne peut pas distinguer « un gel a comblé ce jour » de « rien ne
    # s'y est passé » — les deux se ressemblent une fois le jour passé.
    jours_geles = models.CharField(max_length=20, blank=True, default='')

    # Dernier niveau dont la joueuse a vu la célébration. Le niveau lui-même
    # se recalcule depuis les CP à chaque affichage : sans cette trace, on ne
    # saurait pas qu'il vient de monter — ni s'arrêter de fêter l'événement.
    niveau_vu = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"Profil jeu de {self.utilisateur.username} ({self.xp_total} XP)"

    @property
    def initiales(self):
        u = self.utilisateur
        prenom = (u.first_name or u.username or '?').strip()
        nom = (u.last_name or '').strip()
        if nom:
            return (prenom[0] + nom[0]).upper()
        parts = prenom.split()
        if len(parts) > 1:
            return (parts[0][0] + parts[1][0]).upper()
        return prenom[:2].upper()

    @property
    def nom_affiche(self):
        u = self.utilisateur
        if u.first_name:
            return f"{u.first_name} {u.last_name[0]}." if u.last_name else u.first_name
        return u.username

    @property
    def prenom_affiche(self):
        u = self.utilisateur
        return u.first_name or u.username

    @property
    def jours_travailles(self):
        """Indices des jours de la semaine déjà validés, en entiers."""
        return [int(j) for j in self.jours_semaine.split(',') if j.strip().isdigit()]

    @property
    def jours_geles_travailles(self):
        """Indices des jours de la semaine réellement comblés par un gel."""
        return [int(j) for j in self.jours_geles.split(',') if j.strip().isdigit()]


class Saison(models.Model):
    """Une saison de ligue (« SAISON 03 · TOILE »). Une seule est active."""
    numero = models.PositiveIntegerField(unique=True)
    nom = models.CharField(max_length=40, default='Toile')
    date_debut = models.DateField()
    date_fin = models.DateField()
    active = models.BooleanField(default=False)

    class Meta:
        ordering = ['-numero']

    def __str__(self):
        return f"Saison {self.numero:02d} · {self.nom}"

    @property
    def libelle(self):
        return f"SAISON {self.numero:02d} · {self.nom.upper()}"


class Ecusson(models.Model):
    """Catalogue des écussons (badges hexagonaux, écran 45e).

    ``couleur_haut`` / ``couleur_bas`` alimentent le dégradé de l'hexagone ;
    ``icone`` est la clé du pictogramme dessiné par le gabarit.
    """
    CATEGORIES = [
        ('matieres', 'Matières'),
        ('defis', 'Défis & rythme'),
        ('entraide', 'Entraide & savoir'),
    ]
    RANGS = [('toile', 'Toile'), ('laine', 'Laine'), ('or', 'Or')]

    code = models.SlugField(max_length=40, unique=True)
    nom = models.CharField(max_length=60)
    categorie = models.CharField(max_length=20, choices=CATEGORIES, default='matieres')
    rang = models.CharField(max_length=10, choices=RANGS, default='toile')
    condition = models.CharField(max_length=60, blank=True,
                                 help_text="Libellé court : « 148 pièces », « 30 jours »…")
    description = models.CharField(max_length=200, blank=True)
    icone = models.CharField(max_length=30, default='etoile')
    couleur_haut = models.CharField(max_length=9, default='#6BE0A0')
    couleur_bas = models.CharField(max_length=9, default='#12633A')
    niveau_requis = models.PositiveIntegerField(default=0)
    prix_pieces = models.PositiveIntegerField(default=0, help_text="0 = non vendu en boutique.")
    rarete = models.PositiveIntegerField(default=0, help_text="% de couturières qui l'ont obtenu.")
    secret = models.BooleanField(default=False, help_text="Affiché « ? » tant qu'il n'est pas obtenu.")
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['categorie', 'ordre', 'id']

    def __str__(self):
        return self.nom


class EcussonObtenu(models.Model):
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='ecussons')
    ecusson = models.ForeignKey(Ecusson, on_delete=models.CASCADE, related_name='obtentions')
    date_obtention = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('utilisateur', 'ecusson')
        ordering = ['-date_obtention']

    def __str__(self):
        return f"{self.ecusson.nom} – {self.utilisateur.username}"


class PalierSaison(models.Model):
    """Une étape du « sentier de la saison » : un seuil de CP et sa récompense.

    Le seuil est exprimé dans la même unité que la barre de progression de la
    carte d'atelier et du tableau de bord — les CP d'atelier, pas l'XP de
    saison : monter d'un niveau doit ouvrir un coffre.
    """
    saison = models.ForeignKey(Saison, on_delete=models.CASCADE, related_name='paliers')
    numero = models.PositiveIntegerField()
    points_requis = models.PositiveIntegerField(
        help_text="CP d'atelier nécessaires pour débloquer ce palier."
    )
    titre = models.CharField(max_length=120, default='Coffre')
    detail = models.CharField(max_length=160, blank=True)
    pieces = models.PositiveIntegerField(default=0)
    gels = models.PositiveIntegerField(default=0)
    patron = models.ForeignKey(Patron, on_delete=models.SET_NULL, null=True, blank=True)
    ecusson = models.ForeignKey(Ecusson, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['saison', 'numero']
        unique_together = ('saison', 'numero')

    def __str__(self):
        return f"Palier {self.numero} – {self.saison}"


class PalierReclame(models.Model):
    """Coffre déjà ouvert (écran 45d) : empêche de le réclamer deux fois."""
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='paliers_reclames')
    palier = models.ForeignKey(PalierSaison, on_delete=models.CASCADE, related_name='reclamations')
    date_reclamation = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('utilisateur', 'palier')


class ParticipationLigue(models.Model):
    """XP gagnés par une joueuse pendant une saison, dans une ligue donnée.

    Le classement (45a) est un ``order_by('-xp_saison')`` sur ce modèle,
    filtré par saison + ligue.
    """
    LIGUES = [
        ('bois', 'Ligue Bois'),
        ('toile', 'Ligue Toile'),
        ('argent', 'Ligue Argent'),
        ('or', 'Ligue Or'),
        ('platine', 'Ligue Platine'),
        ('diamant', 'Ligue Diamant'),
    ]
    ORDRE_LIGUES = [code for code, _ in LIGUES]

    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='participations_ligue')
    saison = models.ForeignKey(Saison, on_delete=models.CASCADE, related_name='participations')
    ligue = models.CharField(max_length=20, choices=LIGUES, default='or')
    xp_saison = models.PositiveIntegerField(default=0)
    pieces_finies = models.PositiveIntegerField(default=0)
    m2_sauves = models.FloatField(default=0.0)
    bilan_vu = models.BooleanField(default=False)

    class Meta:
        unique_together = ('utilisateur', 'saison')
        ordering = ['-xp_saison']

    def __str__(self):
        return f"{self.utilisateur.username} – {self.get_ligue_display()} ({self.xp_saison} XP)"

    @property
    def ligue_suivante(self):
        try:
            i = self.ORDRE_LIGUES.index(self.ligue)
        except ValueError:
            return None
        return self.ORDRE_LIGUES[i + 1] if i + 1 < len(self.ORDRE_LIGUES) else None

    @property
    def ligue_suivante_nom(self):
        code = self.ligue_suivante
        if not code:
            return self.get_ligue_display()
        return dict(self.LIGUES)[code]


class Duel(models.Model):
    """Duel de la semaine entre deux couturières (écran 45f)."""
    STATUTS = [('propose', 'Proposé'), ('en_cours', 'En cours'), ('termine', 'Terminé')]

    joueuse_a = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='duels_a')
    joueuse_b = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='duels_b')
    score_a = models.PositiveIntegerField(default=0)
    score_b = models.PositiveIntegerField(default=0)
    mise_pieces = models.PositiveIntegerField(default=20)
    xp_gain = models.PositiveIntegerField(default=60)
    date_debut = models.DateTimeField(auto_now_add=True)
    date_fin = models.DateTimeField()
    statut = models.CharField(max_length=12, choices=STATUTS, default='en_cours')

    class Meta:
        ordering = ['-date_debut']

    def __str__(self):
        return f"{self.joueuse_a.username} vs {self.joueuse_b.username}"

    def adversaire_de(self, user):
        return self.joueuse_b if self.joueuse_a_id == user.pk else self.joueuse_a

    def scores_pour(self, user):
        """Retourne (score du joueur, score de l'adversaire)."""
        if self.joueuse_a_id == user.pk:
            return self.score_a, self.score_b
        return self.score_b, self.score_a


class PieceDuel(models.Model):
    """Une pièce cousue comptée dans un duel (« Les pièces comptées »)."""
    duel = models.ForeignKey(Duel, on_delete=models.CASCADE, related_name='pieces_comptees')
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='pieces_duel')
    titre = models.CharField(max_length=120)
    surface_m2 = models.FloatField(default=0.0)
    motif = models.CharField(max_length=20, default='denim',
                             help_text="denim / lin / toile — couleur de la vignette.")
    date_ajout = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date_ajout']


class AnnonceTroc(models.Model):
    """Annonce du « Troc de chutes » (onglet Amis) et bulles troc en salon."""
    SENS = [('donne', 'À donner'), ('cherche', 'Recherche')]
    STATUTS = [('ouverte', 'Ouverte'), ('reservee', 'Réservée'), ('close', 'Close')]

    auteur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='annonces_troc')
    titre = models.CharField(max_length=160)
    sens = models.CharField(max_length=10, choices=SENS, default='donne')
    surface_m2 = models.FloatField(default=0.0)
    distance_m = models.PositiveIntegerField(default=800)
    motif = models.CharField(max_length=20, default='lin')
    statut = models.CharField(max_length=10, choices=STATUTS, default='ouverte')
    preneuse = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='trocs_pris')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        # « donne » avant « cherche » (tri décroissant sur le code) : la carte
        # verte mise en avant dans l'onglet Amis doit offrir du tissu, pas en
        # réclamer.
        ordering = ['-sens', '-date_creation']

    def __str__(self):
        return self.titre

    @property
    def distance_libelle(self):
        """« 800 M » en deçà du kilomètre, « 1,4 KM » au-delà."""
        if self.distance_m >= 1000:
            return f"{self.distance_m / 1000:.1f}".replace('.', ',') + ' KM'
        return f"{self.distance_m} M"

    @property
    def depuis(self):
        """Ancienneté en une seule unité : « il y a 1 h », « il y a 4 j ».

        `timesince` en gabarit produit « 4 jours, 3 heures » ; le tronquer
        laisserait une ellipse au milieu de la pastille.
        """
        from django.utils import timezone

        minutes = int((timezone.now() - self.date_creation).total_seconds() // 60)
        if minutes < 60:
            return f"il y a {max(1, minutes)} min"
        if minutes < 60 * 24:
            return f"il y a {minutes // 60} h"
        return f"il y a {minutes // (60 * 24)} j"


class Salon(models.Model):
    """Salon de discussion (écran 45g).

    Un salon « prive » est créé par une couturière et n'est visible que de ses
    membres ; les autres types sont ouverts à toute la communauté.
    """
    TYPES = [
        ('quartier', 'Quartier'),
        ('sos', 'SOS en direct'),
        ('theme', 'Thématique'),
        ('prive', 'Entre amies'),
    ]

    nom = models.CharField(max_length=80)
    description = models.CharField(max_length=200, blank=True)
    type_salon = models.CharField(max_length=12, choices=TYPES, default='quartier')
    motif = models.CharField(max_length=20, default='denim')
    # Salon de message privé à deux (créé par `gamification.salon_mp_avec`) :
    # un « prive » comme un salon entre amies, mais qu'on ne veut pas voir
    # apparaître dans la liste générale des salons (45g liste).
    est_mp = models.BooleanField(default=False)
    membres = models.ManyToManyField(Utilisateur, blank=True, related_name='salons')
    createur = models.ForeignKey(
        Utilisateur, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='salons_crees',
    )
    date_creation = models.DateTimeField(auto_now_add=True, null=True)

    @property
    def est_prive(self):
        return self.type_salon == 'prive'

    # Défi coopératif affiché en bas du fil.
    defi_titre = models.CharField(max_length=120, blank=True, default='Défi coop du salon')
    defi_objectif_m2 = models.FloatField(default=0.0)
    defi_avance_m2 = models.FloatField(default=0.0)
    defi_echeance = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.nom

    @property
    def defi_pourcentage(self):
        if not self.defi_objectif_m2:
            return 0
        return min(100, round(self.defi_avance_m2 / self.defi_objectif_m2 * 100))

    @property
    def defi_restant_m2(self):
        return round(max(0.0, self.defi_objectif_m2 - self.defi_avance_m2), 1)


class MessageSalon(models.Model):
    """Message d'un salon.

    ``type_message`` dit ce que le message porte en plus de son texte. Les
    pièces jointes sont des clés étrangères **explicites** plutôt qu'une
    relation générique : les types sont peu nombreux et connus, et chacun se
    requête et se pré-charge normalement.
    """
    TYPES = [
        ('texte', 'Texte'),
        ('photos', 'Photos'),
        ('troc', 'Annonce de troc'),
        ('patron', 'Patron partagé'),
        ('etape', 'Étape de patron'),
        ('tissu', 'Tissu de la banque'),
        ('defi_ville', 'Défi de ville'),
        ('duel', 'Invitation à un duel'),
        ('evenement', 'Rendez-vous de l\'agenda'),
        ('ecusson', 'Écusson obtenu'),
    ]

    salon = models.ForeignKey(Salon, on_delete=models.CASCADE, related_name='messages')
    auteur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='messages_salon')
    contenu = models.TextField(blank=True)
    type_message = models.CharField(max_length=12, choices=TYPES, default='texte')
    motifs = models.CharField(max_length=60, blank=True,
                              help_text="Vignettes de la galerie, séparées par des virgules : denim,toile")
    date_envoi = models.DateTimeField(auto_now_add=True)

    # ── Pièces jointes, une seule renseignée à la fois ──────────────────
    annonce = models.ForeignKey(AnnonceTroc, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='messages')
    patron = models.ForeignKey('Patron', on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='messages_salon')
    etape = models.ForeignKey('EtapePatron', on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='messages_salon')
    vetement = models.ForeignKey('Vetement', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='messages_salon')
    defi_ville = models.ForeignKey('DefiVille', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='messages_salon')
    duel = models.ForeignKey('Duel', on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='messages_salon')
    evenement = models.ForeignKey('EvenementCommunaute', on_delete=models.SET_NULL, null=True,
                                  blank=True, related_name='messages_salon')
    ecusson = models.ForeignKey('Ecusson', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='messages_salon')

    # Couturières citées avec « @ » dans le texte, résolues à l'envoi.
    mentions = models.ManyToManyField(Utilisateur, blank=True, related_name='mentions_salon')

    class Meta:
        ordering = ['date_envoi']

    def __str__(self):
        return f"{self.auteur.username} · {self.salon.nom}"

    @property
    def liste_motifs(self):
        return [m.strip() for m in self.motifs.split(',') if m.strip()]

    @property
    def a_piece_jointe(self):
        return self.type_message not in ('texte', 'photos')


class ReactionMessage(models.Model):
    """Réaction d'une couturière à un message, prise dans une courte liste.

    Le jeu d'émojis est volontairement fermé (``gamification.EMOJIS``) : les
    réactions se comptent et se regroupent, ce qu'un champ libre rendrait
    impraticable. Une couturière ne pose qu'une réaction par émoji et par
    message — reposer la même la retire.
    """
    message = models.ForeignKey(MessageSalon, on_delete=models.CASCADE, related_name='reactions')
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='reactions_salon')
    emoji = models.CharField(max_length=8)
    date_reaction = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('message', 'utilisateur', 'emoji')
        ordering = ['date_reaction']

    def __str__(self):
        return f"{self.emoji} · {self.utilisateur.username}"


class EvenementCommunaute(models.Model):
    """Atelier, live ou marathon affiché dans « Août à l'atelier » (37a) et
    détaillé par l'écran 45h."""
    FORMATS = [('presentiel', 'Sur place'), ('en_ligne', 'En ligne'), ('marathon', 'Marathon')]

    titre = models.CharField(max_length=140)
    description = models.TextField(blank=True)
    accroche = models.CharField(max_length=160, blank=True,
                                help_text="Ligne courte affichée sur la carte de l'agenda.")
    format_evenement = models.CharField(max_length=12, choices=FORMATS, default='presentiel')
    date_evenement = models.DateField()
    heure_debut = models.CharField(max_length=10, blank=True, default='14h')
    heure_fin = models.CharField(max_length=10, blank=True, default='18h')
    lieu = models.CharField(max_length=120, blank=True)
    adresse = models.CharField(max_length=200, blank=True)
    distance_km = models.FloatField(null=True, blank=True)
    machines_dispo = models.PositiveIntegerField(default=0)
    xp_gain = models.PositiveIntegerField(default=30)
    duree = models.CharField(max_length=40, blank=True)
    motif = models.CharField(max_length=20, default='denim')
    animatrice = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='evenements_animes')
    participants = models.ManyToManyField(Utilisateur, blank=True, through='InscriptionEvenement',
                                          related_name='evenements')

    class Meta:
        ordering = ['date_evenement']

    def __str__(self):
        return f"{self.titre} ({self.date_evenement:%d/%m})"

    MOIS_COURTS = ['JANV', 'FÉVR', 'MARS', 'AVR', 'MAI', 'JUIN',
                   'JUIL', 'AOÛT', 'SEPT', 'OCT', 'NOV', 'DÉC']

    @property
    def jour(self):
        return self.date_evenement.day

    @property
    def mois_court(self):
        return self.MOIS_COURTS[self.date_evenement.month - 1]

    @property
    def horaire(self):
        if self.heure_debut and self.heure_fin:
            return f"{self.heure_debut} → {self.heure_fin}"
        return self.heure_debut or ''


class InscriptionEvenement(models.Model):
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE)
    evenement = models.ForeignKey(EvenementCommunaute, on_delete=models.CASCADE)
    rappel_actif = models.BooleanField(default=True)
    date_inscription = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('utilisateur', 'evenement')


class Quete(models.Model):
    """Modèle de quête (quotidienne ou hebdomadaire). L'avancement réel d'une
    joueuse vit dans ``QueteUtilisateur``."""
    PERIODES = [('jour', 'Quotidienne'), ('semaine', 'Hebdomadaire')]

    code = models.SlugField(max_length=40, unique=True)
    libelle = models.CharField(max_length=140)
    detail = models.CharField(max_length=160, blank=True)
    periode = models.CharField(max_length=10, choices=PERIODES, default='jour')
    objectif = models.PositiveIntegerField(default=1)
    xp = models.PositiveIntegerField(default=20)
    pieces = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    ordre = models.PositiveIntegerField(default=0)

    # Bouton d'action de la quête mise en avant (écran 45i) : chaque quête
    # renvoie là où on peut réellement l'accomplir.
    cta_libelle = models.CharField(max_length=60, default='Continuer')
    cta_route = models.CharField(
        max_length=60, default='patrons',
        help_text="Nom d'URL Django vers l'écran qui permet d'accomplir la quête.",
    )

    class Meta:
        ordering = ['periode', 'ordre']

    def __str__(self):
        return self.libelle


class QueteUtilisateur(models.Model):
    """Avancement d'une quête pour une joueuse sur une période donnée.
    ``periode_cle`` vaut « 2026-08-15 » (jour) ou « 2026-W33 » (semaine)."""
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='quetes')
    quete = models.ForeignKey(Quete, on_delete=models.CASCADE, related_name='avancements')
    periode_cle = models.CharField(max_length=16)
    avancement = models.PositiveIntegerField(default=0)
    terminee = models.BooleanField(default=False)
    recompense_versee = models.BooleanField(default=False)

    class Meta:
        unique_together = ('utilisateur', 'quete', 'periode_cle')

    def __str__(self):
        return f"{self.quete.libelle} – {self.utilisateur.username}"

    @property
    def pourcentage(self):
        if not self.quete.objectif:
            return 0
        return min(100, round(self.avancement / self.quete.objectif * 100))


class CoffreQuotidien(models.Model):
    """Coffre débloqué quand toutes les quêtes du jour sont faites (45i → 45d)."""
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='coffres_quotidiens')
    periode_cle = models.CharField(max_length=16)
    pieces = models.PositiveIntegerField(default=30)
    ouvert = models.BooleanField(default=False)
    date_ouverture = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('utilisateur', 'periode_cle')


class DefiVille(models.Model):
    """Défi collectif d'une ville (« 500 m² recousus avant la fin du mois »)."""
    ville = models.CharField(max_length=60, default='Lyon')
    titre = models.CharField(max_length=160)
    objectif_m2 = models.FloatField(default=500)
    date_fin = models.DateField()
    actif = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.titre} ({self.ville})"

    @property
    def total_m2(self):
        return round(sum(c.m2 for c in self.contributions.all()), 1)

    @property
    def pourcentage(self):
        if not self.objectif_m2:
            return 0
        return min(100, round(self.total_m2 / self.objectif_m2 * 100))


class ContributionDefiVille(models.Model):
    """Total courant d'une couturière sur un défi.

    C'est un cumul entretenu par ``gamification.declarer_m2`` : le détail
    ligne à ligne vit dans ``DeclarationM2``. Garder le total ici évite de
    ré-agréger le journal à chaque affichage du classement des quartiers.
    """
    defi = models.ForeignKey(DefiVille, on_delete=models.CASCADE, related_name='contributions')
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='contributions_defi')
    quartier = models.CharField(max_length=60, default='Croix-Rousse')
    m2 = models.FloatField(default=0.0)
    date_maj = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('defi', 'utilisateur')
        ordering = ['-m2']

    def __str__(self):
        return f"{self.utilisateur.username} · {self.m2} m² ({self.quartier})"


class DeclarationM2(models.Model):
    """Une déclaration de surface sauvée, telle qu'elle a été saisie.

    Journal append-only : il alimente l'historique de l'écran de défi et rend
    le cumul de ``ContributionDefiVille`` vérifiable.
    """
    defi = models.ForeignKey(DefiVille, on_delete=models.CASCADE, related_name='declarations')
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='declarations_m2')
    m2 = models.FloatField()
    quartier = models.CharField(max_length=60, blank=True)
    commentaire = models.CharField(max_length=140, blank=True)
    date_declaration = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_declaration']

    def __str__(self):
        return f"{self.m2} m² · {self.utilisateur.username}"


class Amitie(models.Model):
    """Lien d'amitié en deux temps : `de` invite, `vers` accepte.

    Tant que `acceptee` est faux, la demande est en attente — elle n'entre ni
    dans le compte d'amies ni dans le classement entre amies. Le lien est
    ensuite valable dans les deux sens (voir ``gamification.ids_amies``).
    """
    de = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='amities_envoyees')
    vers = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='amities_recues')
    acceptee = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_reponse = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('de', 'vers')
        ordering = ['-date_creation']

    def __str__(self):
        etat = 'amies' if self.acceptee else 'en attente'
        return f"{self.de.username} → {self.vers.username} ({etat})"


class Notification(models.Model):
    """Événement à signaler à une couturière (pastille + feuille de la cloche).

    Volontairement dénormalisée : le titre et le lien sont figés à l'émission.
    Une notification est une trace de ce qui s'est passé à ce moment-là ; elle
    ne doit pas changer de sens parce que la donnée d'origine a bougé.
    """
    TYPES = [
        ('amitie_demande', "Demande d'amitié"),
        ('amitie_acceptee', 'Amitié acceptée'),
        ('duel', 'Duel'),
        ('coffre', 'Coffre disponible'),
        ('niveau', 'Montée de niveau'),
        ('reponse', 'Réponse à ta question'),
        ('salon', 'Message de salon'),
        ('evenement', 'Événement'),
        ('troc', 'Troc de chutes'),
        ('saison', 'Saison'),
        ('defi', 'Défi de ville'),
    ]

    destinataire = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='notifications')
    type_notif = models.CharField(max_length=20, choices=TYPES)
    titre = models.CharField(max_length=160)
    detail = models.CharField(max_length=200, blank=True)
    lien = models.CharField(max_length=200, blank=True, help_text="URL déjà résolue.")
    emetteur = models.ForeignKey(
        Utilisateur, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notifications_emises',
        help_text="Couturière à l'origine de l'événement, si elle existe.",
    )
    lue = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation']
        indexes = [models.Index(fields=['destinataire', 'lue', '-date_creation'])]

    def __str__(self):
        return f"{self.get_type_notif_display()} → {self.destinataire.username}"

    @property
    def depuis(self):
        """Ancienneté en une seule unité : « 12 min », « 3 h », « 2 j »."""
        from django.utils import timezone

        minutes = int((timezone.now() - self.date_creation).total_seconds() // 60)
        if minutes < 60:
            return f"{max(1, minutes)} min"
        if minutes < 60 * 24:
            return f"{minutes // 60} h"
        return f"{minutes // (60 * 24)} j"


class QuestionEntraide(models.Model):
    """Question posée à l'atelier (onglet Entraide)."""
    auteur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='questions_entraide')
    contenu = models.TextField()
    tags = models.CharField(max_length=120, blank=True,
                            help_text="Séparés par des virgules : denim,machine")
    motif = models.CharField(max_length=20, blank=True,
                             help_text="Vignette photo : denim / lin / toile / laine")
    resolue = models.BooleanField(default=False)
    xp_gain = models.PositiveIntegerField(default=15)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation']

    def __str__(self):
        return self.contenu[:60]

    @property
    def liste_tags(self):
        return [t.strip() for t in self.tags.split(',') if t.strip()]

    @property
    def nb_reponses(self):
        return self.reponses.count()

    @property
    def reponse_validee(self):
        return self.reponses.filter(validee=True).first()


class ReponseEntraide(models.Model):
    question = models.ForeignKey(QuestionEntraide, on_delete=models.CASCADE, related_name='reponses')
    auteur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='reponses_entraide')
    contenu = models.TextField()
    validee = models.BooleanField(default=False, help_text="Réponse retenue par l'autrice de la question.")
    coeurs = models.PositiveIntegerField(default=0)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-validee', 'date_creation']


class DisponibiliteEntraide(models.Model):
    """« Dispo maintenant » : couturières qui acceptent d'être sollicitées."""
    utilisateur = models.OneToOneField(Utilisateur, on_delete=models.CASCADE, related_name='dispo_entraide')
    specialites = models.CharField(max_length=120, blank=True, default='Denim, fermetures')
    en_ligne = models.BooleanField(default=True)
    delai_reponse_min = models.PositiveIntegerField(default=5)

    def __str__(self):
        return f"{self.utilisateur.username} – {self.specialites}"


class TransactionPieces(models.Model):
    """Historique des pièces (achats de la boutique 45c, gains de coffre…)."""
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='transactions_pieces')
    libelle = models.CharField(max_length=140)
    montant = models.IntegerField(help_text="Négatif pour un achat, positif pour un gain.")
    icone = models.CharField(max_length=20, default='piece')
    date_transaction = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_transaction']

    def __str__(self):
        return f"{self.libelle} ({self.montant:+d})"


class OffreBoutique(models.Model):
    """Article de la boutique de pièces (écran 45c)."""
    CATEGORIES = [
        ('pack', 'Offre du jour'),
        ('patron', 'Patrons'),
        ('gel', 'Bonus de série'),
        ('ecusson', 'Écussons'),
    ]

    code = models.SlugField(max_length=40, unique=True)
    nom = models.CharField(max_length=120)
    categorie = models.CharField(max_length=12, choices=CATEGORIES, default='patron')
    prix_pieces = models.PositiveIntegerField(default=50)
    prix_barre = models.PositiveIntegerField(default=0, help_text="Prix d'origine affiché barré. 0 = aucun.")
    remise = models.CharField(max_length=10, blank=True, help_text="Ex. « -10% »")
    quantite_gels = models.PositiveIntegerField(default=0)
    patron = models.ForeignKey(Patron, on_delete=models.SET_NULL, null=True, blank=True)
    ecusson = models.ForeignKey(Ecusson, on_delete=models.SET_NULL, null=True, blank=True)
    niveau_requis = models.PositiveIntegerField(default=0)
    motif = models.CharField(max_length=20, default='denim')
    mise_en_avant = models.BooleanField(default=False, help_text="Affiché en « offre du jour ».")
    fin_offre = models.DateTimeField(null=True, blank=True)
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['categorie', 'ordre', 'id']

    def __str__(self):
        return self.nom

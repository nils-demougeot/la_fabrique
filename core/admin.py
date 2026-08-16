from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (Utilisateur, Vetement, Patron, EtapePatron, PiecePatron, GestePatron, PlanDeCoupe, Tutoriel,
                     Projet, Recommandation, AchatPatron, ProgressionProjet, PatronLike,
                     PostCommunaute, LikePost, SauvegardePost, CommentairePost, Suivi, Hashtag)


class GestePatronInline(admin.StackedInline):
    model = GestePatron
    extra = 0
    ordering = ['numero']
    fields = ['numero', 'titre', 'description', 'video', 'pieces']
    filter_horizontal = ['pieces']


class EtapePatronInline(admin.StackedInline):
    model = EtapePatron
    extra = 0
    ordering = ['numero']
    fields = ['numero', 'titre', 'description', 'image', 'conseil', 'materiaux_etape']
    show_change_link = True


class PiecePatronInline(admin.TabularInline):
    model = PiecePatron
    extra = 0
    ordering = ['ordre']
    fields = ['ordre', 'nom', 'quantite', 'largeur_cm', 'hauteur_cm', 'svg']


class TutorielInline(admin.TabularInline):
    model = Tutoriel
    extra = 1
    fields = ['titre', 'typeTutoriel', 'source', 'urlVideoOuArticle', 'description']


@admin.register(Patron)
class PatronAdmin(admin.ModelAdmin):
    list_display  = ['titre', 'typeObjet', 'difficulte', 'duree', 'surfaceMin', 'surfaceMax', 'estPremium']
    list_filter   = ['estPremium', 'difficulte', 'typeObjet']
    search_fields = ['titre', 'description']
    inlines       = [EtapePatronInline, PiecePatronInline, TutorielInline]
    fieldsets = [
        (None, {
            'fields': ['titre', 'photo', 'description', 'typeObjet', 'pdf_patron', 'createur'],
        }),
        ('Matières & Outils', {
            'fields': ['matiere_requise', 'materiel'],
            'description': 'matiere_requise : matières acceptées séparées par virgules (ex: coton,lin). '
                           'materiel : outils nécessaires (aiguille, fil, ciseaux…).',
        }),
        ('Caractéristiques', {
            'fields': ['difficulte', 'duree', 'surfaceMin', 'surfaceMax'],
        }),
        ('Accès', {
            'fields': ['estPremium'],
        }),
    ]


@admin.register(Tutoriel)
class TutorielAdmin(admin.ModelAdmin):
    list_display  = ['titre', 'patron', 'typeTutoriel', 'source']
    search_fields = ['titre', 'patron__titre']


@admin.register(EtapePatron)
class EtapePatronAdmin(admin.ModelAdmin):
    list_display  = ['titre', 'patron', 'numero']
    list_filter   = ['patron']
    search_fields = ['titre', 'patron__titre']
    inlines       = [GestePatronInline]


admin.site.register(Utilisateur, UserAdmin)
admin.site.register(Vetement)
admin.site.register(Projet)
admin.site.register(Recommandation)
admin.site.register(AchatPatron)
admin.site.register(ProgressionProjet)
admin.site.register(PlanDeCoupe)
admin.site.register(PatronLike)
admin.site.register(PiecePatron)
admin.site.register(GestePatron)


class CommentairePostInline(admin.TabularInline):
    model = CommentairePost
    extra = 0
    fields = ['utilisateur', 'contenu', 'date_creation']
    readonly_fields = ['date_creation']


@admin.register(PostCommunaute)
class PostCommunauteAdmin(admin.ModelAdmin):
    list_display  = ['titre', 'utilisateur', 'type_creation', 'niveau', 'date_creation', 'nb_vues']
    list_filter   = ['type_creation', 'niveau']
    search_fields = ['titre', 'description', 'utilisateur__username']
    inlines       = [CommentairePostInline]
    readonly_fields = ['date_creation', 'nb_vues']


admin.site.register(Hashtag)
admin.site.register(LikePost)
admin.site.register(SauvegardePost)
admin.site.register(CommentairePost)
admin.site.register(Suivi)


# ── Communauté « atelier » (onglet Partage) ─────────────────────────────────

from .models import (  # noqa: E402
    Amitie, AnnonceTroc, CoffreQuotidien, ContributionDefiVille, DefiVille,
    DisponibiliteEntraide, Duel, Ecusson, EcussonObtenu, EvenementCommunaute,
    InscriptionEvenement, MessageSalon, OffreBoutique, PalierReclame,
    PalierSaison, ParticipationLigue, PieceDuel, ProfilJeu, Quete,
    QuestionEntraide, QueteUtilisateur, ReponseEntraide, Salon, Saison,
    TransactionPieces,
)


class PalierSaisonInline(admin.TabularInline):
    model = PalierSaison
    extra = 0
    ordering = ['numero']
    fields = ['numero', 'points_requis', 'titre', 'detail', 'pieces', 'gels', 'patron', 'ecusson']


@admin.register(Saison)
class SaisonAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'date_debut', 'date_fin', 'active']
    list_filter = ['active']
    inlines = [PalierSaisonInline]


@admin.register(ProfilJeu)
class ProfilJeuAdmin(admin.ModelAdmin):
    list_display = ['utilisateur', 'xp_total', 'serie_actuelle', 'serie_record',
                    'gels', 'quartier', 'code_atelier']
    search_fields = ['utilisateur__username', 'code_atelier']
    list_filter = ['ville', 'quartier']


@admin.register(ParticipationLigue)
class ParticipationLigueAdmin(admin.ModelAdmin):
    list_display = ['utilisateur', 'saison', 'ligue', 'xp_saison', 'pieces_finies', 'm2_sauves']
    list_filter = ['saison', 'ligue']
    search_fields = ['utilisateur__username']


@admin.register(Ecusson)
class EcussonAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code', 'categorie', 'rang', 'condition', 'rarete', 'secret']
    list_filter = ['categorie', 'rang', 'secret']
    search_fields = ['nom', 'code']


@admin.register(Duel)
class DuelAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'score_a', 'score_b', 'statut', 'date_fin']
    list_filter = ['statut']


class MessageSalonInline(admin.TabularInline):
    model = MessageSalon
    extra = 0
    fields = ['auteur', 'type_message', 'contenu', 'date_envoi']
    readonly_fields = ['date_envoi']


@admin.register(Salon)
class SalonAdmin(admin.ModelAdmin):
    list_display = ['nom', 'type_salon', 'defi_avance_m2', 'defi_objectif_m2']
    list_filter = ['type_salon']
    filter_horizontal = ['membres']
    inlines = [MessageSalonInline]


@admin.register(EvenementCommunaute)
class EvenementCommunauteAdmin(admin.ModelAdmin):
    list_display = ['titre', 'date_evenement', 'format_evenement', 'lieu', 'xp_gain']
    list_filter = ['format_evenement']
    search_fields = ['titre', 'lieu']


@admin.register(Quete)
class QueteAdmin(admin.ModelAdmin):
    list_display = ['libelle', 'code', 'periode', 'objectif', 'xp', 'pieces', 'active']
    list_filter = ['periode', 'active']


@admin.register(OffreBoutique)
class OffreBoutiqueAdmin(admin.ModelAdmin):
    list_display = ['nom', 'categorie', 'prix_pieces', 'niveau_requis', 'mise_en_avant']
    list_filter = ['categorie', 'mise_en_avant']


@admin.register(QuestionEntraide)
class QuestionEntraideAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'auteur', 'tags', 'resolue', 'date_creation']
    list_filter = ['resolue']
    search_fields = ['contenu', 'auteur__username']


@admin.register(DefiVille)
class DefiVilleAdmin(admin.ModelAdmin):
    list_display = ['titre', 'ville', 'objectif_m2', 'date_fin', 'actif']
    list_filter = ['ville', 'actif']


@admin.register(AnnonceTroc)
class AnnonceTrocAdmin(admin.ModelAdmin):
    list_display = ['titre', 'auteur', 'sens', 'surface_m2', 'statut']
    list_filter = ['sens', 'statut']


@admin.register(TransactionPieces)
class TransactionPiecesAdmin(admin.ModelAdmin):
    list_display = ['utilisateur', 'libelle', 'montant', 'date_transaction']
    search_fields = ['utilisateur__username', 'libelle']


# Modèles de liaison : l'inscription par défaut suffit pour le débogage.
for _modele in (Amitie, CoffreQuotidien, ContributionDefiVille, DisponibiliteEntraide,
                EcussonObtenu, InscriptionEvenement, PalierReclame, PieceDuel,
                QueteUtilisateur, ReponseEntraide):
    admin.site.register(_modele)
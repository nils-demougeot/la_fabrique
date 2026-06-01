from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (Utilisateur, Vetement, Patron, EtapePatron, Tutoriel, Projet, Recommandation,
                     AchatPatron, ProgressionProjet, PatronLike,
                     PostCommunaute, LikePost, SauvegardePost, CommentairePost, Suivi, Hashtag)


class EtapePatronInline(admin.StackedInline):
    model = EtapePatron
    extra = 0
    ordering = ['numero']
    fields = ['numero', 'titre', 'description', 'conseil', 'materiaux_etape', 'video_url']


class TutorielInline(admin.TabularInline):
    model = Tutoriel
    extra = 1
    fields = ['titre', 'typeTutoriel', 'source', 'urlVideoOuArticle', 'description']


@admin.register(Patron)
class PatronAdmin(admin.ModelAdmin):
    list_display  = ['titre', 'typeObjet', 'difficulte', 'duree', 'surfaceMin', 'surfaceMax', 'estPremium']
    list_filter   = ['estPremium', 'difficulte', 'typeObjet']
    search_fields = ['titre', 'description']
    inlines       = [EtapePatronInline, TutorielInline]
    fieldsets = [
        (None, {
            'fields': ['titre', 'photo', 'description', 'typeObjet'],
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


admin.site.register(Utilisateur, UserAdmin)
admin.site.register(Vetement)
admin.site.register(Projet)
admin.site.register(Recommandation)
admin.site.register(AchatPatron)
admin.site.register(ProgressionProjet)
admin.site.register(PatronLike)


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
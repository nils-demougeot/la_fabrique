from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Utilisateur, Vetement, Patron, EtapePatron, Tutoriel, Projet, Recommandation, AchatPatron


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
            'fields': ['titre', 'photo', 'description', 'typeObjet', 'materiel'],
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
# core/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Utilisateur, Vetement, Patron, Tutoriel, Projet, Recommandation, AchatPatron

admin.site.register(Utilisateur, UserAdmin)

admin.site.register(Vetement)
admin.site.register(Patron)
admin.site.register(Tutoriel)
admin.site.register(Projet)
admin.site.register(Recommandation)
admin.site.register(AchatPatron)
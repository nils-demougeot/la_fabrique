"""Deux versions du design servies côte à côte.

    · « classique »  — le design de base, templates de core/templates/.
    · « fait-main »  — la DA papier déchiré / vichy. Seuls les templates
      qu'elle modifie vivent dans core/templates_fait_main/ ; pour tout le
      reste, elle retombe sur les templates classiques.

On bascule en ajoutant `?design=fait-main` (ou `?design=classique`) à
n'importe quelle URL : le choix est gardé dans un cookie, la navigation
reste donc dans la version choisie. Sans cookie, c'est le classique.

Côté rendu, chaque version a son propre `Engine` — et donc son propre cache
de templates : un cache commun resservirait à l'une la page compilée pour
l'autre. Le middleware pose la version de la requête dans une ContextVar,
que le backend lit à chaque `get_template`.
"""
from contextvars import ContextVar

from django.conf import settings
from django.template.backends.django import DjangoTemplates
from django.template.engine import Engine

CLASSIQUE = 'classique'
FAIT_MAIN = 'fait-main'
VERSIONS = (CLASSIQUE, FAIT_MAIN)

COOKIE = 'design'
DOSSIER_FAIT_MAIN = settings.BASE_DIR / 'core' / 'templates_fait_main'

_version = ContextVar('design_version', default=CLASSIQUE)


class DesignTemplates(DjangoTemplates):
    """Backend Django standard, doublé d'un moteur « fait main » dont le
    dossier de templates passe avant ceux de l'application."""

    def __init__(self, params):
        super().__init__(params)
        self._classique = self.engine
        moteur = self._classique
        self._fait_main = Engine(
            dirs=[DOSSIER_FAIT_MAIN, *moteur.dirs],
            app_dirs=moteur.app_dirs,
            context_processors=moteur.context_processors,
            debug=moteur.debug,
            libraries=moteur.libraries,
            builtins=[b for b in moteur.builtins if b not in Engine.default_builtins],
            string_if_invalid=moteur.string_if_invalid,
            file_charset=moteur.file_charset,
            autoescape=moteur.autoescape,
        )

    @property
    def engine(self):
        return self._fait_main if _version.get() == FAIT_MAIN else self._classique

    @engine.setter
    def engine(self, valeur):
        # Appelé une seule fois, par DjangoTemplates.__init__.
        self._classique = valeur


class DesignMiddleware:
    """Choisit la version du design pour la requête et la mémorise."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        demandee = request.GET.get(COOKIE)
        version = demandee if demandee in VERSIONS else request.COOKIES.get(COOKIE)
        if version not in VERSIONS:
            version = CLASSIQUE

        request.design = version
        jeton = _version.set(version)
        try:
            response = self.get_response(request)
        finally:
            _version.reset(jeton)

        if demandee in VERSIONS:
            response.set_cookie(COOKIE, demandee, max_age=60 * 60 * 24 * 365, samesite='Lax')
        return response

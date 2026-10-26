"""Plusieurs versions du design servies côte à côte.

    · « classique »  — le design de base, templates de core/templates/.
    · « fait-main »  — la DA papier déchiré / vichy. Seuls les templates
      qu'elle modifie vivent dans core/templates_fait_main/ ; pour tout le
      reste, elle retombe sur les templates classiques.
    · « scrapbook »  — variante de la page d'accueil seulement (fond kraft
      sombre, stickers et chutes de tissu, core/templates_scrapbook/) ; les
      autres pages sont celles de « fait-main ».

On bascule en ajoutant `?design=<version>` à n'importe quelle URL : le choix
est gardé dans un cookie, la navigation reste donc dans la version choisie.
Sans cookie, c'est le classique.

Côté rendu, chaque version a son propre `Engine` — et donc son propre cache
de templates : un cache commun resservirait à l'une la page compilée pour
l'autre. Le middleware pose la version de la requête dans une ContextVar,
que le backend lit à chaque `get_template`.
"""
from contextvars import ContextVar

from django.conf import settings
from django.dispatch import receiver
from django.template import engines
from django.template.backends.django import DjangoTemplates
from django.template.engine import Engine
from django.utils.autoreload import autoreload_started, file_changed

CLASSIQUE = 'classique'
FAIT_MAIN = 'fait-main'
SCRAPBOOK = 'scrapbook'

_CORE = settings.BASE_DIR / 'core'
# Dossiers consultés avant les templates de l'application, du plus
# spécifique au plus général.
DOSSIERS = {
    CLASSIQUE: [],
    FAIT_MAIN: [_CORE / 'templates_fait_main'],
    SCRAPBOOK: [_CORE / 'templates_scrapbook', _CORE / 'templates_fait_main'],
}
VERSIONS = tuple(DOSSIERS)

COOKIE = 'design'

_version = ContextVar('design_version', default=CLASSIQUE)


class DesignTemplates(DjangoTemplates):
    """Backend Django standard, doublé d'un moteur par version du design,
    dont les dossiers de templates passent avant ceux de l'application."""

    def __init__(self, params):
        super().__init__(params)
        moteur = self._moteurs[CLASSIQUE]
        for version, dossiers in DOSSIERS.items():
            if version == CLASSIQUE:
                continue
            self._moteurs[version] = Engine(
                dirs=[*dossiers, *moteur.dirs],
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
        return self._moteurs.get(_version.get(), self._moteurs[CLASSIQUE])

    @engine.setter
    def engine(self, valeur):
        # Appelé une seule fois, par DjangoTemplates.__init__.
        self._moteurs = {CLASSIQUE: valeur}

    def vider_caches_annexes(self):
        for version, moteur in self._moteurs.items():
            if version != CLASSIQUE:
                for loader in moteur.template_loaders:
                    loader.reset()


# ── Développement : l'autoreloader de Django ne surveille que les dossiers
# du moteur classique. Sans ces deux récepteurs, un template modifié dans
# templates_fait_main/ ou templates_scrapbook/ resterait servi depuis le
# cache jusqu'au redémarrage du serveur.
def _dossiers_annexes():
    return {d for dossiers in DOSSIERS.values() for d in dossiers}


@receiver(autoreload_started, dispatch_uid='design_surveiller_templates')
def _surveiller(sender, **kwargs):
    for dossier in _dossiers_annexes():
        sender.watch_dir(dossier, '**/*')


@receiver(file_changed, dispatch_uid='design_template_modifie')
def _template_modifie(sender, file_path, **kwargs):
    # Les moteurs annexes retombent aussi sur les templates classiques et en
    # gardent leur propre copie en cache : tout template modifié les concerne.
    if file_path.suffix != '.html':
        return None
    for backend in engines.all():
        if isinstance(backend, DesignTemplates):
            backend.vider_caches_annexes()
    if any(dossier in file_path.parents for dossier in _dossiers_annexes()):
        return True  # pris en charge : pas de redémarrage complet
    return None  # template classique : Django vide aussi son propre cache


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

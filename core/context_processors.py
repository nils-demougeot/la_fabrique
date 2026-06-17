from django.conf import settings


def feature_flags(request):
    """Expose les feature flags aux templates (ex. désactivation de la communauté en bêta)."""
    return {
        'COMMUNAUTE_ACTIVE': getattr(settings, 'COMMUNAUTE_ACTIVE', True),
    }

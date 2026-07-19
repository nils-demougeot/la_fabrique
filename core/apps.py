from django.apps import AppConfig
from django.conf import settings


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        # Précharge le modèle de détourage IA (rembg) en tâche de fond au démarrage
        # du process : le premier appel réel (import onnxruntime + init de session)
        # prend ~30s, ce qui serait sinon subi par le premier utilisateur.
        # Sans effet si REMBG_DETOURAGE_ENABLED=False (voir settings.py).
        if not settings.REMBG_DETOURAGE_ENABLED:
            return

        import threading

        def _warmup():
            try:
                from core.detourage import _get_session
                _get_session()
            except Exception:
                pass  # échec silencieux : le premier appel réel réessaiera normalement

        threading.Thread(target=_warmup, daemon=True).start()

import os

from django.conf import settings
from whitenoise.storage import CompressedManifestStaticFilesStorage


class PatchedCompressedManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """
    Fix for Django 5.2 + whitenoise 6.x incompatibility.

    Django 5.2's ManifestFilesMixin sets keep_intermediate_files = False,
    which causes intermediate hashed files to be deleted during post-processing.
    Whitenoise then tries to compress those deleted files and raises FileNotFoundError.

    Fixes:
    1. keep_intermediate_files = True: preserve intermediate files during hashing passes
    2. compress_files: skip files that no longer exist instead of crashing
    3. manifest_strict = False: tolérance au runtime sur les entrées de manifeste.
    4. hashed_name: ne pas faire échouer collectstatic quand un CSS référence un
       fichier introuvable (ex : admin/css/base.css → img/icon-debug.svg). On
       conserve alors la référence d'origine au lieu de lever MissingFileError.
    """

    keep_intermediate_files = True
    manifest_strict = False

    def hashed_name(self, name, content=None, filename=None):
        try:
            return super().hashed_name(name, content, filename)
        except ValueError:
            # Référence (souvent un asset de l'admin Django) absente du collecte :
            # on laisse l'URL telle quelle plutôt que de casser tout le build.
            return name

    def compress_files(self, paths):
        extensions = getattr(settings, "WHITENOISE_SKIP_COMPRESS_EXTENSIONS", None)
        self.compressor = self.create_compressor(extensions=extensions, quiet=True)

        for path in paths:
            if not self.compressor.should_compress(path):
                continue
            full_path = self.path(path)
            if not os.path.exists(full_path):
                continue
            prefix_len = len(full_path) - len(path)
            for compressed_path in self.compressor.compress(full_path):
                compressed_name = compressed_path[prefix_len:]
                yield path, compressed_name

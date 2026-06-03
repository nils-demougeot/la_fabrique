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
    """

    keep_intermediate_files = True

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

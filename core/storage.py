from concurrent.futures import ThreadPoolExecutor, as_completed

from django.conf import settings
from whitenoise.storage import CompressedManifestStaticFilesStorage


class PatchedCompressedManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """
    Workaround for whitenoise 6.12 + Python 3.14 incompatibility:
    convert the futures generator to a list before passing to as_completed,
    ensuring all tasks are submitted before any results are consumed.
    """

    def compress_files(self, paths):
        extensions = getattr(settings, "WHITENOISE_SKIP_COMPRESS_EXTENSIONS", None)
        self.compressor = self.create_compressor(extensions=extensions, quiet=True)

        def _compress_path(path):
            compressed = []
            full_path = self.path(path)
            prefix_len = len(full_path) - len(path)
            for compressed_path in self.compressor.compress(full_path):
                compressed_name = compressed_path[prefix_len:]
                compressed.append((path, compressed_name))
            return compressed

        paths_to_compress = [p for p in paths if self.compressor.should_compress(p)]

        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(_compress_path, p) for p in paths_to_compress]
            for future in as_completed(futures):
                yield from future.result()

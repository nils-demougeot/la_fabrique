"""Détourage automatique côté serveur par segmentation IA (rembg).

Remplace le seuillage colorimétrique historique (voir `autoDetectPolygon` en
JS dans ajout_textile.html, conservé tel quel comme repli) par un modèle de
segmentation pré-entraîné, nettement plus robuste aux fonds non uniformes.

Activation/désactivation : réglage `REMBG_DETOURAGE_ENABLED` (settings.py).
Toute erreur ici (import, inférence, réseau au premier téléchargement du
modèle) est censée être rattrapée par l'appelant (core.views.detourage_auto),
qui répond alors en échec pour laisser le JS retomber sur l'ancien algorithme.
"""
import logging
import threading
from io import BytesIO

import numpy as np
from PIL import Image as PILImage
from scipy import ndimage as ndi
from skimage.measure import approximate_polygon, find_contours, label, regionprops

logger = logging.getLogger('core')

# u2netp : modèle léger (~4.7 Mo), suffisant pour isoler un vêtement sur fond
# quelconque et adapté à un serveur peu dimensionné (pas de GPU nécessaire).
_MODEL_NAME = 'u2netp'
_MAX_DIM = 640  # downscale avant segmentation : accélère l'inférence sans perte utile
_MIN_AREA_RATIO = 0.02
_MAX_AREA_RATIO = 0.93
_BORDER_SATURATION_RATIO = 0.55
_POLY_MIN_POINTS = 8
_POLY_MAX_POINTS = 28

_session = None
_session_lock = threading.Lock()


def _get_session():
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                from rembg import new_session
                _session = new_session(_MODEL_NAME)
    return _session


def auto_polygon_rembg(image_bytes):
    """Détecte le contour d'un vêtement par segmentation IA.

    Renvoie une liste de points normalisés [{'x': .., 'y': ..}, ...] (même
    format que la sortie d'autoDetectPolygon côté client), ou None si aucun
    contour exploitable n'a été trouvé.
    """
    from rembg import remove

    with PILImage.open(BytesIO(image_bytes)) as im:
        im.load()
        im = im.convert('RGB')
        w0, h0 = im.size
        scale = min(1.0, _MAX_DIM / max(w0, h0))
        if scale < 1.0:
            im = im.resize(
                (max(1, round(w0 * scale)), max(1, round(h0 * scale))),
                PILImage.LANCZOS,
            )
        result = remove(im, session=_get_session())

    alpha = np.array(result.split()[-1])
    h, w = alpha.shape
    mask = alpha > 128

    structure = np.ones((3, 3), dtype=bool)
    mask = ndi.binary_opening(mask, structure=structure)
    mask = ndi.binary_closing(mask, structure=structure)

    total = w * h
    area = int(mask.sum())
    if area < total * _MIN_AREA_RATIO or area > total * _MAX_AREA_RATIO:
        return None

    # Rejet si la silhouette sature les 4 bords (fond mal isolé, cadre ambigu).
    if (mask[0, :].mean() > _BORDER_SATURATION_RATIO
            and mask[-1, :].mean() > _BORDER_SATURATION_RATIO
            and mask[:, 0].mean() > _BORDER_SATURATION_RATIO
            and mask[:, -1].mean() > _BORDER_SATURATION_RATIO):
        return None

    # Plus grande composante connexe.
    labeled = label(mask, connectivity=2)
    regions = regionprops(labeled)
    if not regions:
        return None
    biggest = max(regions, key=lambda r: r.area)
    comp = labeled == biggest.label

    # Tracé de contour (marching squares) : peut renvoyer plusieurs boucles
    # (bord extérieur + trous internes non comblés) — on garde la plus longue.
    contours = find_contours(comp.astype(np.float64), level=0.5)
    if not contours:
        return None
    contour = max(contours, key=len)  # points en (row, col) = (y, x)
    if len(contour) < _POLY_MIN_POINTS:
        return None

    # Simplification (Douglas-Peucker) avec ajustement de la tolérance pour
    # viser un nombre de points éditable à la main, comme côté client.
    tolerance = max(w, h) * 0.006
    simplified = approximate_polygon(contour, tolerance=tolerance)
    guard = 0
    while len(simplified) > _POLY_MAX_POINTS and guard < 6:
        tolerance *= 1.4
        simplified = approximate_polygon(contour, tolerance=tolerance)
        guard += 1
    guard = 0
    while len(simplified) < _POLY_MIN_POINTS and tolerance > 1 and guard < 12:
        tolerance *= 0.6
        simplified = approximate_polygon(contour, tolerance=tolerance)
        guard += 1

    # find_contours/approximate_polygon renvoient une boucle fermée (1er == dernier point).
    if len(simplified) > 1 and np.allclose(simplified[0], simplified[-1]):
        simplified = simplified[:-1]

    if len(simplified) < 3:
        return None

    return [
        {'x': min(1.0, max(0.0, float(col) / w)), 'y': min(1.0, max(0.0, float(row) / h))}
        for row, col in simplified
    ]

"""Génération du PDF d'un patron : toutes les pièces à découper, à **taille réelle**.

Les pièces sont disposées dans un grand « plan » à l'échelle 1:1 (en millimètres),
puis ce plan est découpé en tuiles A4. L'utilisateur imprime toutes les feuilles
(à 100 %, sans « ajuster à la page »), les recoupe le long des repères puis les
assemble en grille pour reconstituer les pièces en grandeur nature.

Aucune dépendance lourde : tout est dessiné en vectoriel avec ReportLab. Les formes
SVG enregistrées (si présentes) sont rendues fidèlement ; sinon on dessine le
contour réel de la pièce à partir de ses dimensions (largeur_cm × hauteur_cm).
"""
import math
import re
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas

# ── Géométrie de page (en mm) ────────────────────────────────────────────────
PAGE_W = 210.0
PAGE_H = 297.0
MARGIN = 8.0                      # marge tout autour : zone de découpe / collage
CONTENT_W = PAGE_W - 2 * MARGIN   # largeur utile d'une tuile (194 mm)
CONTENT_H = PAGE_H - 2 * MARGIN   # hauteur utile d'une tuile (281 mm)
GAP = 12.0                        # espace entre deux pièces dans le plan

# ── Couleurs : tout en noir & blanc (économie d'encre, pas de remplissage) ──
C_INK = Color(0, 0, 0)            # contours et titres
C_TEXT = Color(0, 0, 0)           # texte principal
C_MUTED = Color(0.40, 0.40, 0.40)  # texte secondaire
C_LINE = Color(0.70, 0.70, 0.70)   # traits légers / repères
C_TRIM = Color(0.55, 0.55, 0.55)   # cadre de découpe
C_HATCH = Color(0.72, 0.72, 0.72)  # hachures intérieures (très claires)
HATCH_STEP = 9.0                  # espacement des hachures (mm) — clairsemé


# ════════════════════════════════════════════════════════════════════════════
#  Analyse SVG → liste de segments cubiques absolus (en coordonnées viewBox)
# ════════════════════════════════════════════════════════════════════════════
_NUM = re.compile(r'[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?')
_KAPPA = 0.5522847498307936  # approximation d'arc de cercle par bézier cubique


def _floats(s):
    return [float(x) for x in _NUM.findall(s or '')]


def _attr(tag, name):
    m = re.search(name + r'\s*=\s*"([^"]*)"', tag) or re.search(name + r"\s*=\s*'([^']*)'", tag)
    return m.group(1) if m else None


def _q_to_c(p0, ctrl, p1):
    """Convertit une quadratique (p0, ctrl, p1) en cubique (c1, c2)."""
    c1 = (p0[0] + 2 / 3 * (ctrl[0] - p0[0]), p0[1] + 2 / 3 * (ctrl[1] - p0[1]))
    c2 = (p1[0] + 2 / 3 * (ctrl[0] - p1[0]), p1[1] + 2 / 3 * (ctrl[1] - p1[1]))
    return c1, c2


def _parse_path_d(d):
    """Renvoie une liste d'opérations absolues : ('M',x,y) ('L',x,y)
    ('C',x1,y1,x2,y2,x,y) ('Z',). Couvre M L H V C S Q T Z (+ minuscules).
    Les arcs 'A' sont approximés par un segment droit (rares sur un patron)."""
    ops = []
    tokens = re.findall(r'([MmLlHhVvCcSsQqTtAaZz])|(' + _NUM.pattern + r')', d or '')
    cmds = []
    cur_cmd = None
    nums = []
    def flush():
        if cur_cmd is not None:
            cmds.append((cur_cmd, nums[:]))
    for letter, num in tokens:
        if letter:
            flush()
            cur_cmd = letter
            nums.clear()
        elif num:
            nums.append(float(num))
    flush()

    cx = cy = 0.0          # position courante
    sx = sy = 0.0          # début du sous-chemin
    prev_c2 = None         # dernier point de contrôle (pour S)
    prev_q = None          # dernier point de contrôle quad (pour T)
    last = None

    def take(vals, n):
        for i in range(0, len(vals) - n + 1, n):
            yield vals[i:i + n]

    for cmd, vals in cmds:
        rel = cmd.islower()
        C = cmd.upper()
        if C == 'M':
            for j, (x, y) in enumerate(take(vals, 2)):
                if rel:
                    x += cx; y += cy
                if j == 0:
                    cx, cy = x, y; sx, sy = x, y
                    ops.append(('M', cx, cy))
                else:
                    cx, cy = x, y
                    ops.append(('L', cx, cy))
            prev_c2 = prev_q = None
        elif C == 'L':
            for x, y in take(vals, 2):
                if rel: x += cx; y += cy
                cx, cy = x, y; ops.append(('L', cx, cy))
            prev_c2 = prev_q = None
        elif C == 'H':
            for (x,) in take(vals, 1):
                cx = (cx + x) if rel else x; ops.append(('L', cx, cy))
            prev_c2 = prev_q = None
        elif C == 'V':
            for (y,) in take(vals, 1):
                cy = (cy + y) if rel else y; ops.append(('L', cx, cy))
            prev_c2 = prev_q = None
        elif C == 'C':
            for x1, y1, x2, y2, x, y in take(vals, 6):
                if rel: x1+=cx; y1+=cy; x2+=cx; y2+=cy; x+=cx; y+=cy
                ops.append(('C', x1, y1, x2, y2, x, y))
                prev_c2 = (x2, y2); cx, cy = x, y
            prev_q = None
        elif C == 'S':
            for x2, y2, x, y in take(vals, 4):
                if rel: x2+=cx; y2+=cy; x+=cx; y+=cy
                if prev_c2: x1 = 2*cx - prev_c2[0]; y1 = 2*cy - prev_c2[1]
                else: x1, y1 = cx, cy
                ops.append(('C', x1, y1, x2, y2, x, y))
                prev_c2 = (x2, y2); cx, cy = x, y
            prev_q = None
        elif C == 'Q':
            for qx, qy, x, y in take(vals, 4):
                if rel: qx+=cx; qy+=cy; x+=cx; y+=cy
                c1, c2 = _q_to_c((cx, cy), (qx, qy), (x, y))
                ops.append(('C', c1[0], c1[1], c2[0], c2[1], x, y))
                prev_q = (qx, qy); cx, cy = x, y
            prev_c2 = None
        elif C == 'T':
            for x, y in take(vals, 2):
                if rel: x+=cx; y+=cy
                if prev_q: qx = 2*cx - prev_q[0]; qy = 2*cy - prev_q[1]
                else: qx, qy = cx, cy
                c1, c2 = _q_to_c((cx, cy), (qx, qy), (x, y))
                ops.append(('C', c1[0], c1[1], c2[0], c2[1], x, y))
                prev_q = (qx, qy); cx, cy = x, y
            prev_c2 = None
        elif C == 'A':
            # approximation : segment droit jusqu'au point d'arrivée
            for *_ignored, x, y in take(vals, 7):
                if rel: x+=cx; y+=cy
                cx, cy = x, y; ops.append(('L', cx, cy))
            prev_c2 = prev_q = None
        elif C == 'Z':
            ops.append(('Z',)); cx, cy = sx, sy; prev_c2 = prev_q = None
    return ops


def _rounded_rect_ops(x, y, w, h, rx, ry):
    """Ops cubiques d'un rectangle (éventuellement arrondi)."""
    rx = max(0.0, min(rx, w / 2)); ry = max(0.0, min(ry, h / 2))
    if rx <= 0 or ry <= 0:
        return [('M', x, y), ('L', x + w, y), ('L', x + w, y + h),
                ('L', x, y + h), ('Z',)]
    kx, ky = rx * _KAPPA, ry * _KAPPA
    x2, y2 = x + w, y + h
    return [
        ('M', x + rx, y),
        ('L', x2 - rx, y),
        ('C', x2 - rx + kx, y, x2, y + ry - ky, x2, y + ry),
        ('L', x2, y2 - ry),
        ('C', x2, y2 - ry + ky, x2 - rx + kx, y2, x2 - rx, y2),
        ('L', x + rx, y2),
        ('C', x + rx - kx, y2, x, y2 - ry + ky, x, y2 - ry),
        ('L', x, y + ry),
        ('C', x, y + ry - ky, x + rx - kx, y, x + rx, y),
        ('Z',),
    ]


def _ellipse_ops(cx, cy, rx, ry):
    kx, ky = rx * _KAPPA, ry * _KAPPA
    return [
        ('M', cx + rx, cy),
        ('C', cx + rx, cy + ky, cx + kx, cy + ry, cx, cy + ry),
        ('C', cx - kx, cy + ry, cx - rx, cy + ky, cx - rx, cy),
        ('C', cx - rx, cy - ky, cx - kx, cy - ry, cx, cy - ry),
        ('C', cx + kx, cy - ry, cx + rx, cy - ky, cx + rx, cy),
        ('Z',),
    ]


def parse_svg_shape(svg_bytes):
    """Analyse un SVG et renvoie ``(vw, vh, ops)`` où ``ops`` est la liste des
    opérations cubiques absolues (coordonnées du viewBox). Renvoie ``None`` si
    rien d'exploitable. Tolérant : ne lève jamais d'exception."""
    try:
        text = svg_bytes.decode('utf-8', 'ignore') if isinstance(svg_bytes, bytes) else str(svg_bytes)
    except Exception:
        return None
    svg_tag = re.search(r'<svg[^>]*>', text, re.I)
    vw = vh = None
    if svg_tag:
        vb = _attr(svg_tag.group(0), 'viewBox')
        if vb:
            nums = _floats(vb)
            if len(nums) == 4:
                vw, vh = nums[2], nums[3]
        if vw is None:
            w = _attr(svg_tag.group(0), 'width'); h = _attr(svg_tag.group(0), 'height')
            if w and h:
                fw, fh = _floats(w), _floats(h)
                if fw and fh: vw, vh = fw[0], fh[0]

    ops = []
    for tag in re.findall(r'<(?:path|rect|polygon|polyline|circle|ellipse|line)\b[^>]*>', text, re.I):
        kind = re.match(r'<(\w+)', tag).group(1).lower()
        try:
            if kind == 'path':
                ops += _parse_path_d(_attr(tag, 'd'))
            elif kind == 'rect':
                x = float(_attr(tag, 'x') or 0); y = float(_attr(tag, 'y') or 0)
                w = float(_attr(tag, 'width') or 0); h = float(_attr(tag, 'height') or 0)
                rxa, rya = _attr(tag, 'rx'), _attr(tag, 'ry')
                rx = float(rxa) if rxa else (float(rya) if rya else 0)
                ry = float(rya) if rya else rx
                if w > 0 and h > 0:
                    ops += _rounded_rect_ops(x, y, w, h, rx, ry)
            elif kind in ('polygon', 'polyline'):
                pts = _floats(_attr(tag, 'points'))
                pairs = list(zip(pts[0::2], pts[1::2]))
                if pairs:
                    ops.append(('M', pairs[0][0], pairs[0][1]))
                    for px, py in pairs[1:]:
                        ops.append(('L', px, py))
                    if kind == 'polygon':
                        ops.append(('Z',))
            elif kind == 'circle':
                cx = float(_attr(tag, 'cx') or 0); cy = float(_attr(tag, 'cy') or 0)
                r = float(_attr(tag, 'r') or 0)
                if r > 0: ops += _ellipse_ops(cx, cy, r, r)
            elif kind == 'ellipse':
                cx = float(_attr(tag, 'cx') or 0); cy = float(_attr(tag, 'cy') or 0)
                rx = float(_attr(tag, 'rx') or 0); ry = float(_attr(tag, 'ry') or 0)
                if rx > 0 and ry > 0: ops += _ellipse_ops(cx, cy, rx, ry)
            elif kind == 'line':
                x1 = float(_attr(tag, 'x1') or 0); y1 = float(_attr(tag, 'y1') or 0)
                x2 = float(_attr(tag, 'x2') or 0); y2 = float(_attr(tag, 'y2') or 0)
                ops += [('M', x1, y1), ('L', x2, y2)]
        except (TypeError, ValueError):
            continue

    if not ops:
        return None
    if not vw or not vh:
        xs = [o[i] for o in ops for i in range(1, len(o), 2) if len(o) > 1]
        ys = [o[i] for o in ops for i in range(2, len(o), 2) if len(o) > 2]
        if xs and ys:
            vw, vh = max(xs) or 1, max(ys) or 1
        else:
            return None
    return (vw, vh, ops)


# ════════════════════════════════════════════════════════════════════════════
#  Construction de la liste des pièces (« items ») et placement dans le plan
# ════════════════════════════════════════════════════════════════════════════
def _svg_bytes(piece):
    """Lit le contenu du SVG d'une pièce, ou None (jamais d'exception)."""
    if not getattr(piece, 'svg', None):
        return None
    try:
        piece.svg.open('rb')
        try:
            return piece.svg.read()
        finally:
            piece.svg.close()
    except Exception:
        return None


def _build_items(pieces):
    """Transforme les PiecePatron en items à placer (un par exemplaire)."""
    items = []
    for pc in pieces:
        w = (pc.largeur_cm or 0) * 10.0   # cm → mm
        h = (pc.hauteur_cm or 0) * 10.0
        shape = parse_svg_shape(_svg_bytes(pc))
        if (w <= 0 or h <= 0) and shape:
            # Pas de dimensions réelles : on retombe sur le ratio du viewBox,
            # interprété en mm (cas limite, sans échelle fiable).
            vw, vh, _ = shape
            w = w or vw
            h = h or vh
        if w <= 0 or h <= 0:
            continue
        items.append({
            'name': pc.nom or 'Pièce',
            'qte': max(1, pc.quantite or 1),
            'w': w, 'h': h, 'shape': shape,
        })
    return items


def _pack(items, gap=GAP):
    """Placement « étagères » : remplit des rangées de gauche à droite.
    Définit it['x'], it['y'] (coin haut-gauche, mm). Renvoie (masterW, masterH)."""
    if not items:
        return 0.0, 0.0
    maxw = max(it['w'] for it in items)
    total_area = sum((it['w'] + gap) * (it['h'] + gap) for it in items)
    target = max(maxw, math.sqrt(total_area))  # plan à peu près carré
    items.sort(key=lambda it: it['h'], reverse=True)
    x = y = shelf_h = master_w = 0.0
    for it in items:
        if x > 0 and x + it['w'] > target:
            x = 0.0; y += shelf_h + gap; shelf_h = 0.0
        it['x'] = x; it['y'] = y
        x += it['w'] + gap
        shelf_h = max(shelf_h, it['h'])
        master_w = max(master_w, x - gap)
    master_h = y + shelf_h
    return master_w, master_h


# ════════════════════════════════════════════════════════════════════════════
#  Dessin
# ════════════════════════════════════════════════════════════════════════════
def _device_ops(it, to_dev):
    """Renvoie les opérations du contour de la pièce en coordonnées PDF (points).
    Utilise la forme SVG si disponible, sinon un rectangle (arrondi) réel."""
    shape = it['shape']
    if shape:
        vw, vh, ops = shape
        sx = it['w'] / vw if vw else 1
        sy = it['h'] / vh if vh else 1
        def conv(vx, vy):
            return to_dev(it['x'] + vx * sx, it['y'] + vy * sy)
    else:
        rr = min(it['w'], it['h']) * 0.04
        ops = _rounded_rect_ops(it['x'], it['y'], it['w'], it['h'], rr, rr)
        def conv(X, Y):
            return to_dev(X, Y)
    dops = []
    for op in ops:
        t = op[0]
        if t in ('M', 'L'):
            dops.append((t,) + conv(op[1], op[2]))
        elif t == 'C':
            a = conv(op[1], op[2]); b = conv(op[3], op[4]); e = conv(op[5], op[6])
            dops.append(('C', a[0], a[1], b[0], b[1], e[0], e[1]))
        elif t == 'Z':
            dops.append(('Z',))
    return dops


def _path_from_dops(c, dops):
    p = c.beginPath()
    for op in dops:
        if op[0] == 'M': p.moveTo(op[1], op[2])
        elif op[0] == 'L': p.lineTo(op[1], op[2])
        elif op[0] == 'C': p.curveTo(op[1], op[2], op[3], op[4], op[5], op[6])
        elif op[0] == 'Z': p.close()
    return p


def _draw_shape(c, it, to_dev):
    """Contour noir uniquement (pas de remplissage) + hachures intérieures
    clairsemées pour signaler l'intérieur de la pièce, en économisant l'encre."""
    dops = _device_ops(it, to_dev)
    if not dops:
        return
    xs = [op[i] for op in dops for i in range(1, len(op), 2)]
    ys = [op[i] for op in dops for i in range(2, len(op), 2)]
    if not xs or not ys:
        return
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)

    # Hachures diagonales (clippées à l'intérieur de la forme)
    c.saveState()
    c.clipPath(_path_from_dops(c, dops), stroke=0, fill=0)
    c.setStrokeColor(C_HATCH); c.setLineWidth(0.4)
    step = HATCH_STEP * mm
    b = (y0 - x1)
    b -= b % step
    while b <= (y1 - x0):
        c.line(x0, x0 + b, x1, x1 + b)   # droites y = x + b
        b += step
    c.restoreState()

    # Contour
    c.setStrokeColor(C_INK); c.setLineWidth(1.1)
    c.drawPath(_path_from_dops(c, dops), stroke=1, fill=0)


def _draw_tile(c, items, r, col, rows, cols, page_no, total_pages):
    """Dessine une tuile A4 (rangée r, colonne col) du plan."""
    ox, oy = col * CONTENT_W, r * CONTENT_H   # origine de la tuile dans le plan (mm)

    def to_dev(X, Y):
        """Plan (mm, origine haut-gauche, y vers le bas) → points PDF."""
        return ((MARGIN + (X - ox)) * mm, (PAGE_H - MARGIN - (Y - oy)) * mm)

    # Zone utile (rectangle de découpe), en points
    cx0, cy0 = MARGIN * mm, MARGIN * mm
    cw, ch = CONTENT_W * mm, CONTENT_H * mm

    def cell(rr, cc):
        return f"L{rr + 1}C{cc + 1}"

    # — Pièces (clippées à la zone utile) —
    c.saveState()
    clip = c.beginPath(); clip.rect(cx0, cy0, cw, ch); c.clipPath(clip, stroke=0, fill=0)
    for it in items:
        # n'afficher que les pièces qui touchent cette tuile
        if (it['x'] > ox + CONTENT_W or it['x'] + it['w'] < ox or
                it['y'] > oy + CONTENT_H or it['y'] + it['h'] < oy):
            continue
        _draw_shape(c, it, to_dev)
        # étiquette près du coin haut-gauche de la pièce
        lx, ly = to_dev(it['x'] + 4, it['y'] + 9)
        c.setFillColor(C_TEXT); c.setFont('Helvetica-Bold', 8)
        c.drawString(lx, ly, it['name'][:40])
        c.setFillColor(C_MUTED); c.setFont('Helvetica', 7)
        c.drawString(lx, ly - 9, f"{it['w']/10:.0f} × {it['h']/10:.0f} cm")
        # nombre d'exemplaires à découper, bien visible (cadre)
        qte = it.get('qte', 1)
        if qte > 1:
            txt = f"À découper {qte}×"
            c.setFont('Helvetica-Bold', 8.5)
            tw = c.stringWidth(txt, 'Helvetica-Bold', 8.5)
            bx, by = lx, ly - 26
            c.setStrokeColor(C_INK); c.setLineWidth(0.8)
            c.rect(bx - 3, by - 3, tw + 6, 14, stroke=1, fill=0)
            c.setFillColor(C_INK)
            c.drawString(bx, by, txt)
    c.restoreState()

    # — Repères de découpe / assemblage —
    c.saveState()
    c.setStrokeColor(C_TRIM); c.setLineWidth(0.5); c.setDash(3, 3)
    c.rect(cx0, cy0, cw, ch, stroke=1, fill=0)
    c.setDash()
    # croix de calage aux quatre coins
    c.setLineWidth(0.5)
    for (mx, my) in [(cx0, cy0), (cx0 + cw, cy0), (cx0, cy0 + ch), (cx0 + cw, cy0 + ch)]:
        c.line(mx - 4, my, mx + 4, my); c.line(mx, my - 4, mx, my + 4)

    # repères de voisinage sur les 4 côtés (pour placer/assembler les feuilles)
    c.setFont('Helvetica-Bold', 8); c.setFillColor(C_MUTED)
    if col + 1 < cols:                       # bord droit → feuille suivante
        c.drawRightString(cx0 + cw - 3, cy0 + ch / 2, f"{cell(r, col + 1)} →")
    if col > 0:                              # bord gauche ← feuille précédente
        c.drawString(cx0 + 3, cy0 + ch / 2, f"← {cell(r, col - 1)}")
    if r > 0:                                # bord haut ↑ rangée précédente
        c.drawCentredString(cx0 + cw / 2, cy0 + ch - 11, f"↑ {cell(r - 1, col)}")
    if r + 1 < rows:                         # bord bas ↓ rangée suivante
        c.drawCentredString(cx0 + cw / 2, cy0 + 4, f"↓ {cell(r + 1, col)}")

    # — Badge d'identité de la feuille, bien visible en haut (dans la marge) —
    badge = f"Feuille {cell(r, col)}"
    c.setFont('Helvetica-Bold', 13)
    bw = c.stringWidth(badge, 'Helvetica-Bold', 13)
    bpad = 6
    by = cy0 + ch + 4
    c.setFillColor(C_INK)
    c.rect(cx0, by, bw + 2 * bpad, 17, stroke=0, fill=1)   # pavé noir
    c.setFillColor(Color(1, 1, 1))                          # texte blanc
    c.drawString(cx0 + bpad, by + 4.5, badge)
    # rappel ligne/colonne à droite du badge
    c.setFillColor(C_MUTED); c.setFont('Helvetica', 8)
    c.drawString(cx0 + bw + 2 * bpad + 8, by + 5,
                 f"Rangée {r + 1}/{rows} · Colonne {col + 1}/{cols}")

    # bandeau d'assemblage en bas (rappel)
    c.setFont('Helvetica-Bold', 9); c.setFillColor(C_INK)
    c.drawString(cx0 + 2, cy0 - 7, f"{cell(r, col)}  ·  Rangée {r + 1}/{rows} · Colonne {col + 1}/{cols}")
    c.setFont('Helvetica', 7); c.setFillColor(C_MUTED)
    c.drawRightString(cx0 + cw, cy0 - 7, f"Feuille {page_no}/{total_pages} — assembler en grille")
    c.restoreState()
    c.showPage()


def _draw_logo(c, x, top_y, target_w):
    """Dessine le logo « La Fabrique » en noir, renvoie sa hauteur (points)."""
    try:
        from django.contrib.staticfiles import finders
        path = finders.find('core/images/logo-la-fabrique.svg')
        text = open(path, encoding='utf-8').read() if path else None
    except Exception:
        text = None
    if not text:
        return 0
    m = re.search(r'viewBox="([^"]+)"', text)
    vb = _floats(m.group(1)) if m else None
    if not vb or len(vb) != 4 or not vb[2]:
        return 0
    vw, vh = vb[2], vb[3]
    scale = target_w / vw

    def mp(vx, vy):
        return (x + vx * scale, top_y - vy * scale)

    c.setFillColor(C_INK)
    for d in re.findall(r'<path[^>]*\sd="([^"]+)"', text):
        p = c.beginPath()
        for op in _parse_path_d(d):
            t = op[0]
            if t == 'M': p.moveTo(*mp(op[1], op[2]))
            elif t == 'L': p.lineTo(*mp(op[1], op[2]))
            elif t == 'C':
                a = mp(op[1], op[2]); b = mp(op[3], op[4]); e = mp(op[5], op[6])
                p.curveTo(a[0], a[1], b[0], b[1], e[0], e[1])
            elif t == 'Z': p.close()
        c.drawPath(p, stroke=0, fill=1)
    return vh * scale


def _draw_cover(c, patron, items, rows, cols, master_w, master_h, total_pages):
    """Page de garde : logo, titre, contrôle d'échelle, plan d'assemblage, liste."""
    left = 16 * mm

    # — Logo La Fabrique en haut —
    logo_h = _draw_logo(c, left, (PAGE_H - 14) * mm, 42 * mm)
    y = (PAGE_H - 14) * mm - (logo_h + 22 if logo_h else 4)

    c.setFillColor(C_INK); c.setFont('Helvetica-Bold', 22)
    c.drawString(left, y, "Patron à découper")
    y -= 22
    c.setFillColor(C_TEXT); c.setFont('Helvetica-Bold', 14)
    c.drawString(left, y, (patron.titre or '')[:48])
    y -= 24

    c.setFillColor(C_MUTED); c.setFont('Helvetica', 9.5)
    intro = [
        "Imprimez toutes les feuilles sur du papier A4 à 100 % (désactivez « Ajuster à la page »).",
        "AVANT de découper, repérez chaque feuille par son code (L1C1, L1C2…) et placez-les",
        "selon le plan ci-dessous et les flèches imprimées sur les bords (→ L1C2, ↓ L2C1).",
        f"Assemblez-les en grille ({rows} rangée(s) × {cols} colonne(s)) en faisant coïncider les croix",
        "de calage, puis collez. Posez enfin les pièces sur le tissu pour les reporter et les couper.",
    ]
    for line in intro:
        c.drawString(left, y, line); y -= 13
    y -= 8

    # — Contrôle d'échelle : carré témoin de 5 cm —
    c.setFillColor(C_TEXT); c.setFont('Helvetica-Bold', 11)
    c.drawString(left, y, "1.  Vérifiez l'échelle d'impression"); y -= 16
    box = 50 * mm
    bx, by = left, y - box
    c.setStrokeColor(C_INK); c.setLineWidth(1.0)
    c.rect(bx, by, box, box, stroke=1, fill=0)
    c.setFillColor(C_INK); c.setFont('Helvetica-Bold', 10)
    c.drawCentredString(bx + box / 2, by + box / 2 + 4, "5 cm")
    c.setFont('Helvetica', 8)
    c.drawCentredString(bx + box / 2, by + box / 2 - 9, "× 5 cm")
    c.setFillColor(C_MUTED); c.setFont('Helvetica', 9)
    c.drawString(bx + box + 12, by + box - 10, "Ce carré doit mesurer exactement")
    c.drawString(bx + box + 12, by + box - 23, "5 × 5 cm une fois imprimé.")
    c.drawString(bx + box + 12, by + box - 36, "Sinon, revérifiez le réglage d'échelle")
    c.drawString(bx + box + 12, by + box - 49, "de votre imprimante (100 %).")
    y = by - 22

    # — Plan d'assemblage miniature (borné en largeur ET en hauteur) —
    c.setFillColor(C_TEXT); c.setFont('Helvetica-Bold', 11)
    c.drawString(left, y, "2.  Plan d'assemblage des feuilles"); y -= 14
    max_map_w = 66 * mm
    max_map_h = 52 * mm
    scale = min(max_map_w / (cols * CONTENT_W), max_map_h / (rows * CONTENT_H))
    map_w = cols * CONTENT_W * scale
    map_h = rows * CONTENT_H * scale
    mx0, my0 = left, y - map_h
    cell_w = CONTENT_W * scale
    fs = max(4.0, min(8.0, cell_w * 0.16))   # police adaptée à la taille des cellules
    for rr in range(rows):
        for cc in range(cols):
            px = mx0 + cc * CONTENT_W * scale
            py = my0 + (rows - 1 - rr) * CONTENT_H * scale
            c.setStrokeColor(C_LINE); c.setLineWidth(0.6)
            c.rect(px, py, cell_w - 1.5, CONTENT_H * scale - 1.5, stroke=1, fill=0)
            c.setFillColor(C_INK); c.setFont('Helvetica-Bold', fs)
            c.drawCentredString(px + cell_w / 2,
                                py + CONTENT_H * scale / 2 - fs * 0.35, f"L{rr + 1}C{cc + 1}")
    c.setFillColor(C_MUTED); c.setFont('Helvetica', 8)
    c.drawString(mx0 + map_w + 12, my0 + map_h - 10,
                 f"{total_pages - 1} feuille(s) de pièces.")
    c.drawString(mx0 + map_w + 12, my0 + map_h - 23,
                 f"Plan total : {master_w/10:.0f} × {master_h/10:.0f} cm.")
    y = my0 - 22

    # — Liste des pièces —
    c.setFillColor(C_TEXT); c.setFont('Helvetica-Bold', 11)
    c.drawString(left, y, "3.  Pièces du patron"); y -= 14
    c.setFillColor(C_MUTED); c.setFont('Helvetica', 8.5)
    c.drawString(left, y, "Chaque forme n'est imprimée qu'une fois : réutilisez-la autant de fois qu'indiqué.")
    y -= 16
    for it in items:
        if y < 30 * mm:
            break
        qte = it.get('qte', 1)
        c.setFillColor(C_INK); c.setFont('Helvetica', 9.5); c.drawString(left, y, "•")
        c.setFillColor(C_TEXT); c.setFont('Helvetica-Bold', 9.5)
        c.drawString(left + 12, y, it['name'][:30])
        c.setFillColor(C_MUTED); c.setFont('Helvetica', 9.5)
        c.drawString(left + 200, y, f"{it['w']/10:.0f} × {it['h']/10:.0f} cm")
        c.setFillColor(C_INK)
        c.setFont('Helvetica-Bold' if qte > 1 else 'Helvetica', 9.5)
        c.drawString(left + 290, y, f"à découper {qte}×")
        y -= 15

    if not items:
        c.setFillColor(C_MUTED); c.setFont('Helvetica', 10)
        c.drawString(left, y, "Aucune pièce avec des dimensions n'est enregistrée pour ce patron.")

    c.showPage()


# ════════════════════════════════════════════════════════════════════════════
#  Point d'entrée
# ════════════════════════════════════════════════════════════════════════════
def build_patron_pdf(patron, pieces):
    """Construit et renvoie les octets du PDF du patron."""
    items = _build_items(pieces)
    master_w, master_h = _pack(items)
    cols = max(1, math.ceil(master_w / CONTENT_W)) if master_w else 1
    rows = max(1, math.ceil(master_h / CONTENT_H)) if master_h else 1
    total_pages = 1 + (rows * cols if items else 0)

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Patron — {patron.titre}")
    _draw_cover(c, patron, items, rows, cols, master_w, master_h, total_pages)
    if items:
        page_no = 2
        for r in range(rows):
            for col in range(cols):
                _draw_tile(c, items, r, col, rows, cols, page_no, total_pages)
                page_no += 1
    c.save()
    return buf.getvalue()

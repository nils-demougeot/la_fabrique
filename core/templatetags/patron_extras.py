import re

from django import template
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

register = template.Library()

# Jeton posé dans le texte d'une consigne pour référencer une pièce précise,
# ex: "avant de surpiquer la pièce [[piece:2]]." — l'index est 0-based, dans
# le même ordre que la liste « pieces_display » du contexte (donc que le
# défilement des pièces affiché à l'écran).
_PIECE_REF_RE = re.compile(r'\[\[piece:(\d+)\]\]')


@register.filter(name='render_piece_refs', is_safe=True)
def render_piece_refs(text, pieces_display):
    """Remplace les jetons [[piece:i]] par un badge coloré numéroté (même
    couleur/numéro que dans le défilement des pièces), échappe le reste du
    texte, et convertit les retours à la ligne en <br>."""
    if not text:
        return ''
    pieces_list = list(pieces_display) if pieces_display is not None else []

    chunks = []
    last = 0
    for m in _PIECE_REF_RE.finditer(text):
        chunks.append(escape(text[last:m.start()]))
        idx = int(m.group(1))
        if 0 <= idx < len(pieces_list):
            pd = pieces_list[idx]
            chunks.append(format_html(
                '<span class="ep-inline-piece" style="background:{};color:{};">{}</span>',
                pd['bg'], pd['fg'], idx + 1,
            ))
        # Jeton hors limites (pièce supprimée depuis la rédaction) : ignoré.
        last = m.end()
    chunks.append(escape(text[last:]))

    html = ''.join(chunks).replace('\n', '<br>')
    return mark_safe(html)

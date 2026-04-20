"""Airline logo caching service.

Downloads airline logos from avs.io on first request and caches them locally
in app/static/img/airlines/. Returns a local URL on success, or an inline
SVG data URI fallback if the download fails.
"""
import os
import urllib.request

# Absolute path to the logo cache directory (resolved relative to this file)
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOGO_DIR = os.path.join(_BASE_DIR, 'static', 'img', 'airlines')

os.makedirs(_LOGO_DIR, exist_ok=True)


def get_logo_url(airline_code: str) -> str:
    """Return a URL for the airline logo image.

    Checks whether a cached PNG exists in static/img/airlines/{code}.png.
    If not, attempts to download it from avs.io and save it locally.
    On any failure returns a self-contained SVG data URI fallback.

    Args:
        airline_code: IATA airline code, e.g. 'SU', 'S7'.

    Returns:
        A local static URL string, or an SVG data URI string.
    """
    if not airline_code:
        return generate_svg_fallback('?')

    code = airline_code.upper()
    local_path = os.path.join(_LOGO_DIR, f'{code}.png')

    # Already cached — return the static URL
    if os.path.exists(local_path):
        return f'/static/img/airlines/{code}.png'

    # Try to download from avs.io
    remote_url = f'https://pics.avs.io/36/36/{code}.png'
    try:
        req = urllib.request.Request(
            remote_url,
            headers={'User-Agent': 'Mozilla/5.0 avia_web/1.0'},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = response.read()
        with open(local_path, 'wb') as fh:
            fh.write(data)
        return f'/static/img/airlines/{code}.png'
    except Exception:
        return generate_svg_fallback(code)


def generate_svg_fallback(code: str) -> str:
    """Return a data URI for a 36x36 SVG placeholder with the airline code.

    Args:
        code: Airline code; only the first two characters are shown.

    Returns:
        A ``data:image/svg+xml,...`` URI string.
    """
    label = (code[:2] if code else '?').upper()
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36">'
        '<rect width="36" height="36" rx="4" fill="#cccccc"/>'
        f'<text x="18" y="24" font-size="13" font-family="sans-serif" '
        f'text-anchor="middle" fill="#555555">{label}</text>'
        '</svg>'
    )
    # Minimal percent-encoding for embedding in a URI
    encoded = (svg
               .replace(' ', '%20')
               .replace('#', '%23')
               .replace('<', '%3C')
               .replace('>', '%3E')
               .replace('"', '%22'))
    return f'data:image/svg+xml,{encoded}'

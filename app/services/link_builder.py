from urllib.parse import quote


MARKER = '548874'
AVIASALES_BASE = 'https://www.aviasales.ru'
TP_MEDIA_BASE = 'https://tp.media/r'


def build_booking_url(link_fragment):
    """Build affiliate booking URL from API link fragment."""
    if not link_fragment:
        return None
    direct_url = f'{AVIASALES_BASE}{link_fragment}'
    return f'{TP_MEDIA_BASE}?marker={MARKER}&p=4114&u={quote(direct_url, safe="")}'

import logging
import time
import requests
from config import Config

logger = logging.getLogger(__name__)

API_BASE = 'https://api.travelpayouts.com'


def generate_discovery_ranges(step=None, max_price=None):
    """Generate full price ranges for discovery scan (step=100, max=35000 by default)."""
    step = step or Config.DISCOVERY_PRICE_STEP
    max_price = max_price or Config.DISCOVERY_MAX_PRICE
    ranges = []
    for low in range(1, max_price + 1, step):
        high = min(low + step - 1, max_price)
        ranges.append((low, high))
    return ranges


def generate_update_ranges(known_prices, padding=None, merge_gap=100):
    """Build price ranges around known prices from DB.

    Example: prices [3200, 3450, 8100, 14500]
    -> ranges: (3000, 3650), (7900, 8300), (14300, 14700)
    Close prices (3200, 3450) merge into one range.
    """
    padding = padding or Config.UPDATE_PRICE_PADDING
    if not known_prices:
        return []

    sorted_prices = sorted(set(known_prices))
    ranges = []
    current_min = sorted_prices[0] - padding
    current_max = sorted_prices[0] + padding

    for price in sorted_prices[1:]:
        if price - padding <= current_max + merge_gap:
            current_max = price + padding
        else:
            ranges.append((max(1, current_min), current_max))
            current_min = price - padding
            current_max = price + padding

    ranges.append((max(1, current_min), current_max))
    return ranges


class TravelpayoutsClient:
    def __init__(self):
        self.token = Config.AVIA_API
        self.session = requests.Session()
        self.session.params = {'token': self.token}

    def search_by_ranges(self, origin, destination, ranges):
        """Fetch direct flights for a route by querying given price ranges.
        Returns deduplicated list of tickets across all ranges."""
        url = f'{API_BASE}/aviasales/v3/search_by_price_range'
        all_tickets = []
        seen = set()

        for value_min, value_max in ranges:
            params = {
                'origin': origin,
                'destination': destination,
                'value_min': value_min,
                'value_max': value_max,
                'one_way': 'true',
                'direct': 'true',
                'currency': 'rub',
                'limit': 1000,
                'page': 1,
            }
            try:
                resp = self.session.get(url, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                if data.get('success') is False:
                    logger.error('API error %s->%s range %d-%d: %s',
                                 origin, destination, value_min, value_max, data)
                    continue

                tickets = data.get('data', [])
                new_count = 0
                for t in tickets:
                    key = (t.get('departure_at'), t.get('price'), t.get('duration'))
                    if key not in seen:
                        seen.add(key)
                        all_tickets.append(t)
                        new_count += 1

                if new_count:
                    logger.debug('SBPR %d-%d %s->%s: %d tickets, %d new',
                                 value_min, value_max, origin, destination,
                                 len(tickets), new_count)
            except Exception:
                logger.exception('Failed SBPR %d-%d %s->%s',
                                 value_min, value_max, origin, destination)
            time.sleep(0.2)

        return all_tickets

    def search_all_flights(self, origin, destination):
        """Discovery scan: full sweep with fine-grained price step."""
        ranges = generate_discovery_ranges()
        logger.info('Discovery SBPR: %d ranges for %s->%s', len(ranges), origin, destination)
        return self.search_by_ranges(origin, destination, ranges)

    def search_by_update_ranges(self, origin, destination, known_prices):
        """Price update scan: smart ranges around known prices."""
        ranges = generate_update_ranges(known_prices)
        if not ranges:
            logger.info('No known prices for %s->%s, skipping update scan', origin, destination)
            return []
        logger.info('Update SBPR: %d ranges for %s->%s (from %d known prices)',
                     len(ranges), origin, destination, len(known_prices))
        return self.search_by_ranges(origin, destination, ranges)

    def prices_for_dates(self, origin, destination, month):
        """Fetch flights per date for a month (YYYY-MM).
        Used to enrich data with airline/flight_number/departure time."""
        url = f'{API_BASE}/aviasales/v3/prices_for_dates'
        params = {
            'origin': origin,
            'destination': destination,
            'departure_at': month,
            'direct': 'true',
            'sorting': 'price',
            'limit': 1000,
            'one_way': 'true',
            'cy': 'rub',
            'unique': 'false',
        }
        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get('data', [])
        except Exception:
            logger.exception('Failed to fetch prices_for_dates %s->%s %s',
                             origin, destination, month)
            return []

    def fetch_airlines(self):
        """Fetch airline directory (Russian names)."""
        url = f'{API_BASE}/data/ru/airlines.json'
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.exception('Failed to fetch airlines')
            return []

"""Scrape flight data locally and send to RPi server via API.

Run this script on any PC with a browser. It will:
1. Open aviasales.ru in Chrome, intercept search results
2. Collect flight data for all dates and routes
3. POST the data to the RPi server for database storage
4. Repeat every N minutes (default: 10)

Usage:
    python scrape_and_send.py                       # one-shot
    python scrape_and_send.py --loop --interval 10  # every 10 min
    python scrape_and_send.py --days 60 --url https://avia-ai.ru
    python scrape_and_send.py --routes LED-CEK      # one direction only

Environment variables (or .env file):
    SCRAPE_API_KEY   — API key matching the server config
    SCRAPE_API_URL   — server URL (default: https://avia-ai.ru)
    CAPTCHA_API_KEY  — 2captcha.com API key for auto-solving Turnstile captcha
"""
import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import requests
from dotenv import load_dotenv
import os

# Add project root to path so we can import parse_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.parse_playwright import scrape_all

load_dotenv()

# --- Logging: console + rotating file ---
# File: logs/scraper.log next to this script. 5 files × 5 MB = 25 MB cap.
# All loggers (scrape_and_send, parse_playwright, etc.) share these handlers
# because they attach to the root logger.
_LOG_DIR = Path(__file__).resolve().parent / 'logs'
_LOG_DIR.mkdir(exist_ok=True)
_LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'

_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)
# Avoid duplicate handlers on re-import / reloader restart
if not any(isinstance(h, RotatingFileHandler) for h in _root_logger.handlers):
    _file_handler = RotatingFileHandler(
        _LOG_DIR / 'scraper.log',
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8',
    )
    _file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    _root_logger.addHandler(_file_handler)
if not any(isinstance(h, logging.StreamHandler)
           and not isinstance(h, RotatingFileHandler)
           for h in _root_logger.handlers):
    _stream_handler = logging.StreamHandler()
    _stream_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    _root_logger.addHandler(_stream_handler)

logger = logging.getLogger('scrape_and_send')

DEFAULT_API_URL = 'https://avia-ai.ru'
IMPORT_ENDPOINT = '/api/scrape/import'


def parse_proxies(proxy_str):
    """Parse SCRAPE_PROXIES env into list of Playwright proxy dicts.

    Format: comma-separated, each item is either empty (direct) or
    http://user:pass@host:port

    Returns list where None = direct connection, dict = proxy config.
    """
    if not proxy_str:
        return [None]

    result = []
    for item in proxy_str.split(','):
        item = item.strip()
        if not item:
            result.append(None)
            continue

        # Parse http://user:pass@host:port
        from urllib.parse import urlparse
        parsed = urlparse(item)
        proxy = {'server': f'{parsed.scheme}://{parsed.hostname}:{parsed.port}'}
        if parsed.username:
            proxy['username'] = parsed.username
        if parsed.password:
            proxy['password'] = parsed.password
        result.append(proxy)

    return result if result else [None]


def transform_flights(scrape_data):
    """Convert parse_playwright output to API import format.

    Args:
        scrape_data: dict {(origin, dest): {date_str: [flight_dicts]}}

    Returns:
        list of flight dicts ready for the import API
    """
    flights = []

    for (origin, dest), route_data in scrape_data.items():
        for date_str, day_flights in route_data.items():
            for f in day_flights:
                dep_unix = f.get('departure_unix', 0)
                if not dep_unix:
                    continue

                # Convert unix timestamp to UTC datetime
                dt_utc = datetime.fromtimestamp(dep_unix, tz=timezone.utc)
                depart_time_utc = dt_utc.strftime('%H:%M')

                # Prefer cheapest no-baggage fare, but fall back to the
                # overall cheapest tariff if the flight has no hand-luggage
                # option (some airlines/dates sell only baggage-included
                # tariffs — without this fallback those flights were being
                # silently dropped, which is the "missing night flight" bug).
                prices_list = f.get('prices', [])
                if not prices_list:
                    continue
                no_bag = [p for p in prices_list
                          if p.get('baggage_count', 0) == 0]
                cheapest = no_bag[0] if no_bag else prices_list[0]
                cheapest_price = cheapest.get('price', 0)

                if cheapest_price <= 0:
                    continue

                # Build aviasales search link
                origin = f['origin']
                dest = f['destination']
                dd = f['depart_date']  # "2026-02-15"
                arr_unix = f.get('arrival_unix', 0)
                try:
                    d = datetime.strptime(dd, '%Y-%m-%d')
                    link = f'/search/{origin}{d.day:02d}{d.month:02d}{dest}1'
                except ValueError:
                    link = ''

                flights.append({
                    'origin': origin,
                    'destination': dest,
                    'airline': f['operating_carrier'],
                    'flight_number': f['operating_number'],
                    'depart_date': dd,
                    'depart_time': depart_time_utc,
                    'departure_at': dt_utc.isoformat(),
                    'departure_unix': dep_unix,
                    'duration': f.get('duration_min'),
                    'price': cheapest_price,
                    'link': link,
                    'baggage_count': cheapest.get('baggage_count'),
                    'baggage_weight': cheapest.get('baggage_weight'),
                    'fare_name': cheapest.get('fare_name', ''),
                    'seats_available': cheapest.get('seats_available'),
                    'equipment': f.get('equipment', ''),
                    'arrive_time_local': f.get('arrive_time_local', ''),
                    'prices': f.get('prices', []),
                })

    return flights


def send_flights(flights, api_url, api_key):
    """POST flights to the server import endpoint.

    Args:
        flights: list of flight dicts
        api_url: base server URL (e.g. https://avia-ai.ru)
        api_key: API key string

    Returns:
        response JSON dict or None on error
    """
    url = api_url.rstrip('/') + IMPORT_ENDPOINT

    logger.info('Sending %d flights to %s ...', len(flights), url)

    try:
        resp = requests.post(
            url,
            json={'flights': flights},
            headers={
                'X-API-Key': api_key,
                'Content-Type': 'application/json',
            },
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        logger.info('Server response: %s', result)
        return result
    except requests.exceptions.RequestException as e:
        logger.error('Failed to send data: %s', e)
        if hasattr(e, 'response') and e.response is not None:
            logger.error('Response body: %s', e.response.text[:500])
        return None


def main():
    parser = argparse.ArgumentParser(description='Scrape flights and send to server')
    parser.add_argument('--days', type=int, default=30,
                        help='Number of days ahead to scrape (default: 30)')
    parser.add_argument('--url', type=str,
                        default=os.getenv('SCRAPE_API_URL', DEFAULT_API_URL),
                        help='Server API URL (default: from SCRAPE_API_URL env or avia-ai.ru)')
    parser.add_argument('--key', type=str,
                        default=os.getenv('SCRAPE_API_KEY', ''),
                        help='API key (default: from SCRAPE_API_KEY env)')
    parser.add_argument('--routes', type=str, default=None,
                        help='Routes to scrape, comma-separated (e.g. LED-CEK,CEK-LED)')
    parser.add_argument('--headless', action='store_true',
                        help='Run browser headless (needs Xvfb on Linux)')
    parser.add_argument('--save-json', type=str, default=None,
                        help='Save raw scrape data to JSON file (for debugging)')
    parser.add_argument('--loop', action='store_true',
                        help='Run continuously with --interval pause between cycles')
    parser.add_argument('--interval', type=int,
                        default=int(os.getenv('SCRAPE_INTERVAL', '30')),
                        help='Minutes between scrape cycles (default: from SCRAPE_INTERVAL env or 30)')
    parser.add_argument('--proxy', type=str, default=None,
                        help='Force specific proxy (http://user:pass@host:port) for this run')
    parser.add_argument('--solve-captcha', action='store_true',
                        help='Open browser and wait for manual captcha solve before scraping')
    parser.add_argument('--night-days', type=int, default=0,
                        help='Extended scrape depth (e.g. 90). Once a day at --night-hour, '
                             'scrape this many days instead of --days')
    parser.add_argument('--night-hour', type=int, default=0,
                        help='Hour (0-23) to trigger the extended night scrape (default: 0)')
    args = parser.parse_args()

    if not args.key:
        logger.error('No API key provided. Set SCRAPE_API_KEY env variable or use --key')
        sys.exit(1)

    # Parse routes
    routes = None
    if args.routes:
        routes = []
        for r in args.routes.split(','):
            parts = r.strip().upper().split('-')
            if len(parts) == 2:
                routes.append((parts[0], parts[1]))
            else:
                logger.error('Invalid route format: %s (expected ORIGIN-DEST)', r)
                sys.exit(1)

    # Manual captcha solve mode
    if args.solve_captcha:
        from app.services.parse_playwright import solve_captcha_interactive
        logger.info('Opening browser for manual captcha solve...')
        solve_captcha_interactive()
        logger.info('Captcha solved! Continuing with scraping...')

    # Parse proxy rotation list
    if args.proxy:
        # Single proxy forced via CLI
        proxies = parse_proxies(args.proxy)
        logger.info('Using forced proxy: %s',
                     proxies[0]['server'] if proxies[0] else 'direct')
    else:
        proxies = parse_proxies(os.getenv('SCRAPE_PROXIES', ''))
        if len(proxies) > 1:
            labels = []
            for p in proxies:
                labels.append(p['server'] if p else 'direct')
            logger.info('Proxy rotation: %s', ' -> '.join(labels))

    cycle = 0
    night_done_date = None  # track which date we already did the night run
    while True:
        cycle += 1
        cycle_start = time.time()

        # Rotate proxy: cycle through the list
        proxy = proxies[(cycle - 1) % len(proxies)]
        proxy_label = proxy['server'] if proxy else 'direct'

        # Decide how many days to scrape this cycle
        now_dt = datetime.now()
        today_date = now_dt.date()
        if (args.night_days
                and now_dt.hour == args.night_hour
                and night_done_date != today_date):
            days = args.night_days
            night_done_date = today_date
            logger.info('*** Night extended scrape: %d days ***', days)
        else:
            days = args.days

        try:
            logger.info('=== Cycle %d started [%s] ===', cycle, proxy_label)

            # Step 1: Scrape
            logger.info('Scraping: %d days, routes=%s, headless=%s, proxy=%s',
                        days, routes or 'all', args.headless, proxy_label)

            captcha_api_key = os.getenv('CAPTCHA_API_KEY', '')
            scrape_data = scrape_all(
                days_ahead=days,
                routes=routes,
                headless=args.headless,
                proxy=proxy,
                captcha_api_key=captcha_api_key or None,
            )

            # Step 2: Transform
            flights = transform_flights(scrape_data)
            logger.info('Transformed %d flights total', len(flights))

            if not flights:
                logger.warning('No flights scraped')
            else:
                # Optional: save raw data for debugging
                if args.save_json:
                    json_data = {}
                    for (o, d), route_data in scrape_data.items():
                        json_data[f'{o}-{d}'] = route_data
                    with open(args.save_json, 'w', encoding='utf-8') as fp:
                        json.dump(json_data, fp, ensure_ascii=False, indent=2)
                    logger.info('Raw data saved to %s', args.save_json)

                # Step 3: Send
                result = send_flights(flights, args.url, args.key)

                if result:
                    logger.info('Cycle %d done! Created: %d, Updated: %d, '
                                'Price changes: %d, Errors: %d',
                                cycle,
                                result.get('created', 0),
                                result.get('updated', 0),
                                result.get('price_changes', 0),
                                result.get('errors', 0))
                else:
                    logger.error('Failed to send data to server')

        except KeyboardInterrupt:
            raise
        except Exception:
            logger.exception('Cycle %d failed with error', cycle)

        if not args.loop:
            break

        # Re-read interval from .env (can be changed without restart)
        load_dotenv(override=True)
        interval = int(os.getenv('SCRAPE_INTERVAL', args.interval))

        # Wait for next cycle
        elapsed = time.time() - cycle_start
        wait = max(0, interval * 60 - elapsed)
        logger.info('Cycle %d took %.0f sec. Next in %.0f sec (%.1f min)...',
                     cycle, elapsed, wait, wait / 60)
        try:
            time.sleep(wait)
        except KeyboardInterrupt:
            logger.info('Interrupted by user, exiting.')
            break


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()

"""
Aviasales flight parser using Playwright.

Opens aviasales.ru search pages as parallel tabs in a single browser context,
intercepts JSON responses with full flight data
(prices, airlines, flight numbers, baggage, tariffs).

Uses system Chrome with persistent profile to bypass bot detection.
On headless servers (RPi), use Xvfb virtual display + headless=False.
"""
import logging
import json
import os
import platform
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

AVIASALES_SEARCH_URL = (
    'https://www.aviasales.ru/search/{origin}{day:02d}{month:02d}{dest}1?direct'
)
BATCH_SIZE = 5           # tabs per batch
BATCH_TIMEOUT_S = 35     # max seconds to wait per batch
POLL_INTERVAL_MS = 1000  # check captured data every N ms
SETTLE_DELAY_S = 3       # extra wait after all tabs captured data
INTER_BATCH_PAUSE = 8    # seconds between batches
INTER_ROUTE_PAUSE = 30   # seconds between routes

# Persistent Chrome profile dir (shared cookies/state across runs)
CHROME_PROFILE_DIR = str(Path(__file__).resolve().parent.parent.parent / '_chrome_profile')

# 2captcha extension
CAPTCHA_SOLVE_TIMEOUT = 180  # max seconds to wait for extension to solve
CAPTCHA_EXT_DIR = str(Path(__file__).resolve().parent.parent.parent / 'extensions' / '2captcha')


def build_search_url(origin, dest, d):
    """Build aviasales one-way direct search URL for a date."""
    return AVIASALES_SEARCH_URL.format(
        origin=origin, dest=dest, day=d.day, month=d.month,
    )


def _setup_page_blocking(page):
    """Block heavy resources on a page — images, fonts, media, ads, analytics."""
    page.route('**/*.{png,jpg,jpeg,gif,webp,svg,ico,woff,woff2,ttf,eot,mp4,webm}',
               lambda route: route.abort())
    page.route('**/ads**', lambda route: route.abort())
    page.route('**/analytics**', lambda route: route.abort())
    page.route('**/mc.yandex.ru/**', lambda route: route.abort())
    page.route('**/google-analytics.com/**', lambda route: route.abort())
    page.route('**/googletagmanager.com/**', lambda route: route.abort())


# ---------------------------------------------------------------------------
# Captcha detection & auto-solving via 2captcha browser extension
# ---------------------------------------------------------------------------

def _has_captcha(page):
    """Check if any captcha (reCAPTCHA, Turnstile, etc.) is on the page."""
    try:
        captcha_selectors = [
            # Google reCAPTCHA
            'iframe[src*="recaptcha"]',
            'iframe[src*="google.com/recaptcha"]',
            '.g-recaptcha',
            '#recaptcha',
            'iframe[title*="recaptcha"]',
            # Cloudflare Turnstile
            'iframe[src*="challenges.cloudflare.com"]',
            'iframe[src*="turnstile"]',
            '#challenge-running',
            '#challenge-form',
            '#challenge-stage',
            '.cf-turnstile',
            '#turnstile-wrapper',
            # Generic
            '[data-sitekey]',
        ]
        for sel in captcha_selectors:
            if page.locator(sel).count() > 0:
                return True

        # Check page title for challenge keywords
        title = page.title().lower()
        if any(kw in title for kw in ['challenge', 'cloudflare', 'just a moment',
                                       'attention required', 'checking your browser']):
            return True

        return False
    except Exception:
        return False


def _wait_for_captcha_solve(page, timeout=CAPTCHA_SOLVE_TIMEOUT):
    """Wait for 2captcha extension to solve captcha on a page.

    The extension injects a .captcha-solver button with data-state attribute.
    Returns True if captcha was solved.
    """
    # Check if extension solver button exists
    solver = page.query_selector('.captcha-solver')
    if not solver:
        # Extension might need a moment to detect the captcha
        page.wait_for_timeout(3000)
        solver = page.query_selector('.captcha-solver')

    if not solver:
        logger.warning('No captcha-solver button found (extension not loaded?)')
        return False

    state = solver.get_attribute('data-state') or ''
    logger.info('Captcha solver state: %s', state)

    # Click to start solving if ready
    if state == 'ready':
        logger.info('Clicking captcha solver button...')
        try:
            solver.click(force=True)
        except Exception as e:
            logger.warning('Click failed, trying JS click: %s', e)
            try:
                page.evaluate('document.querySelector(".captcha-solver").click()')
            except Exception:
                pass

    # Wait for solved state
    try:
        page.wait_for_selector(
            '.captcha-solver[data-state="solved"]',
            timeout=timeout * 1000,
        )
        logger.info('Captcha solved by extension!')
        # Wait for page to process the solution
        page.wait_for_timeout(3000)
        return True
    except Exception:
        # Check final state
        solver = page.query_selector('.captcha-solver')
        final_state = solver.get_attribute('data-state') if solver else 'none'
        logger.warning('Captcha solve timeout (state: %s)', final_state)
        return False


def _ensure_no_captcha(context, captcha_api_key):
    """Open a test page to check for captcha. Let extension solve if found.

    Must be called before starting route scraping.
    Returns True if ready to scrape, False if captcha couldn't be solved.
    """
    page = context.new_page()
    _setup_page_blocking(page)

    # Track if search results data arrives (means no blocking captcha)
    got_data = [False]

    def on_response(response):
        if 'v3.2/results' in response.url and response.status == 200:
            got_data[0] = True

    page.on('response', on_response)

    try:
        page.goto('https://www.aviasales.ru/search/LED1502CEK1?direct',
                   wait_until='domcontentloaded', timeout=30000)
    except Exception as e:
        logger.warning('Captcha check page failed to load: %s', e)
        try:
            page.close()
        except Exception:
            pass
        return True  # proceed anyway, batch will handle captcha

    # Wait and check if data loads (no blocking captcha)
    page.wait_for_timeout(12000)

    if got_data[0]:
        logger.info('No captcha — data loaded, ready to scrape')
        page.close()
        return True

    # No data after 12 sec — likely blocked by captcha
    if not _has_captcha(page):
        logger.info('No data and no captcha detected — proceeding anyway')
        page.close()
        return True

    logger.info('Captcha blocking page, waiting for extension to solve...')
    solved = _wait_for_captcha_solve(page)
    page.close()

    if solved:
        logger.info('Pre-check captcha solved! Cookies saved.')
        return True

    logger.warning('Could not solve pre-check captcha')
    return False


# ---------------------------------------------------------------------------
# Direct-flights filter activation
# ---------------------------------------------------------------------------

def _ensure_direct_filter_active(page, wait_ms=15000):
    """Make sure the 'Прямые рейсы' filter is CHECKED on the page.

    Reads the real filter state from the DOM (real <input type=checkbox> or
    aria-checked attribute) and only clicks when it is NOT already active.
    This is important: aviasales ships the URL ?direct param, but on some
    tabs/builds the sidebar UI doesn't reflect it — in that case we click
    to activate, and on tabs where it's already active we leave it alone
    (so we never accidentally disable it).

    Returns True if a click was performed (caller should drop pre-click
    capture for this tab because a new filtered chunk is coming).
    Returns False if already active, not found, or state could not be
    determined.
    """
    try:
        page.wait_for_selector('text=/Прямые/i', timeout=wait_ms)
    except Exception:
        logger.debug('Direct filter text not in DOM within %d ms', wait_ms)
        return False

    # Locate the filter via JS, read state, click only if inactive.
    state = page.evaluate(
        """
        () => {
          const walker = document.createTreeWalker(
            document.body, NodeFilter.SHOW_TEXT, null, false);
          let textNode;
          while ((textNode = walker.nextNode())) {
            const t = (textNode.textContent || '').trim();
            if (!/^Прямые( рейсы)?$/i.test(t)) continue;
            // Walk up to find a container with meaningful state
            let el = textNode.parentElement;
            for (let depth = 0; el && depth < 10; depth++, el = el.parentElement) {
              // 1. A real checkbox input inside this ancestor
              const input = el.querySelector && el.querySelector('input[type="checkbox"]');
              if (input) {
                const wasChecked = !!input.checked;
                let how = 'noop';
                if (!wasChecked) {
                  // Prefer the associated <label> — that's what a human
                  // would click, and it fires the native change event
                  // correctly for both real and visually-hidden inputs.
                  if (input.labels && input.labels.length > 0) {
                    input.labels[0].click();
                    how = 'label';
                  } else {
                    // Fall back to clicking the input directly
                    input.click();
                    how = 'input';
                  }
                  // If still not checked (React controlled input that
                  // ignores DOM .click()), set the value natively and
                  // dispatch a change event.
                  if (!input.checked) {
                    const setter = Object.getOwnPropertyDescriptor(
                      window.HTMLInputElement.prototype, 'checked').set;
                    setter.call(input, true);
                    input.dispatchEvent(new Event('change', {bubbles: true}));
                    input.dispatchEvent(new Event('input', {bubbles: true}));
                    how = how + '+setter';
                  }
                }
                return {
                  type: 'input',
                  how: how,
                  wasChecked: wasChecked,
                  nowChecked: !!input.checked,
                  container: el.tagName.toLowerCase(),
                };
              }
              // 2. aria-checked on the element itself
              const aria = el.getAttribute && el.getAttribute('aria-checked');
              if (aria === 'true' || aria === 'false') {
                const wasChecked = aria === 'true';
                if (!wasChecked) el.click();
                return {
                  type: 'aria',
                  wasChecked: wasChecked,
                  nowChecked: el.getAttribute('aria-checked') === 'true',
                  container: el.tagName.toLowerCase(),
                };
              }
            }
            return {type: 'unknown', container: 'nostate'};
          }
          return {type: 'notext'};
        }
        """
    )
    logger.info('Direct filter state: %s', state)
    if not state:
        return False
    # Only report "activated" if the state actually flipped — otherwise we'd
    # mistakenly reset the capture for a tab where the click did nothing.
    if (state.get('type') in ('input', 'aria')
            and not state.get('wasChecked')
            and state.get('nowChecked')):
        page.wait_for_timeout(1500)  # let new filtered chunk arrive
        return True
    return False


# ---------------------------------------------------------------------------
# Results parser
# ---------------------------------------------------------------------------

def parse_results_chunk(data):
    """Extract flights from a search/v3.2/results JSON chunk.

    Returns list of dicts:
        {origin, destination, operating_carrier, operating_number,
         depart_date, depart_time_local, arrive_time_local,
         departure_unix, duration_min, equipment,
         prices: [{price, baggage_count, baggage_weight, fare_name,
                   agent_id, carrier_code, flight_number}]}
    """
    if isinstance(data, list):
        data = data[-1] if data else {}

    flight_legs = data.get('flight_legs', [])
    tickets = data.get('tickets', [])

    leg_index = {i: leg for i, leg in enumerate(flight_legs)}

    results = []

    for ticket in tickets:
        segments = ticket.get('segments', [])
        if not segments:
            continue

        seg = segments[0]
        flight_indices = seg.get('flights', [])
        if len(flight_indices) != 1:
            continue

        leg_idx = flight_indices[0]
        leg = leg_index.get(leg_idx, {})
        if not leg:
            continue

        op = leg.get('operating_carrier_designator', {})
        origin = leg.get('origin', '')
        destination = leg.get('destination', '')
        dep_local = leg.get('local_departure_date_time', '')
        arr_local = leg.get('local_arrival_date_time', '')
        dep_unix = leg.get('departure_unix_timestamp', 0)
        arr_unix = leg.get('arrival_unix_timestamp', 0)
        duration_min = (arr_unix - dep_unix) // 60 if arr_unix and dep_unix else None
        equipment = leg.get('equipment', {}).get('name', '')

        operating_carrier = op.get('carrier', '')
        operating_number = op.get('number', '')

        depart_date = dep_local[:10] if dep_local else ''
        depart_time = dep_local[11:16] if len(dep_local) >= 16 else ''
        arrive_time = arr_local[11:16] if len(arr_local) >= 16 else ''

        prices = []
        for proposal in ticket.get('proposals', []):
            price_val = proposal.get('price', {}).get('value', 0)
            agent_id = proposal.get('agent_id', 0)

            flight_terms = proposal.get('flight_terms', {})
            ft = flight_terms.get(str(leg_idx), {})

            baggage = ft.get('baggage', {})
            baggage_count = baggage.get('count', 0)
            baggage_weight = baggage.get('weight')

            tariff_info = ft.get('additional_tariff_info', {})
            fare_name = tariff_info.get('fare_name', '')

            seats_available = ft.get('seats_available')

            marketing = ft.get('marketing_carrier_designator', {})
            carrier_code = marketing.get('carrier', operating_carrier)
            carrier_number = marketing.get('number', operating_number)

            prices.append({
                'price': int(price_val),
                'baggage_count': baggage_count,
                'baggage_weight': baggage_weight,
                'fare_name': fare_name,
                'seats_available': seats_available,
                'agent_id': agent_id,
                'carrier_code': carrier_code,
                'flight_number': carrier_number,
            })

        prices.sort(key=lambda p: p['price'])

        results.append({
            'origin': origin,
            'destination': destination,
            'operating_carrier': operating_carrier,
            'operating_number': operating_number,
            'depart_date': depart_date,
            'depart_time_local': depart_time,
            'arrive_time_local': arrive_time,
            'departure_unix': dep_unix,
            'arrival_unix': arr_unix,
            'duration_min': duration_min,
            'equipment': equipment,
            'prices': prices,
        })

    return results


# ---------------------------------------------------------------------------
# Route scraper
# ---------------------------------------------------------------------------

def scrape_route(context, origin, dest, dates, on_date_done=None,
                 captcha_api_key=None):
    """Scrape flights for a route across multiple dates using parallel tabs.

    Uses a single browser context — each date opens as a tab.
    Intercepts v3.2/results responses and exits early when all data is captured.

    Args:
        context: Playwright BrowserContext instance
        origin: origin airport code (e.g. 'LED')
        dest: destination airport code (e.g. 'CEK')
        dates: list of date objects to search
        on_date_done: optional callback(date_str, flights_list)
        captcha_api_key: 2captcha API key for auto-solving

    Returns:
        dict: {date_str: [flight_dicts]}
    """
    all_results = {}

    for batch_start in range(0, len(dates), BATCH_SIZE):
        batch_dates = dates[batch_start:batch_start + BATCH_SIZE]
        logger.info('Scraping %s->%s batch %d-%d of %d',
                     origin, dest,
                     batch_start + 1, batch_start + len(batch_dates), len(dates))

        pages = []
        captured = {}         # date_str -> response body with the best ticket set
        captured_tickets = {} # date_str -> ticket count of that body
        has_tickets = set()   # dates where any ticket ever appeared

        # --- Open all tabs ---
        for d in batch_dates:
            date_str = d.isoformat()
            url = build_search_url(origin, dest, d)

            page = context.new_page()
            _setup_page_blocking(page)

            def make_handler(ds):
                def handler(response):
                    if 'results' in response.url and response.status == 200:
                        ct = response.headers.get('content-type', '')
                        if 'json' in ct and 'v3.2/results' in response.url:
                            try:
                                body = response.json()
                                chunk = body[-1] if isinstance(body, list) else body
                                tickets = chunk.get('tickets') or []
                                n = len(tickets)
                                # Keep the chunk with the MOST tickets, not
                                # the most bytes — aviasales sometimes sends
                                # a smaller but more complete chunk later in
                                # the polling sequence, and "largest-bytes"
                                # would silently drop that extra flight.
                                if n > captured_tickets.get(ds, 0):
                                    captured[ds] = body
                                    captured_tickets[ds] = n
                                if tickets:
                                    has_tickets.add(ds)
                                logger.debug('  [%s] chunk tickets=%d (best=%d)',
                                             ds, n, captured_tickets.get(ds, 0))
                            except Exception:
                                pass
                return handler

            page.on('response', make_handler(date_str))

            # Try to open page, retry with fresh page on failure
            opened = False
            for attempt in range(2):
                try:
                    page.goto(url, wait_until='domcontentloaded', timeout=30000)
                    opened = True
                    break
                except Exception as e:
                    if attempt == 0:
                        logger.warning('  %s: goto failed, retrying fresh page...', date_str)
                        try:
                            page.close()
                        except Exception:
                            pass
                        page = context.new_page()
                        _setup_page_blocking(page)
                        page.on('response', make_handler(date_str))
                    else:
                        logger.warning('  %s: goto failed (giving up): %s', date_str, e)
                        try:
                            page.close()
                        except Exception:
                            pass

            if not opened:
                continue
            pages.append((page, date_str))

        # --- Phase 2: make sure 'Прямые рейсы' filter is active on every tab ---
        # All tabs opened in parallel in phase 1 — by the time we get here the
        # oldest tab has had several seconds to render the filters sidebar.
        # _ensure_direct_filter_active() reads the real state and only clicks
        # when the checkbox is NOT already checked, so we can never turn it
        # off by accident.
        for idx, (pg, ds) in enumerate(pages):
            try:
                clicked = _ensure_direct_filter_active(pg)
                if clicked:
                    # Pre-click response was unfiltered — drop it and let the
                    # new filtered chunk win the "most tickets" race.
                    captured.pop(ds, None)
                    captured_tickets.pop(ds, None)
                    has_tickets.discard(ds)
                # Save a one-time debug screenshot of the first tab so the
                # user can visually confirm the filter checkbox state.
                if idx == 0:
                    try:
                        ss = Path(CHROME_PROFILE_DIR).parent / '_debug_filter_state.png'
                        pg.screenshot(path=str(ss), full_page=False)
                        logger.info('Filter state screenshot saved: %s', ss)
                    except Exception:
                        pass
            except Exception as e:
                logger.debug('Filter activation failed for %s: %s', ds, e)

        # --- Wait for results: poll until all tabs have tickets or timeout ---
        if not pages:
            logger.warning('All pages failed to open in this batch, skipping')
            continue

        target = {d.isoformat() for d in batch_dates}
        deadline = time.time() + BATCH_TIMEOUT_S
        poll_page = pages[0][0]  # use first tab to drive the event loop

        captcha_detected = False
        captcha_solved = False
        captcha_checked = False
        batch_time_start = time.time()
        while time.time() < deadline:
            if has_tickets >= target:
                poll_page.wait_for_timeout(SETTLE_DELAY_S * 1000)
                break

            # Captcha detection — only when no data is coming in
            elapsed_batch = time.time() - batch_time_start
            should_check = (
                elapsed_batch > 15 and not has_tickets and not captured
                and not captcha_checked
            )
            if should_check and not captcha_solved:
                captcha_page = None
                captcha_page_idx = -1
                for idx, (pg, ds) in enumerate(pages):
                    try:
                        if _has_captcha(pg):
                            captcha_page = pg
                            captcha_page_idx = idx
                            break
                    except Exception:
                        pass

                captcha_checked = True
                if captcha_page and captcha_api_key:
                    logger.info('CAPTCHA in batch — waiting for extension...')
                    solved = _wait_for_captcha_solve(captcha_page)
                    if solved:
                        logger.info('Captcha solved! Reloading other tabs...')
                        for idx2, (pg, ds) in enumerate(pages):
                            if idx2 == captcha_page_idx:
                                continue
                            try:
                                pg.reload(wait_until='domcontentloaded',
                                          timeout=30000)
                            except Exception:
                                pass
                        deadline = time.time() + BATCH_TIMEOUT_S
                        batch_time_start = time.time()
                        captcha_solved = True
                        continue
                    else:
                        logger.warning('CAPTCHA not solved — aborting batch.')
                        captcha_detected = True
                        break

            poll_page.wait_for_timeout(POLL_INTERVAL_MS)

        captured_count = len(has_tickets)
        elapsed = int(BATCH_TIMEOUT_S - (deadline - time.time()))
        extra = ' (after captcha solve)' if captcha_solved else ''
        logger.info('Batch captured: %d/%d dates (%d sec)%s',
                     captured_count, len(batch_dates), elapsed, extra)

        # Debug: screenshot first tab if nothing captured
        if captured_count == 0 and pages:
            try:
                dbg_page = pages[0][0]
                ss_path = str(Path(CHROME_PROFILE_DIR).parent / '_debug_screenshot.png')
                dbg_page.screenshot(path=ss_path)
                logger.info('Debug screenshot saved: %s', ss_path)
                logger.info('Page URL: %s', dbg_page.url)
                logger.info('Page title: %s', dbg_page.title())
            except Exception as e:
                logger.warning('Could not save debug screenshot: %s', e)

        # --- Close all tabs ---
        for page, _ in pages:
            try:
                page.close()
            except Exception:
                pass

        # --- Parse captured responses ---
        for d in batch_dates:
            date_str = d.isoformat()
            raw = captured.get(date_str)
            if raw:
                flights = parse_results_chunk(raw)
                direct = [f for f in flights
                          if f['origin'] == origin and f['destination'] == dest]
                all_results[date_str] = direct
                logger.info('  %s: %d direct flights', date_str, len(direct))
                if on_date_done:
                    on_date_done(date_str, direct)
            else:
                all_results[date_str] = []
                if not captcha_detected:
                    logger.warning('  %s: no data captured', date_str)

        if captcha_detected:
            logger.warning('Captcha detected — skipping remaining batches for %s->%s',
                           origin, dest)
            break

        if batch_start + BATCH_SIZE < len(dates):
            time.sleep(INTER_BATCH_PAUSE)

    return all_results


def _needs_virtual_display():
    """Check if we need a virtual display (Linux without DISPLAY)."""
    if platform.system() != 'Linux':
        return False
    return not os.environ.get('DISPLAY')


def scrape_all(days_ahead=30, routes=None, headless=False, profile_dir=None,
               proxy=None, captcha_api_key=None):
    """Full scrape: both directions, N days ahead.

    Uses system Chrome with persistent profile to avoid captcha.
    On Linux without display, automatically starts Xvfb virtual display.

    Args:
        days_ahead: number of days to scan from today
        routes: list of (origin, dest) tuples, default LED<->CEK
        headless: run browser without GUI (likely triggers captcha!)
        profile_dir: Chrome profile directory (default: _chrome_profile in project root)
        proxy: proxy dict for Playwright, e.g.
               {"server": "http://host:port", "username": "u", "password": "p"}
               or None for direct connection
        captcha_api_key: 2captcha API key for auto-solving captchas

    Returns:
        dict: {(origin, dest): {date_str: [flights]}}
    """
    if routes is None:
        routes = [('LED', 'CEK'), ('CEK', 'LED')]

    if profile_dir is None:
        profile_dir = CHROME_PROFILE_DIR
        # Separate profile per proxy to avoid cookie conflicts
        if proxy:
            import hashlib
            proxy_hash = hashlib.md5(proxy['server'].encode()).hexdigest()[:8]
            profile_dir = profile_dir + '_' + proxy_hash

    dates = [date.today() + timedelta(days=i) for i in range(days_ahead)]

    all_data = {}

    # On Linux without display (RPi/server) — start virtual display
    virtual_display = None
    if _needs_virtual_display() and not headless:
        try:
            from pyvirtualdisplay import Display
            virtual_display = Display(visible=0, size=(800, 600))
            virtual_display.start()
            logger.info('Started virtual display (Xvfb)')
        except ImportError:
            logger.warning('pyvirtualdisplay not installed, '
                           'install: pip install pyvirtualdisplay')
        except Exception as e:
            logger.warning('Failed to start virtual display: %s', e)

    try:
        with sync_playwright() as p:
            for origin, dest in routes:
                # Fresh persistent context per route (own browser process)
                chrome_args = ['--disable-blink-features=AutomationControlled']

                # Load 2captcha extension if API key provided and ext exists
                if captcha_api_key and os.path.isdir(CAPTCHA_EXT_DIR):
                    chrome_args.extend([
                        f'--disable-extensions-except={CAPTCHA_EXT_DIR}',
                        f'--load-extension={CAPTCHA_EXT_DIR}',
                    ])
                    logger.info('Loading 2captcha extension from %s', CAPTCHA_EXT_DIR)

                launch_kw = dict(
                    user_data_dir=profile_dir,
                    headless=headless,
                    viewport={'width': 1280, 'height': 720},
                    locale='ru-RU',
                    args=chrome_args,
                )

                # Use system Chrome on Windows UNLESS extension is loaded
                # (system Chrome blocks side-loading extensions via --load-extension)
                use_extension = captcha_api_key and os.path.isdir(CAPTCHA_EXT_DIR)
                if platform.system() == 'Windows' and not use_extension:
                    for chrome_path in [
                        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
                    ]:
                        if os.path.exists(chrome_path):
                            launch_kw['executable_path'] = chrome_path
                            break

                if proxy:
                    launch_kw['proxy'] = proxy
                context = p.chromium.launch_persistent_context(**launch_kw)

                # Pre-check: solve captcha before scraping
                if captcha_api_key:
                    if not _ensure_no_captcha(context, captcha_api_key):
                        logger.warning('Captcha unsolvable — skipping %s->%s',
                                       origin, dest)
                        context.close()
                        continue

                logger.info('=== Scraping %s -> %s (%d dates) ===',
                             origin, dest, len(dates))
                route_data = scrape_route(context, origin, dest, dates,
                                          captcha_api_key=captcha_api_key)
                all_data[(origin, dest)] = route_data

                context.close()
                time.sleep(INTER_ROUTE_PAUSE)
    finally:
        if virtual_display:
            virtual_display.stop()
            logger.info('Stopped virtual display')

    # Summary
    for (origin, dest), route_data in all_data.items():
        total_flights = sum(len(flights) for flights in route_data.values())
        dates_with_data = sum(1 for flights in route_data.values() if flights)
        logger.info('Route %s->%s: %d flights across %d dates',
                     origin, dest, total_flights, dates_with_data)

    return all_data


def solve_captcha_interactive(profile_dir=None, timeout_s=120):
    """Open browser with aviasales and wait for captcha to be solved.

    Polls the page every 2 seconds. Once captcha elements disappear
    or search results appear, closes the browser.
    Cookies persist in the profile for subsequent scrape runs.
    """
    if profile_dir is None:
        profile_dir = CHROME_PROFILE_DIR

    logger.info('=== CAPTCHA SOLVE MODE ===')
    logger.info('Browser opening aviasales.ru — solve captcha if shown.')
    logger.info('Waiting up to %d seconds...', timeout_s)

    with sync_playwright() as p:
        launch_kw = dict(
            user_data_dir=profile_dir,
            headless=False,
            viewport={'width': 1280, 'height': 720},
            locale='ru-RU',
        )
        if platform.system() == 'Windows':
            launch_kw['channel'] = 'chrome'
        context = p.chromium.launch_persistent_context(**launch_kw)

        page = context.new_page()
        page.goto('https://www.aviasales.ru/search/LED1402CEK1?direct',
                  wait_until='domcontentloaded')

        # Wait for page to fully load (captcha appears after ~3s)
        logger.info('Waiting for page to load...')
        page.wait_for_timeout(8000)

        deadline = time.time() + timeout_s
        solved = False

        # Check if captcha is present
        has_captcha = page.locator('[class*="captcha"]').count() > 0
        if not has_captcha:
            logger.info('No captcha on page — ready to scrape!')
            solved = True
        else:
            logger.info('CAPTCHA found! Solve it in the browser window...')
            while time.time() < deadline:
                page.wait_for_timeout(3000)

                has_captcha = page.locator('[class*="captcha"]').count() > 0
                has_results = page.locator('[class*="product-list"]').count() > 0

                if not has_captcha or has_results:
                    logger.info('Captcha solved!')
                    solved = True
                    break

                remaining = int(deadline - time.time())
                logger.info('Waiting for captcha solve... %d sec left', remaining)

        if not solved:
            logger.warning('Timeout waiting for captcha solve.')

        # Give extra time for cookies to be set
        page.wait_for_timeout(3000)
        context.close()

    logger.info('Browser closed. Session saved.')


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

    print('Starting scrape (30 days, both directions)...')
    data = scrape_all(days_ahead=30)

    for (origin, dest), route_data in data.items():
        print(f'\n=== {origin} -> {dest} ===')
        for date_str, flights in sorted(route_data.items()):
            if not flights:
                print(f'  {date_str}: no flights')
                continue
            for f in flights:
                cheapest = f['prices'][0] if f['prices'] else {}
                price = cheapest.get('price', '?')
                bag = cheapest.get('baggage_count', '?')
                fare = cheapest.get('fare_name', '')
                carrier = f['operating_carrier']
                number = f['operating_number']
                dep = f['depart_time_local']
                n_tariffs = len(f['prices'])
                print(f'  {date_str} | {carrier} {number:>4} | {dep} | '
                      f'{price:>6}₽ | bag={bag} | {fare} ({n_tariffs} tariffs)')

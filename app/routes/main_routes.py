from datetime import date, datetime, timedelta, timezone
from itertools import product
from flask import Blueprint, render_template, jsonify, request, current_app
from sqlalchemy import func, and_
from app.database import db
from app.models import Flight, PriceHistory, Airline
from app.services.link_builder import build_booking_url

main_bp = Blueprint('main', __name__)


def _utc_iso(dt):
    """Format datetime as ISO string with Z suffix (UTC)."""
    if dt is None:
        return None
    s = dt.isoformat()
    if s.endswith('+00:00'):
        return s[:-6] + 'Z'
    return s + 'Z'

ROUTE_NAMES = {
    'LED': 'Санкт-Петербург',
    'CEK': 'Челябинск',
}

ALLOWED_ROUTES = [('LED', 'CEK'), ('CEK', 'LED')]


@main_bp.route('/')
def index():
    """Main page: route cards with cheapest prices."""
    today = date.today()
    now_utc = datetime.now(timezone.utc)
    now_hhmm = now_utc.strftime('%H:%M')

    routes_data = []
    for origin, dest in ALLOWED_ROUTES:
        candidates = (Flight.query
                      .filter_by(origin=origin, destination=dest)
                      .filter(Flight.depart_date >= today)
                      .filter(Flight.is_available == True)
                      .order_by(Flight.price.asc())
                      .all())
        # Skip today's flights that already departed
        cheapest = None
        for c in candidates:
            if c.depart_date > today or c.depart_time > now_hhmm:
                cheapest = c
                break

        airline_obj = None
        if cheapest:
            airline_obj = db.session.get(Airline, cheapest.airline)

        routes_data.append({
            'origin': origin,
            'destination': dest,
            'origin_name': ROUTE_NAMES.get(origin, origin),
            'dest_name': ROUTE_NAMES.get(dest, dest),
            'cheapest': cheapest,
            'airline_name': (airline_obj.name_ru if airline_obj and airline_obj.name_ru
                             else (airline_obj.name_en if airline_obj else cheapest.airline))
                            if cheapest else None,
        })

    tracker = getattr(current_app, 'tracker', None)
    last_update = tracker.last_update if tracker else None

    return render_template('index.html', routes=routes_data, last_update=last_update)


@main_bp.route('/route/<origin>/<destination>')
def route_calendar(origin, destination):
    """Calendar page for a route."""
    origin = origin.upper()
    destination = destination.upper()
    if (origin, destination) not in ALLOWED_ROUTES:
        return 'Invalid route', 404

    return render_template('calendar.html',
                           origin=origin,
                           destination=destination,
                           origin_name=ROUTE_NAMES.get(origin, origin),
                           dest_name=ROUTE_NAMES.get(destination, destination))


@main_bp.route('/api/calendar/<origin>/<destination>')
def api_calendar(origin, destination):
    """JSON API: calendar data for a month."""
    origin = origin.upper()
    destination = destination.upper()
    if (origin, destination) not in ALLOWED_ROUTES:
        return jsonify({'error': 'Invalid route'}), 404

    month_str = request.args.get('month', '')
    if not month_str:
        month_str = date.today().strftime('%Y-%m')

    try:
        year, month = map(int, month_str.split('-'))
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid month format, use YYYY-MM'}), 400

    # Get all flights for this route and month (including past for history)
    today = date.today()
    now_utc = datetime.now(timezone.utc)
    now_hhmm = now_utc.strftime('%H:%M')

    flights = (Flight.query
               .filter_by(origin=origin, destination=destination)
               .filter(db.extract('year', Flight.depart_date) == year)
               .filter(db.extract('month', Flight.depart_date) == month)
               .order_by(Flight.depart_date, Flight.price)
               .all())

    # Build response
    days = {}
    future_prices = []  # only future dates for color tier calculation

    for f in flights:
        day_key = f.depart_date.isoformat()
        # Past dates + today's already-departed flights → show greyed out
        is_past = (f.depart_date < today or
                   (f.depart_date == today and (f.depart_time or '') <= now_hhmm))

        if day_key not in days:
            days[day_key] = {
                'cheapest_price': None,
                'flight_count': 0,
                'flights': [],
                'all_past': True,
            }

        if not is_past:
            days[day_key]['all_past'] = False

        airline_obj = db.session.get(Airline, f.airline)
        airline_name = f.airline
        if airline_obj:
            airline_name = airline_obj.name_ru or airline_obj.name_en or f.airline

        history = [{
            'old': h.old_price,
            'new': h.new_price,
            'at': _utc_iso(h.changed_at) or '',
        } for h in f.price_history]

        flight_data = {
            'airline': f.airline,
            'airline_name': airline_name,
            'airline_logo': f'http://pics.avs.io/36/36/{f.airline}.png',
            'flight_number': f.flight_number or '',
            'price': f.price,
            'departure_at': f.departure_at or '',
            'duration': f.duration,
            'transfers': 0,
            'booking_url': build_booking_url(f.link),
            'price_history': history,
            'is_available': f.is_available,
            'baggage_count': f.baggage_count,
            'baggage_weight': f.baggage_weight,
            'fare_name': f.fare_name or '',
            'seats_available': f.seats_available,
            'equipment': f.equipment or '',
            'arrive_time_local': f.arrive_time_local or '',
        }

        days[day_key]['flights'].append(flight_data)
        days[day_key]['flight_count'] = len(days[day_key]['flights'])

        if not is_past:
            future_prices.append(f.price)

        # For past dates: cheapest from any flight; for future: only available
        if is_past or f.is_available:
            current_cheapest = days[day_key]['cheapest_price']
            if current_cheapest is None or f.price < current_cheapest:
                days[day_key]['cheapest_price'] = f.price

    price_range = {
        'min': min(future_prices) if future_prices else 0,
        'max': max(future_prices) if future_prices else 0,
    }

    tracker = getattr(current_app, 'tracker', None)
    last_update = tracker.last_update if tracker else None

    return jsonify({
        'days': days,
        'price_range': price_range,
        'last_update': _utc_iso(last_update),
    })


@main_bp.route('/api/last_update')
def api_last_update():
    tracker = getattr(current_app, 'tracker', None)
    last_update = tracker.last_update if tracker else None
    return jsonify({
        'last_update': _utc_iso(last_update),
    })


# ─── "Выгодные билеты" ────────────────────────────────────────────

@main_bp.route('/deals')
def deals_page():
    """Page: round-trip deal finder."""
    return render_template('deals.html')


@main_bp.route('/api/deals')
def api_deals():
    """Find best round-trip combinations within date/duration constraints.

    Query params:
        origin      – departure city (LED or CEK), default LED
        month       – YYYY-MM  (used when no date_from/date_to)
        date_from   – YYYY-MM-DD  (optional, overrides month)
        date_to     – YYYY-MM-DD  (optional, overrides month)
        min_days    – minimum trip length in days (default 5)
        max_days    – maximum trip length in days (default 10)
    """
    origin = request.args.get('origin', 'LED').upper()
    dest = 'CEK' if origin == 'LED' else 'LED'
    if (origin, dest) not in ALLOWED_ROUTES:
        return jsonify({'error': 'Invalid route'}), 400

    min_days = int(request.args.get('min_days', 5))
    max_days = int(request.args.get('max_days', 10))
    if min_days < 1:
        min_days = 1
    if max_days > 30:
        max_days = 30
    if min_days > max_days:
        min_days, max_days = max_days, min_days

    today = date.today()
    now_utc = datetime.now(timezone.utc)
    now_hhmm = now_utc.strftime('%H:%M')

    # Determine outbound date range
    date_from_str = request.args.get('date_from', '')
    date_to_str = request.args.get('date_to', '')
    if date_from_str and date_to_str:
        try:
            d_from = date.fromisoformat(date_from_str)
            d_to = date.fromisoformat(date_to_str)
        except ValueError:
            return jsonify({'error': 'Invalid date format'}), 400
    else:
        month_str = request.args.get('month', '')
        if not month_str:
            month_str = today.strftime('%Y-%m')
        try:
            year, month = map(int, month_str.split('-'))
        except (ValueError, AttributeError):
            return jsonify({'error': 'Invalid month format'}), 400
        d_from = date(year, month, 1)
        # last day of month
        if month == 12:
            d_to = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            d_to = date(year, month + 1, 1) - timedelta(days=1)

    # Don't search in the past
    if d_from < today:
        d_from = today

    if d_to < d_from:
        return jsonify({'deals': [], 'count': 0})

    # The latest possible return date
    return_deadline = d_to + timedelta(days=max_days)

    # Fetch outbound flights (origin → dest)
    outbound_q = (Flight.query
                  .filter_by(origin=origin, destination=dest, is_available=True)
                  .filter(Flight.depart_date >= d_from, Flight.depart_date <= d_to)
                  .order_by(Flight.depart_date, Flight.price)
                  .all())

    # Fetch return flights (dest → origin)
    return_from = d_from + timedelta(days=min_days)
    return_q = (Flight.query
                .filter_by(origin=dest, destination=origin, is_available=True)
                .filter(Flight.depart_date >= return_from, Flight.depart_date <= return_deadline)
                .order_by(Flight.depart_date, Flight.price)
                .all())

    # Index return flights by date for fast lookup
    returns_by_date = {}
    for f in return_q:
        returns_by_date.setdefault(f.depart_date, []).append(f)

    # Build airline name cache
    airline_cache = {}

    def get_airline_name(code):
        if code not in airline_cache:
            obj = db.session.get(Airline, code)
            airline_cache[code] = (obj.name_ru or obj.name_en or code) if obj else code
        return airline_cache[code]

    # Skip today's flights that already departed
    def is_departed(f):
        return f.depart_date == today and (f.depart_time or '') <= now_hhmm

    # Build combinations
    deals = []
    for out_f in outbound_q:
        if is_departed(out_f):
            continue
        for delta in range(min_days, max_days + 1):
            ret_date = out_f.depart_date + timedelta(days=delta)
            for ret_f in returns_by_date.get(ret_date, []):
                if is_departed(ret_f):
                    continue
                deals.append({
                    'total': out_f.price + ret_f.price,
                    'days': delta,
                    'outbound': {
                        'date': out_f.depart_date.isoformat(),
                        'airline': out_f.airline,
                        'airline_name': get_airline_name(out_f.airline),
                        'airline_logo': f'http://pics.avs.io/36/36/{out_f.airline}.png',
                        'flight_number': out_f.flight_number or '',
                        'price': out_f.price,
                        'departure_at': out_f.departure_at or '',
                        'duration': out_f.duration,
                        'booking_url': build_booking_url(out_f.link),
                        'equipment': out_f.equipment or '',
                        'seats_available': out_f.seats_available,
                    },
                    'return': {
                        'date': ret_f.depart_date.isoformat(),
                        'airline': ret_f.airline,
                        'airline_name': get_airline_name(ret_f.airline),
                        'airline_logo': f'http://pics.avs.io/36/36/{ret_f.airline}.png',
                        'flight_number': ret_f.flight_number or '',
                        'price': ret_f.price,
                        'departure_at': ret_f.departure_at or '',
                        'duration': ret_f.duration,
                        'booking_url': build_booking_url(ret_f.link),
                        'equipment': ret_f.equipment or '',
                        'seats_available': ret_f.seats_available,
                    },
                })

    # Sort by total price, limit to top 50
    deals.sort(key=lambda d: d['total'])
    deals = deals[:50]

    tracker = getattr(current_app, 'tracker', None)
    last_update = tracker.last_update if tracker else None

    return jsonify({
        'deals': deals,
        'count': len(deals),
        'last_update': _utc_iso(last_update),
    })


# ─── "Минимум за месяц" (исторический) ───────────────────────────

@main_bp.route('/lowest/<origin>/<destination>')
def lowest_page(origin, destination):
    """Page: historical lowest price per day for a month."""
    origin = origin.upper()
    destination = destination.upper()
    if (origin, destination) not in ALLOWED_ROUTES:
        return 'Invalid route', 404

    return render_template('lowest.html',
                           origin=origin,
                           destination=destination,
                           origin_name=ROUTE_NAMES.get(origin, origin),
                           dest_name=ROUTE_NAMES.get(destination, destination))


@main_bp.route('/api/lowest/<origin>/<destination>')
def api_lowest(origin, destination):
    """JSON API: per-day historical minimum across all observed prices.

    For every flight on the date, walks PriceHistory + current price and
    returns the lowest value ever seen, with the timestamp it was first
    observed and which airline/flight had it.
    """
    origin = origin.upper()
    destination = destination.upper()
    if (origin, destination) not in ALLOWED_ROUTES:
        return jsonify({'error': 'Invalid route'}), 404

    month_str = request.args.get('month', '') or date.today().strftime('%Y-%m')
    try:
        year, month = map(int, month_str.split('-'))
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid month format, use YYYY-MM'}), 400

    flights = (Flight.query
               .filter_by(origin=origin, destination=destination)
               .filter(db.extract('year', Flight.depart_date) == year)
               .filter(db.extract('month', Flight.depart_date) == month)
               .all())

    airline_cache = {}

    def get_airline_name(code):
        if code not in airline_cache:
            obj = db.session.get(Airline, code)
            airline_cache[code] = (obj.name_ru or obj.name_en or code) if obj else code
        return airline_cache[code]

    days = {}
    for f in flights:
        # Reconstruct full price timeline for this flight as (price, observed_at)
        # Original price (before any changes) lived from found_at until first change.
        history_asc = sorted(f.price_history, key=lambda h: h.changed_at)
        observed = []
        if history_asc:
            observed.append((history_asc[0].old_price, f.found_at))
            for h in history_asc:
                observed.append((h.new_price, h.changed_at))
        else:
            observed.append((f.price, f.found_at))

        min_price, min_at = min(observed, key=lambda x: x[0])

        day_key = f.depart_date.isoformat()
        existing = days.get(day_key)
        if existing is None or min_price < existing['min_price']:
            days[day_key] = {
                'min_price': min_price,
                'observed_at': _utc_iso(min_at),
                'airline': f.airline,
                'airline_name': get_airline_name(f.airline),
                'airline_logo': f'http://pics.avs.io/36/36/{f.airline}.png',
                'flight_number': f.flight_number or '',
            }

    prices = [d['min_price'] for d in days.values()]
    price_range = {
        'min': min(prices) if prices else 0,
        'max': max(prices) if prices else 0,
    }

    tracker = getattr(current_app, 'tracker', None)
    last_update = tracker.last_update if tracker else None

    return jsonify({
        'days': days,
        'price_range': price_range,
        'last_update': _utc_iso(last_update),
    })


# ─── "Горячие билеты" ─────────────────────────────────────────────

@main_bp.route('/hot')
def hot_deals_page():
    """Page: hottest deals in the nearest days."""
    return render_template('hot_deals.html')


@main_bp.route('/api/hot-deals')
def api_hot_deals():
    """Cheapest available flights in the next 14 days, both directions."""
    today = date.today()
    now_utc = datetime.now(timezone.utc)
    now_hhmm = now_utc.strftime('%H:%M')
    horizon = today + timedelta(days=14)

    flights = (Flight.query
               .filter(Flight.is_available == True)
               .filter(Flight.depart_date >= today, Flight.depart_date <= horizon)
               .order_by(Flight.price.asc())
               .limit(100)
               .all())

    airline_cache = {}

    def get_airline_name(code):
        if code not in airline_cache:
            obj = db.session.get(Airline, code)
            airline_cache[code] = (obj.name_ru or obj.name_en or code) if obj else code
        return airline_cache[code]

    results = []
    for f in flights:
        # Skip today's departed flights
        if f.depart_date == today and (f.depart_time or '') <= now_hhmm:
            continue
        results.append({
            'origin': f.origin,
            'destination': f.destination,
            'origin_name': ROUTE_NAMES.get(f.origin, f.origin),
            'dest_name': ROUTE_NAMES.get(f.destination, f.destination),
            'date': f.depart_date.isoformat(),
            'airline': f.airline,
            'airline_name': get_airline_name(f.airline),
            'airline_logo': f'http://pics.avs.io/36/36/{f.airline}.png',
            'flight_number': f.flight_number or '',
            'price': f.price,
            'departure_at': f.departure_at or '',
            'duration': f.duration,
            'booking_url': build_booking_url(f.link),
            'equipment': f.equipment or '',
            'seats_available': f.seats_available,
        })
        if len(results) >= 20:
            break

    tracker = getattr(current_app, 'tracker', None)
    last_update = tracker.last_update if tracker else None

    return jsonify({
        'deals': results,
        'count': len(results),
        'last_update': _utc_iso(last_update),
    })

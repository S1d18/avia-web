from datetime import date, datetime, timedelta, timezone
from flask import Blueprint, render_template, jsonify, request, current_app
from sqlalchemy import func, and_
from app.database import db
from app.models import Flight, PriceHistory, Airline
from app.services.link_builder import build_booking_url
from app.services.logo_service import get_logo_url
from app.services.deals_service import (
    ROUTE_NAMES, ALLOWED_ROUTES, utc_iso,
    get_hot_deals, get_deals, get_lowest,
)

main_bp = Blueprint('main', __name__)


def _utc_iso(dt):
    return utc_iso(dt)


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
            'airline_logo': get_logo_url(cheapest.airline) if cheapest else '',
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
            'airline_logo': get_logo_url(f.airline),
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
    """Find best round-trip combinations within date/duration constraints."""
    origin = request.args.get('origin', 'LED').upper()
    dest = 'CEK' if origin == 'LED' else 'LED'
    if (origin, dest) not in ALLOWED_ROUTES:
        return jsonify({'error': 'Invalid route'}), 400

    min_days = max(1, int(request.args.get('min_days', 5)))
    max_days = min(30, int(request.args.get('max_days', 10)))
    if min_days > max_days:
        min_days, max_days = max_days, min_days

    today = date.today()
    date_from_str = request.args.get('date_from', '')
    date_to_str = request.args.get('date_to', '')
    if date_from_str and date_to_str:
        try:
            d_from = date.fromisoformat(date_from_str)
            d_to = date.fromisoformat(date_to_str)
        except ValueError:
            return jsonify({'error': 'Invalid date format'}), 400
    else:
        month_str = request.args.get('month', '') or today.strftime('%Y-%m')
        try:
            year, month = map(int, month_str.split('-'))
        except (ValueError, AttributeError):
            return jsonify({'error': 'Invalid month format'}), 400
        d_from = date(year, month, 1)
        d_to = date(year + (month // 12), month % 12 + 1, 1) - timedelta(days=1)

    d_from = max(d_from, today)
    if d_to < d_from:
        return jsonify({'deals': [], 'count': 0})

    return jsonify(get_deals(origin, dest, d_from, d_to, min_days, max_days))


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
    """JSON API: per-day historical minimum across all observed prices."""
    origin = origin.upper()
    destination = destination.upper()
    if (origin, destination) not in ALLOWED_ROUTES:
        return jsonify({'error': 'Invalid route'}), 404

    month_str = request.args.get('month', '') or date.today().strftime('%Y-%m')
    try:
        year, month = map(int, month_str.split('-'))
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid month format, use YYYY-MM'}), 400

    return jsonify(get_lowest(origin, destination, year, month))


# ─── "Горячие билеты" ─────────────────────────────────────────────

@main_bp.route('/hot')
def hot_deals_page():
    """Page: hottest deals in the nearest days."""
    return render_template('hot_deals.html')


@main_bp.route('/api/hot-deals')
def api_hot_deals():
    """Cheapest available flights in the next 14 days, both directions."""
    return jsonify(get_hot_deals())

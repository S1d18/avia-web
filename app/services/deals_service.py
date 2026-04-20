from datetime import date, datetime, timedelta, timezone
from flask import current_app
from app.database import db
from app.models import Flight, Airline
from app.services.link_builder import build_booking_url
from app.services.logo_service import get_logo_url

ROUTE_NAMES = {
    'LED': 'Санкт-Петербург',
    'CEK': 'Челябинск',
}

ALLOWED_ROUTES = [('LED', 'CEK'), ('CEK', 'LED')]


def utc_iso(dt):
    if dt is None:
        return None
    s = dt.isoformat()
    if s.endswith('+00:00'):
        return s[:-6] + 'Z'
    return s + 'Z'


def _airline_name(code, cache):
    if code not in cache:
        obj = db.session.get(Airline, code)
        cache[code] = (obj.name_ru or obj.name_en or code) if obj else code
    return cache[code]


def _last_update_iso():
    tracker = getattr(current_app, 'tracker', None)
    return utc_iso(tracker.last_update if tracker else None)


def get_hot_deals():
    today = date.today()
    now_hhmm = datetime.now(timezone.utc).strftime('%H:%M')
    horizon = today + timedelta(days=14)

    flights = (Flight.query
               .filter(Flight.is_available == True)
               .filter(Flight.depart_date >= today, Flight.depart_date <= horizon)
               .order_by(Flight.price.asc())
               .limit(100)
               .all())

    cache = {}
    results = []
    for f in flights:
        if f.depart_date == today and (f.depart_time or '') <= now_hhmm:
            continue
        results.append({
            'origin': f.origin,
            'destination': f.destination,
            'origin_name': ROUTE_NAMES.get(f.origin, f.origin),
            'dest_name': ROUTE_NAMES.get(f.destination, f.destination),
            'date': f.depart_date.isoformat(),
            'airline': f.airline,
            'airline_name': _airline_name(f.airline, cache),
            'airline_logo': get_logo_url(f.airline),
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

    return {'deals': results, 'count': len(results), 'last_update': _last_update_iso()}


def get_deals(origin, dest, d_from, d_to, min_days, max_days):
    today = date.today()
    now_hhmm = datetime.now(timezone.utc).strftime('%H:%M')

    outbound_q = (Flight.query
                  .filter_by(origin=origin, destination=dest, is_available=True)
                  .filter(Flight.depart_date >= d_from, Flight.depart_date <= d_to)
                  .order_by(Flight.depart_date, Flight.price)
                  .all())

    return_from = d_from + timedelta(days=min_days)
    return_deadline = d_to + timedelta(days=max_days)
    return_q = (Flight.query
                .filter_by(origin=dest, destination=origin, is_available=True)
                .filter(Flight.depart_date >= return_from, Flight.depart_date <= return_deadline)
                .order_by(Flight.depart_date, Flight.price)
                .all())

    returns_by_date = {}
    for f in return_q:
        returns_by_date.setdefault(f.depart_date, []).append(f)

    cache = {}

    def is_departed(f):
        return f.depart_date == today and (f.depart_time or '') <= now_hhmm

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
                        'airline_name': _airline_name(out_f.airline, cache),
                        'airline_logo': get_logo_url(out_f.airline),
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
                        'airline_name': _airline_name(ret_f.airline, cache),
                        'airline_logo': get_logo_url(ret_f.airline),
                        'flight_number': ret_f.flight_number or '',
                        'price': ret_f.price,
                        'departure_at': ret_f.departure_at or '',
                        'duration': ret_f.duration,
                        'booking_url': build_booking_url(ret_f.link),
                        'equipment': ret_f.equipment or '',
                        'seats_available': ret_f.seats_available,
                    },
                })

    deals.sort(key=lambda d: d['total'])
    return {'deals': deals[:50], 'count': min(len(deals), 50), 'last_update': _last_update_iso()}


def get_lowest(origin, dest, year, month):
    flights = (Flight.query
               .filter_by(origin=origin, destination=dest)
               .filter(db.extract('year', Flight.depart_date) == year)
               .filter(db.extract('month', Flight.depart_date) == month)
               .all())

    cache = {}
    days = {}
    for f in flights:
        history_asc = sorted(f.price_history, key=lambda h: h.changed_at)
        if history_asc:
            observed = [(history_asc[0].old_price, f.found_at)]
            for h in history_asc:
                observed.append((h.new_price, h.changed_at))
        else:
            observed = [(f.price, f.found_at)]

        min_price, min_at = min(observed, key=lambda x: x[0])
        day_key = f.depart_date.isoformat()
        existing = days.get(day_key)
        if existing is None or min_price < existing['min_price']:
            days[day_key] = {
                'min_price': min_price,
                'observed_at': utc_iso(min_at),
                'airline': f.airline,
                'airline_name': _airline_name(f.airline, cache),
                'airline_logo': get_logo_url(f.airline),
                'flight_number': f.flight_number or '',
            }

    prices = [d['min_price'] for d in days.values()]
    price_range = {'min': min(prices) if prices else 0, 'max': max(prices) if prices else 0}
    return {'days': days, 'price_range': price_range, 'last_update': _last_update_iso()}

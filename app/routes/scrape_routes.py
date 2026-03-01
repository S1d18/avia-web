"""API endpoint for receiving scraped flight data from remote PCs.

PCs run parse_playwright.py → scrape_and_send.py → POST here.
RPi validates API key and upserts flights into the database.
"""
import logging
from datetime import datetime, timezone, date

from flask import Blueprint, jsonify, request, current_app
from app.database import db
from app.models import Flight, PriceHistory

logger = logging.getLogger(__name__)

scrape_bp = Blueprint('scrape', __name__)

# Minimum price difference to record in history (same as price_tracker.py)
MIN_PRICE_DIFF = 20


def _check_api_key():
    """Validate X-API-Key header against config."""
    key = request.headers.get('X-API-Key', '')
    expected = current_app.config.get('SCRAPE_API_KEY', '')
    if not expected:
        return False, 'SCRAPE_API_KEY not configured on server'
    if not key or key != expected:
        return False, 'Invalid API key'
    return True, ''


@scrape_bp.route('/api/scrape/import', methods=['POST'])
def scrape_import():
    """Import scraped flight data from a remote PC.

    Expected JSON body:
    {
        "flights": [
            {
                "origin": "LED",
                "destination": "CEK",
                "airline": "DP",
                "flight_number": "406",
                "depart_date": "2026-02-15",
                "depart_time": "09:30",       # UTC HH:MM
                "departure_at": "2026-02-15T12:30:00+03:00",
                "departure_unix": 1771025700,
                "duration": 165,
                "price": 5000,
                "prices": [...]               # all tariffs (stored for reference)
            },
            ...
        ]
    }

    Returns:
        {"created": N, "updated": N, "price_changes": N, "skipped": N, "errors": N}
    """
    ok, err = _check_api_key()
    if not ok:
        return jsonify({'error': err}), 401

    data = request.get_json(silent=True)
    if not data or 'flights' not in data:
        return jsonify({'error': 'Missing "flights" in request body'}), 400

    flights_data = data['flights']
    if not isinstance(flights_data, list):
        return jsonify({'error': '"flights" must be an array'}), 400

    now = datetime.now(timezone.utc)
    stats = {'created': 0, 'updated': 0, 'price_changes': 0, 'skipped': 0, 'errors': 0}

    for item in flights_data:
        try:
            _upsert_scraped_flight(item, now, stats)
        except Exception:
            db.session.rollback()
            logger.exception('Error importing flight: %s', item)
            stats['errors'] += 1

    # Mark flights as unavailable if Playwright scanned the date but didn't find them
    seen_keys = set()
    scanned_route_dates = set()
    for item in flights_data:
        o = item.get('origin', '').strip().upper()
        d = item.get('destination', '').strip().upper()
        dd = item.get('depart_date', '')
        al = item.get('airline', '').strip().upper()
        dt = item.get('depart_time', '')
        if all([o, d, dd, al, dt]):
            seen_keys.add((o, d, dd, al, dt))
        if o and d and dd:
            scanned_route_dates.add((o, d, dd))

    marked_unavailable = 0
    for (o, d, dd) in scanned_route_dates:
        try:
            depart_dt = date.fromisoformat(dd)
        except ValueError:
            continue
        available_flights = Flight.query.filter_by(
            origin=o, destination=d,
            depart_date=depart_dt, is_available=True,
        ).all()
        for f in available_flights:
            key = (f.origin, f.destination, f.depart_date.isoformat(),
                   f.airline, f.depart_time)
            if key not in seen_keys:
                f.is_available = False
                marked_unavailable += 1

    stats['marked_unavailable'] = marked_unavailable

    try:
        db.session.commit()
        logger.info('Scrape import: %s', stats)
    except Exception:
        db.session.rollback()
        logger.exception('Commit failed for scrape import')
        return jsonify({'error': 'Database commit failed', 'stats': stats}), 500

    # Update tracker's last_update timestamp
    tracker = getattr(current_app, 'tracker', None)
    if tracker:
        tracker.last_update = now

    return jsonify(stats), 200


def _upsert_scraped_flight(item, now, stats):
    """Insert or update a single flight from scraped data."""
    origin = item.get('origin', '').strip().upper()
    destination = item.get('destination', '').strip().upper()
    airline = item.get('airline', '').strip().upper()
    flight_number = str(item.get('flight_number', '')).strip()
    depart_date_str = item.get('depart_date', '')
    depart_time = item.get('depart_time', '')  # UTC HH:MM
    departure_at = item.get('departure_at', '')
    duration = item.get('duration')
    price = item.get('price')
    link = item.get('link', '')
    baggage_count = item.get('baggage_count')
    baggage_weight = item.get('baggage_weight')
    fare_name = item.get('fare_name', '')
    seats_available = item.get('seats_available')
    equipment = item.get('equipment', '')
    arrive_time_local = item.get('arrive_time_local', '')

    # Validate required fields
    if not all([origin, destination, airline, depart_date_str, depart_time]):
        stats['skipped'] += 1
        return

    try:
        depart_date = date.fromisoformat(depart_date_str)
    except (ValueError, TypeError):
        stats['skipped'] += 1
        return

    if not price or int(price) <= 0:
        stats['skipped'] += 1
        return

    price = int(price)

    # Look up existing flight by unique key
    existing = Flight.query.filter_by(
        origin=origin,
        destination=destination,
        depart_date=depart_date,
        airline=airline,
        depart_time=depart_time,
    ).first()

    if existing:
        # Update existing flight
        diff = abs(existing.price - price)
        if diff >= MIN_PRICE_DIFF:
            history = PriceHistory(
                flight_id=existing.id,
                old_price=existing.price,
                new_price=price,
            )
            db.session.add(history)
            stats['price_changes'] += 1
            logger.info('Price changed (scrape): %s %s %s->%s %s %s: %d -> %d',
                        airline, flight_number, origin, destination,
                        depart_date, depart_time, existing.price, price)

        if diff > 0:
            existing.price = price
        existing.flight_number = flight_number or existing.flight_number
        if departure_at:
            existing.departure_at = departure_at
        if duration is not None:
            existing.duration = duration
        if link and not existing.link:
            # Only set link if empty — Data API provides affiliate links
            existing.link = link
        existing.baggage_count = baggage_count
        existing.baggage_weight = baggage_weight
        existing.fare_name = fare_name or existing.fare_name
        existing.seats_available = seats_available
        existing.equipment = equipment or existing.equipment
        existing.arrive_time_local = arrive_time_local or existing.arrive_time_local
        existing.updated_at = now
        existing.is_available = True
        stats['updated'] += 1
    else:
        # Create new flight
        flight = Flight(
            origin=origin,
            destination=destination,
            depart_date=depart_date,
            airline=airline,
            depart_time=depart_time,
            flight_number=flight_number,
            price=price,
            departure_at=departure_at,
            duration=duration,
            link=link,
            baggage_count=baggage_count,
            baggage_weight=baggage_weight,
            fare_name=fare_name,
            seats_available=seats_available,
            equipment=equipment,
            arrive_time_local=arrive_time_local,
            found_at=now,
            updated_at=now,
        )
        db.session.add(flight)
        stats['created'] += 1

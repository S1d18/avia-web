import logging
import re
import time
from datetime import datetime, timezone, date
from dateutil.parser import isoparse
from app.database import db
from app.models import Flight, PriceHistory, Airline
from app.services.api_client import TravelpayoutsClient

logger = logging.getLogger(__name__)

ROUTES = [
    ('LED', 'CEK'),
    ('CEK', 'LED'),
]

# Minimum price difference to record in history (filters API rounding noise)
MIN_PRICE_DIFF = 20

# Regex to extract airline code and timestamps from link's t= parameter
# Format: t=DP17710257001771044000000185LEDCEK_hash_price
# Groups: airline(2), dep_timestamp(10), arr_timestamp(10), middle(6), route(6)
LINK_PATTERN = re.compile(r't=([A-Z0-9]{2})(\d{10})(\d{10})(\d+)([A-Z]{6})')


def parse_link(link):
    """Extract airline code and departure datetime (UTC) from API link field."""
    if not link:
        return None, None
    m = LINK_PATTERN.search(link)
    if not m:
        m2 = re.search(r't=([A-Z0-9]{2})', link)
        return (m2.group(1) if m2 else None), None

    airline = m.group(1)       # e.g. "DP"
    dep_ts = int(m.group(2))   # 10-digit unix timestamp
    dep_dt = datetime.fromtimestamp(dep_ts, tz=timezone.utc)
    return airline, dep_dt


class PriceTracker:
    def __init__(self, app):
        self.app = app
        self.client = TravelpayoutsClient()
        self.last_update = None
        self.last_discovery = None

    # ------------------------------------------------------------------
    # Level 1: Discovery poll (hourly) — full scan to find ALL flights
    # ------------------------------------------------------------------

    def discovery_poll(self):
        """Full discovery scan: SBPR with fine step + PFD enrichment."""
        logger.info('Starting discovery poll...')
        with self.app.app_context():
            for i, (origin, dest) in enumerate(ROUTES):
                if i > 0:
                    time.sleep(0.3)
                self._discovery_route(origin, dest)
            self.last_discovery = datetime.now(timezone.utc)
            self.last_update = self.last_discovery
        logger.info('Discovery poll complete.')

    def _discovery_route(self, origin, destination):
        """Discovery for one route: PFD first (enrichment), then full SBPR sweep."""
        now = datetime.now(timezone.utc)

        # Step 1: PFD — primary source with correct timezone
        pfd_tickets, enrichment, local_to_utc, time_to_utc, enrichment_by_time = \
            self._fetch_prices_for_dates(origin, destination)
        logger.info('Discovery PFD: %d direct tickets for %s->%s',
                     len(pfd_tickets), origin, destination)

        # Step 2: Full SBPR sweep (fine-grained ranges)
        sbpr_tickets = self.client.search_all_flights(origin, destination)
        logger.info('Discovery SBPR: %d unique tickets for %s->%s',
                     len(sbpr_tickets), origin, destination)

        # Step 3: Process all tickets
        seen_keys = set()
        seen_times = set()

        pfd_tickets.sort(key=lambda t: t.get('price', 999999))
        for ticket in pfd_tickets:
            try:
                self._upsert_pfd_flight(ticket, origin, destination, now,
                                        seen_keys, seen_times)
            except Exception:
                db.session.rollback()
                logger.exception('Error processing PFD ticket: %s', ticket)

        sbpr_tickets.sort(key=lambda t: t.get('price', 999999))
        for ticket in sbpr_tickets:
            if ticket.get('transfers', 0) > 0:
                continue
            try:
                self._upsert_flight(ticket, origin, destination, now, enrichment,
                                    local_to_utc, time_to_utc, enrichment_by_time,
                                    seen_keys, seen_times)
            except Exception:
                db.session.rollback()
                logger.exception('Error processing SBPR ticket: %s', ticket)

        self._cleanup_stale_duplicates(origin, destination, now)
        self._restore_sibling_flights(origin, destination, seen_keys, now)

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception('Commit failed for discovery %s->%s', origin, destination)

    # ------------------------------------------------------------------
    # Level 2: Price update poll (every 3 min) — update known flights
    # ------------------------------------------------------------------

    def price_update_poll(self):
        """Quick price update: smart SBPR ranges around known prices."""
        logger.info('Starting price update poll...')
        with self.app.app_context():
            for i, (origin, dest) in enumerate(ROUTES):
                if i > 0:
                    time.sleep(0.3)
                self._price_update_route(origin, dest)
            self.last_update = datetime.now(timezone.utc)
        logger.info('Price update poll complete.')

    def _price_update_route(self, origin, destination):
        """Price update for one route: query DB for known prices, build smart ranges."""
        now = datetime.now(timezone.utc)
        today = date.today()

        # Get all unique prices of future flights for this route
        known_prices = [
            row[0] for row in
            db.session.query(Flight.price)
            .filter_by(origin=origin, destination=destination, is_available=True)
            .filter(Flight.depart_date >= today)
            .distinct()
            .all()
        ]

        if not known_prices:
            logger.info('No known prices for %s->%s, skipping update', origin, destination)
            return

        logger.info('Price update %s->%s: %d unique known prices',
                     origin, destination, len(known_prices))

        # Also fetch PFD for enrichment (needed for timezone correction)
        pfd_tickets, enrichment, local_to_utc, time_to_utc, enrichment_by_time = \
            self._fetch_prices_for_dates(origin, destination)

        # SBPR with smart ranges
        sbpr_tickets = self.client.search_by_update_ranges(origin, destination, known_prices)
        logger.info('Update SBPR: %d tickets for %s->%s',
                     len(sbpr_tickets), origin, destination)

        seen_keys = set()
        seen_times = set()

        # Process PFD first (authoritative timezone)
        pfd_tickets.sort(key=lambda t: t.get('price', 999999))
        for ticket in pfd_tickets:
            try:
                self._upsert_pfd_flight(ticket, origin, destination, now,
                                        seen_keys, seen_times)
            except Exception:
                db.session.rollback()
                logger.exception('Error processing PFD ticket: %s', ticket)

        # Process SBPR tickets
        sbpr_tickets.sort(key=lambda t: t.get('price', 999999))
        for ticket in sbpr_tickets:
            if ticket.get('transfers', 0) > 0:
                continue
            try:
                self._upsert_flight(ticket, origin, destination, now, enrichment,
                                    local_to_utc, time_to_utc, enrichment_by_time,
                                    seen_keys, seen_times)
            except Exception:
                db.session.rollback()
                logger.exception('Error processing SBPR ticket: %s', ticket)

        # No cleanup/restore for price_update — discovery handles that
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception('Commit failed for price update %s->%s', origin, destination)

    # ------------------------------------------------------------------
    # Shared helpers (PFD fetching, upsert logic, cleanup)
    # ------------------------------------------------------------------

    def _fetch_prices_for_dates(self, origin, destination):
        """Fetch prices_for_dates for 3 months. Returns:
        - all_tickets: list of direct flight dicts (primary data source)
        - enrichment: dict keyed by (date, airline, utc_HH:MM) for SBPR enrichment
        - local_to_utc: dict keyed by (date, airline, local_HH:MM) -> utc_HH:MM
          Used to fix SBPR link timestamps (which store local time as UTC)"""
        enrichment = {}
        local_to_utc = {}
        # Fallback mappings without airline — for codeshare resolution
        time_to_utc = {}        # (date, local_HH:MM) -> utc_HH:MM
        enrichment_by_time = {} # (date, utc_HH:MM) -> {flight_number, departure_at}
        all_tickets = []
        today = date.today()

        for m_offset in range(3):
            month = today.month + m_offset
            year = today.year
            if month > 12:
                month -= 12
                year += 1
            month_str = f'{year}-{month:02d}'

            time.sleep(0.2)
            pfd_tickets = self.client.prices_for_dates(origin, destination, month_str)

            for t in pfd_tickets:
                if t.get('transfers', 0) > 0:
                    continue
                airline = t.get('airline', '')
                dep_at = t.get('departure_at', '')
                flight_number = t.get('flight_number', '')
                if not airline or not dep_at:
                    continue

                dep_date = dep_at[:10]
                try:
                    dt = isoparse(dep_at)
                    local_hhmm = dt.strftime('%H:%M')  # Local time as shown in link
                    dt_utc = dt.astimezone(timezone.utc)
                    utc_hhmm = dt_utc.strftime('%H:%M')
                except (ValueError, TypeError):
                    utc_hhmm = ''
                    local_hhmm = ''

                if utc_hhmm:
                    enrichment[(dep_date, airline, utc_hhmm)] = {
                        'flight_number': flight_number,
                        'departure_at': dep_at,
                    }
                    # Fallback without airline (for codeshare resolution)
                    enrichment_by_time.setdefault((dep_date, utc_hhmm), {
                        'flight_number': flight_number,
                        'departure_at': dep_at,
                    })

                if local_hhmm and utc_hhmm:
                    local_to_utc[(dep_date, airline, local_hhmm)] = utc_hhmm
                    # Fallback without airline
                    time_to_utc.setdefault((dep_date, local_hhmm), utc_hhmm)

                # Collect as primary ticket data
                all_tickets.append(t)

        logger.info('Enrichment map: %d entries, local_to_utc: %d entries, '
                     'time_to_utc: %d entries for %s->%s',
                     len(enrichment), len(local_to_utc), len(time_to_utc),
                     origin, destination)
        return all_tickets, enrichment, local_to_utc, time_to_utc, enrichment_by_time

    def _upsert_flight(self, ticket, origin, destination, now, enrichment,
                       local_to_utc, time_to_utc, enrichment_by_time,
                       seen_keys, seen_times):
        """Insert or update a flight from SBPR data.
        Link timestamps are local time stored as UTC — use local_to_utc to fix.
        Codeshares (same physical flight under different airline codes) are
        deduplicated via seen_times set (date, depart_time without airline)."""
        dep_date_str = ticket.get('departure_at', '')
        if not dep_date_str:
            return

        try:
            depart_date = date.fromisoformat(dep_date_str[:10])
        except (ValueError, TypeError):
            return

        price = int(ticket.get('price', 0))
        if price <= 0:
            return

        link = ticket.get('link', '')
        duration = ticket.get('duration')

        # Extract airline from link (and link-parsed time which is LOCAL, not UTC)
        airline, dep_dt = parse_link(link)
        if not airline:
            return

        # Link timestamps are local time stored as UTC — fix via PFD lookup
        if dep_dt:
            link_hhmm = dep_dt.strftime('%H:%M')  # This is actually LOCAL time
            local_key = (dep_date_str[:10], airline, link_hhmm)
            if local_key in local_to_utc:
                # Found matching PFD record — use correct UTC time
                depart_time = local_to_utc[local_key]
            else:
                # Fallback: try without airline (codeshare — different airline code,
                # same physical flight with same local departure time)
                time_key = (dep_date_str[:10], link_hhmm)
                if time_key in time_to_utc:
                    depart_time = time_to_utc[time_key]
                else:
                    depart_time = link_hhmm
        else:
            return

        departure_at = dep_dt.isoformat()

        # Codeshare dedup: if PFD already recorded a flight at this (date, time),
        # skip — it's the same physical flight under a different marketing carrier
        time_dedup_key = (depart_date.isoformat(), depart_time)
        if time_dedup_key in seen_times:
            logger.debug('Skipping codeshare duplicate: %s %s %s %s->%s',
                         airline, depart_date, depart_time, origin, destination)
            return

        # Skip if we already processed a (cheaper) ticket for this key in this cycle
        flight_key = (depart_date.isoformat(), airline, depart_time)
        if flight_key in seen_keys:
            return
        seen_keys.add(flight_key)
        seen_times.add(time_dedup_key)

        # Try to get flight_number from enrichment (match by date+airline+utc_time)
        flight_number = ''
        enrich_key = (dep_date_str[:10], airline, depart_time)
        if enrich_key in enrichment:
            enrich = enrichment[enrich_key]
            flight_number = enrich.get('flight_number', '')
            if enrich.get('departure_at'):
                departure_at = enrich['departure_at']
        else:
            # Fallback: try enrichment without airline (codeshare)
            enrich_time_key = (dep_date_str[:10], depart_time)
            if enrich_time_key in enrichment_by_time:
                enrich = enrichment_by_time[enrich_time_key]
                flight_number = enrich.get('flight_number', '')
                if enrich.get('departure_at'):
                    departure_at = enrich['departure_at']

        existing = Flight.query.filter_by(
            origin=origin,
            destination=destination,
            depart_date=depart_date,
            airline=airline,
            depart_time=depart_time,
        ).first()

        if existing:
            diff = abs(existing.price - price)
            if diff >= MIN_PRICE_DIFF:
                history = PriceHistory(
                    flight_id=existing.id,
                    old_price=existing.price,
                    new_price=price,
                )
                db.session.add(history)
                logger.info('Price changed: %s %s %s->%s %s %s: %d -> %d',
                            airline, flight_number, origin, destination,
                            depart_date, depart_time, existing.price, price)
            if diff > 0:
                existing.price = price
            existing.flight_number = flight_number or existing.flight_number
            existing.departure_at = departure_at
            existing.duration = duration
            existing.link = link
            existing.updated_at = now
        else:
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
                found_at=now,
                updated_at=now,
            )
            db.session.add(flight)

    def _upsert_pfd_flight(self, ticket, origin, destination, now,
                           seen_keys, seen_times):
        """Insert or update a flight from prices_for_dates data.
        Reads airline/depart_time directly from ticket (no link parsing needed)."""
        dep_at = ticket.get('departure_at', '')
        if not dep_at:
            return

        try:
            depart_date = date.fromisoformat(dep_at[:10])
        except (ValueError, TypeError):
            return

        price = int(ticket.get('price', 0))
        if price <= 0:
            return

        airline = ticket.get('airline', '')
        if not airline:
            return

        flight_number = ticket.get('flight_number', '')
        duration = ticket.get('duration')
        link = ticket.get('link', '')

        # Extract HH:MM UTC from departure_at
        try:
            dt = isoparse(dep_at)
            dt_utc = dt.astimezone(timezone.utc)
            depart_time = dt_utc.strftime('%H:%M')
            departure_at = dep_at
        except (ValueError, TypeError):
            return

        # Skip if already processed from SBPR (which had the cheapest price)
        flight_key = (depart_date.isoformat(), airline, depart_time)
        if flight_key in seen_keys:
            return
        seen_keys.add(flight_key)

        # Track (date, time) for codeshare dedup — PFD flights are authoritative
        time_dedup_key = (depart_date.isoformat(), depart_time)
        seen_times.add(time_dedup_key)

        existing = Flight.query.filter_by(
            origin=origin,
            destination=destination,
            depart_date=depart_date,
            airline=airline,
            depart_time=depart_time,
        ).first()

        if existing:
            diff = abs(existing.price - price)
            if diff >= MIN_PRICE_DIFF:
                history = PriceHistory(
                    flight_id=existing.id,
                    old_price=existing.price,
                    new_price=price,
                )
                db.session.add(history)
                logger.info('Price changed (PFD): %s %s %s->%s %s %s: %d -> %d',
                            airline, flight_number, origin, destination,
                            depart_date, depart_time, existing.price, price)
            if diff > 0:
                existing.price = price
            existing.flight_number = flight_number or existing.flight_number
            existing.departure_at = departure_at
            existing.duration = duration
            existing.link = link
            existing.updated_at = now
        else:
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
                found_at=now,
                updated_at=now,
            )
            db.session.add(flight)

    def _cleanup_stale_duplicates(self, origin, destination, now):
        """Remove flights with wrong depart_time from before the timezone fix.
        A flight is stale if: same (date, airline) exists with a different depart_time
        that WAS updated this cycle, while this one was NOT."""
        from sqlalchemy import func
        subq = (
            db.session.query(
                Flight.depart_date,
                Flight.airline,
                func.count(Flight.id).label('cnt')
            )
            .filter_by(origin=origin, destination=destination)
            .group_by(Flight.depart_date, Flight.airline)
            .having(func.count(Flight.id) > 1)
            .subquery()
        )

        # Get all flights that have duplicates
        dupes = (
            Flight.query
            .filter_by(origin=origin, destination=destination)
            .join(subq, (Flight.depart_date == subq.c.depart_date) &
                        (Flight.airline == subq.c.airline))
            .all()
        )

        # Group by (date, airline) and remove stale ones (not updated this cycle)
        from collections import defaultdict
        groups = defaultdict(list)
        for f in dupes:
            groups[(f.depart_date, f.airline)].append(f)

        deleted = 0
        now_naive = now.replace(tzinfo=None)  # DB stores naive datetimes
        for key, flights in groups.items():
            fresh = [f for f in flights if f.updated_at and f.updated_at >= now_naive]
            stale = [f for f in flights if not f.updated_at or f.updated_at < now_naive]
            if fresh and stale:
                for f in stale:
                    # Move price history to the fresh record
                    fresh_flight = fresh[0]
                    PriceHistory.query.filter_by(flight_id=f.id).update(
                        {'flight_id': fresh_flight.id})
                    db.session.delete(f)
                    deleted += 1
                    logger.info('Deleted stale duplicate: %s %s %s %s->%s (kept %s)',
                                f.airline, f.depart_date, f.depart_time,
                                origin, destination, fresh_flight.depart_time)

        if deleted:
            logger.info('Cleaned up %d stale duplicates for %s->%s', deleted, origin, destination)

    def _restore_sibling_flights(self, origin, destination, seen_keys, now):
        """Restore availability for flights we couldn't see this cycle.
        API returns max 1 flight per airline per date — so a flight not being
        returned doesn't mean it's sold out, just that a cheaper sibling exists.
        Only mark flights as reappeared when directly seen in seen_keys."""
        today = date.today()

        future_flights = (
            Flight.query
            .filter_by(origin=origin, destination=destination)
            .filter(Flight.depart_date >= today)
            .all()
        )

        # Build set of (date, airline) pairs that were seen this cycle
        seen_airline_dates = set()
        for key in seen_keys:
            # key = (date_iso, airline, time)
            seen_airline_dates.add((key[0], key[1]))

        changed = 0
        for f in future_flights:
            flight_key = (f.depart_date.isoformat(), f.airline, f.depart_time)
            airline_date = (f.depart_date.isoformat(), f.airline)

            if flight_key in seen_keys:
                # Directly seen — always mark available
                if not f.is_available:
                    f.is_available = True
                    changed += 1
                    logger.info('Flight reappeared: %s %s %s->%s %s %s',
                                f.airline, f.flight_number, origin, destination,
                                f.depart_date, f.depart_time)
            elif airline_date in seen_airline_dates:
                # Not directly seen, but another flight by same airline on same date
                # was seen — this flight probably still exists (API limit: 1 per airline)
                if not f.is_available:
                    f.is_available = True
                    changed += 1
                    logger.info('Flight restored (sibling seen): %s %s %s->%s %s %s',
                                f.airline, f.flight_number, origin, destination,
                                f.depart_date, f.depart_time)
            # else: no flight by this airline on this date was seen at all.
            # Keep current is_available state — don't mark unavailable based on
            # one poll cycle, API cache may be incomplete (PFD returns partial data).

        if changed:
            logger.info('Availability restored: %d flights for %s->%s', changed, origin, destination)

    # ------------------------------------------------------------------
    # Affiliate link poll (daily) — PFD only, updates link field
    # ------------------------------------------------------------------

    def link_poll(self):
        """Daily affiliate link update: fetch PFD and update link field for known flights."""
        logger.info('Starting link poll (PFD for affiliate links)...')
        with self.app.app_context():
            for origin, dest in ROUTES:
                self._update_links(origin, dest)
            self.last_update = datetime.now(timezone.utc)
        logger.info('Link poll complete.')

    def _update_links(self, origin, destination):
        """Fetch PFD for 3 months and update link field for matching flights."""
        today = date.today()
        updated = 0

        for m_offset in range(3):
            month = today.month + m_offset
            year = today.year
            if month > 12:
                month -= 12
                year += 1
            month_str = f'{year}-{month:02d}'

            time.sleep(0.2)
            pfd_tickets = self.client.prices_for_dates(origin, destination, month_str)

            for t in pfd_tickets:
                if t.get('transfers', 0) > 0:
                    continue
                airline_code = t.get('airline', '')
                dep_at = t.get('departure_at', '')
                link = t.get('link', '')
                if not airline_code or not dep_at or not link:
                    continue

                try:
                    dt = isoparse(dep_at)
                    dt_utc = dt.astimezone(timezone.utc)
                    depart_time = dt_utc.strftime('%H:%M')
                    depart_date = dt.date()
                except (ValueError, TypeError):
                    continue

                flight = Flight.query.filter_by(
                    origin=origin,
                    destination=destination,
                    depart_date=depart_date,
                    airline=airline_code,
                    depart_time=depart_time,
                ).first()

                if flight:
                    flight.link = link
                    updated += 1

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception('Link update commit failed for %s->%s', origin, destination)

        logger.info('Links updated for %s->%s: %d flights', origin, destination, updated)

    def update_airlines(self):
        """Refresh airline directory cache."""
        logger.info('Updating airlines directory...')
        with self.app.app_context():
            airlines_data = self.client.fetch_airlines()
            count = 0
            for item in airlines_data:
                code = item.get('code') or item.get('iata')
                if not code:
                    continue
                existing = db.session.get(Airline, code)
                if existing:
                    existing.name_ru = item.get('name_translations', {}).get('ru') or item.get('name')
                    existing.name_en = item.get('name') or item.get('name_translations', {}).get('en')
                    existing.is_lowcost = item.get('is_lowcost', False)
                else:
                    airline = Airline(
                        iata_code=code,
                        name_ru=item.get('name_translations', {}).get('ru') or item.get('name'),
                        name_en=item.get('name') or item.get('name_translations', {}).get('en'),
                        is_lowcost=item.get('is_lowcost', False),
                    )
                    db.session.add(airline)
                count += 1

            db.session.commit()
            logger.info('Airlines updated: %d records', count)

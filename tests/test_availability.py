"""Tests for flight availability tracking.

Requirements:
1. Flight model has is_available field (default True)
2. Tracker marks future flights not in API response as is_available=False
3. Tracker marks flights back as available when they reappear
4. API calendar includes is_available in flight data
5. Index page cheapest price only considers available future flights
"""
import pytest
from datetime import date, datetime, timezone, timedelta
from app.models import Flight, PriceHistory
from app.database import db as _db


class TestFlightModelAvailability:
    """Flight model should have is_available field."""

    def test_new_flight_is_available_by_default(self, db):
        """New flights should default to is_available=True."""
        f = Flight(
            origin='LED', destination='CEK',
            depart_date=date.today() + timedelta(days=1),
            airline='DP', depart_time='10:00',
            flight_number='DP 123', price=5000,
            found_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.session.add(f)
        db.session.commit()

        loaded = db.session.get(Flight, f.id)
        assert loaded.is_available is True

    def test_flight_can_be_marked_unavailable(self, db):
        """Flights should be markable as unavailable."""
        f = Flight(
            origin='LED', destination='CEK',
            depart_date=date.today() + timedelta(days=1),
            airline='DP', depart_time='10:00',
            flight_number='DP 123', price=5000,
            found_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.session.add(f)
        db.session.commit()

        f.is_available = False
        db.session.commit()

        loaded = db.session.get(Flight, f.id)
        assert loaded.is_available is False


class TestTrackerMarksUnavailable:
    """Tracker should mark flights as unavailable when they disappear from API."""

    def test_future_flight_not_in_api_marked_unavailable(self, app, db, sample_flights):
        """Future flights not updated during poll should be marked is_available=False."""
        from app.services.price_tracker import PriceTracker

        tracker = PriceTracker(app)
        now = datetime.now(timezone.utc)

        # Simulate: only sample_flights[1] (tomorrow DP) was seen in this cycle
        # sample_flights[2] (next_week SU) was NOT seen -> should become unavailable
        seen_keys = {
            (sample_flights[1].depart_date.isoformat(),
             sample_flights[1].airline,
             sample_flights[1].depart_time),
        }

        tracker._mark_unavailable_flights('LED', 'CEK', seen_keys, now)

        # The stale future flight should be unavailable
        stale = db.session.get(Flight, sample_flights[2].id)
        assert stale.is_available is False

        # The fresh future flight should still be available
        fresh = db.session.get(Flight, sample_flights[1].id)
        assert fresh.is_available is True

        # Past flight should not be touched
        past = db.session.get(Flight, sample_flights[0].id)
        assert past.is_available is True

    def test_flight_reappears_marked_available_again(self, app, db, sample_flights):
        """When a previously unavailable flight reappears in API, mark available."""
        from app.services.price_tracker import PriceTracker

        tracker = PriceTracker(app)
        now = datetime.now(timezone.utc)

        # First: mark flight as unavailable
        sample_flights[2].is_available = False
        db.session.commit()

        # Now simulate: this flight appears in API again
        seen_keys = {
            (sample_flights[1].depart_date.isoformat(),
             sample_flights[1].airline,
             sample_flights[1].depart_time),
            (sample_flights[2].depart_date.isoformat(),
             sample_flights[2].airline,
             sample_flights[2].depart_time),
        }

        tracker._mark_unavailable_flights('LED', 'CEK', seen_keys, now)

        reappeared = db.session.get(Flight, sample_flights[2].id)
        assert reappeared.is_available is True


class TestCalendarAPIAvailability:
    """Calendar API should include is_available flag in response."""

    def test_api_includes_is_available_field(self, client, db, sample_flights):
        """Each flight in API response should have is_available field."""
        tomorrow = date.today() + timedelta(days=1)
        month_str = tomorrow.strftime('%Y-%m')

        resp = client.get(f'/api/calendar/LED/CEK?month={month_str}')
        data = resp.get_json()

        day_key = tomorrow.isoformat()
        assert day_key in data['days']

        flights = data['days'][day_key]['flights']
        assert len(flights) >= 1

        for flight in flights:
            assert 'is_available' in flight

    def test_unavailable_flight_shown_in_api(self, client, db, sample_flights):
        """Unavailable flights should still appear in API (for statistics)."""
        next_week = date.today() + timedelta(days=7)
        month_str = next_week.strftime('%Y-%m')

        # Mark as unavailable
        sample_flights[2].is_available = False
        db.session.commit()

        resp = client.get(f'/api/calendar/LED/CEK?month={month_str}')
        data = resp.get_json()

        day_key = next_week.isoformat()
        assert day_key in data['days']

        flights = data['days'][day_key]['flights']
        su_flight = [f for f in flights if f['airline'] == 'SU']
        assert len(su_flight) == 1
        assert su_flight[0]['is_available'] is False

    def test_cheapest_price_only_from_available(self, client, db):
        """Day's cheapest_price should only consider available flights."""
        tomorrow = date.today() + timedelta(days=1)
        now = datetime.now(timezone.utc)

        # Cheap but unavailable
        f1 = Flight(
            origin='LED', destination='CEK',
            depart_date=tomorrow,
            airline='DP', depart_time='10:00',
            flight_number='DP 100', price=3000,
            found_at=now, updated_at=now,
            is_available=False,
        )
        # More expensive but available
        f2 = Flight(
            origin='LED', destination='CEK',
            depart_date=tomorrow,
            airline='SU', depart_time='14:00',
            flight_number='SU 200', price=7000,
            found_at=now, updated_at=now,
            is_available=True,
        )
        db.session.add_all([f1, f2])
        db.session.commit()

        month_str = tomorrow.strftime('%Y-%m')
        resp = client.get(f'/api/calendar/LED/CEK?month={month_str}')
        data = resp.get_json()

        day_key = tomorrow.isoformat()
        # cheapest_price should be 7000 (available), not 3000 (unavailable)
        assert data['days'][day_key]['cheapest_price'] == 7000


class TestIndexPageAvailability:
    """Index page should only show available future flights as cheapest."""

    def test_index_cheapest_ignores_unavailable(self, client, db):
        """Homepage cheapest price should skip unavailable flights."""
        tomorrow = date.today() + timedelta(days=1)
        now = datetime.now(timezone.utc)

        # Cheapest but unavailable
        f1 = Flight(
            origin='LED', destination='CEK',
            depart_date=tomorrow,
            airline='DP', depart_time='10:00',
            flight_number='DP 100', price=2000,
            found_at=now, updated_at=now,
            is_available=False,
        )
        # Available
        f2 = Flight(
            origin='LED', destination='CEK',
            depart_date=tomorrow,
            airline='SU', depart_time='14:00',
            flight_number='SU 200', price=9000,
            found_at=now, updated_at=now,
            is_available=True,
        )
        db.session.add_all([f1, f2])
        db.session.commit()

        resp = client.get('/')
        html = resp.data.decode()

        # Should show 9000, not 2000
        assert '9\xa0000' in html or '9 000' in html or '9000' in html

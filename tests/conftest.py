import pytest
from datetime import date, datetime, timezone, timedelta
from app import create_app
from app.database import db as _db
from app.models import Flight, PriceHistory, Airline


@pytest.fixture
def app():
    """Create app with test config (in-memory SQLite)."""
    app = create_app(test_config={
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
    })

    with app.app_context():
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db(app):
    """Database session fixture."""
    with app.app_context():
        yield _db


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def sample_flights(db):
    """Create sample flights for testing."""
    now = datetime.now(timezone.utc)
    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    next_week = today + timedelta(days=7)

    flights = [
        # Past flight
        Flight(
            origin='LED', destination='CEK',
            depart_date=yesterday,
            airline='DP', depart_time='10:00',
            flight_number='DP 123', price=5000,
            departure_at=f'{yesterday}T10:00:00+03:00',
            duration=180, link='test_link_1',
            found_at=now, updated_at=now,
        ),
        # Future flight - available (updated recently)
        Flight(
            origin='LED', destination='CEK',
            depart_date=tomorrow,
            airline='DP', depart_time='10:00',
            flight_number='DP 456', price=6000,
            departure_at=f'{tomorrow}T10:00:00+03:00',
            duration=180, link='test_link_2',
            found_at=now, updated_at=now,
        ),
        # Future flight - stale (not updated, should become unavailable)
        Flight(
            origin='LED', destination='CEK',
            depart_date=next_week,
            airline='SU', depart_time='14:00',
            flight_number='SU 789', price=8000,
            departure_at=f'{next_week}T14:00:00+03:00',
            duration=180, link='test_link_3',
            found_at=now - timedelta(hours=2),
            updated_at=now - timedelta(hours=2),
        ),
    ]

    for f in flights:
        db.session.add(f)
    db.session.commit()
    return flights

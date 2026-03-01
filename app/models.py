from datetime import datetime, timezone
from app.database import db


class Flight(db.Model):
    __tablename__ = 'flights'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    origin = db.Column(db.String(3), nullable=False)
    destination = db.Column(db.String(3), nullable=False)
    depart_date = db.Column(db.Date, nullable=False)
    airline = db.Column(db.String(10), nullable=False)
    depart_time = db.Column(db.String(5), nullable=False)  # "HH:MM" UTC — part of unique key
    flight_number = db.Column(db.String(20))
    price = db.Column(db.Integer, nullable=False)
    departure_at = db.Column(db.String(50))
    duration = db.Column(db.Integer)
    link = db.Column(db.Text)
    found_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_available = db.Column(db.Boolean, default=True, nullable=False, server_default="1")

    # Playwright-enriched fields
    baggage_count = db.Column(db.Integer)           # checked bags (0 = no baggage)
    baggage_weight = db.Column(db.Integer)          # bag weight in kg
    fare_name = db.Column(db.String(100))           # tariff name (Лайт, Стандарт)
    seats_available = db.Column(db.Integer)         # "Осталось X билетов"
    equipment = db.Column(db.String(100))           # aircraft type (Boeing 737-800)
    arrive_time_local = db.Column(db.String(5))     # HH:MM local arrival time

    price_history = db.relationship('PriceHistory', backref='flight',
                                    cascade='all, delete-orphan',
                                    order_by='PriceHistory.changed_at.desc()')

    __table_args__ = (
        db.UniqueConstraint('origin', 'destination', 'depart_date',
                            'airline', 'depart_time',
                            name='uq_flight_route'),
        db.Index('idx_flights_route', 'origin', 'destination', 'depart_date'),
    )

    def __repr__(self):
        return f'<Flight {self.airline}{self.flight_number} {self.origin}->{self.destination} {self.depart_date} {self.depart_time} {self.price}₽>'


class PriceHistory(db.Model):
    __tablename__ = 'price_history'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    flight_id = db.Column(db.Integer, db.ForeignKey('flights.id', ondelete='CASCADE'), nullable=False)
    old_price = db.Column(db.Integer, nullable=False)
    new_price = db.Column(db.Integer, nullable=False)
    changed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Airline(db.Model):
    __tablename__ = 'airlines'

    iata_code = db.Column(db.String(10), primary_key=True)
    name_ru = db.Column(db.String(200))
    name_en = db.Column(db.String(200))
    is_lowcost = db.Column(db.Boolean, default=False)

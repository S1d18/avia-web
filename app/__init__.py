from flask import Flask
from config import Config
from app.database import db


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)

    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    with app.app_context():
        from app.models import Flight, PriceHistory, Airline
        db.create_all()

        # Migrate: add new columns to existing tables (SQLite ALTER TABLE)
        from sqlalchemy import text, inspect
        inspector = inspect(db.engine)
        existing_cols = {col['name'] for col in inspector.get_columns('flights')}
        new_columns = {
            'baggage_count': 'INTEGER',
            'baggage_weight': 'INTEGER',
            'fare_name': 'VARCHAR(100)',
            'seats_available': 'INTEGER',
            'equipment': 'VARCHAR(100)',
            'arrive_time_local': 'VARCHAR(5)',
        }
        for col_name, col_type in new_columns.items():
            if col_name not in existing_cols:
                db.session.execute(text(
                    f'ALTER TABLE flights ADD COLUMN {col_name} {col_type}'))

        # Enable WAL mode for safer concurrent access
        db.session.execute(text('PRAGMA journal_mode=WAL'))
        db.session.commit()

    from app.routes.main_routes import main_bp
    app.register_blueprint(main_bp)

    from app.routes.scrape_routes import scrape_bp
    app.register_blueprint(scrape_bp)

    return app

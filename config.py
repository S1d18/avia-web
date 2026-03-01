import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    AVIA_API = os.getenv('AVIA_API', '')
    AVIA_ID = os.getenv('AVIA_ID', '548874')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///avia_tracker.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    POLL_INTERVAL_MINUTES = 3
    AIRLINES_UPDATE_HOURS = 24

    # Discovery scan (full range sweep)
    DISCOVERY_INTERVAL_MINUTES = 60
    DISCOVERY_PRICE_STEP = 100
    DISCOVERY_MAX_PRICE = 35000

    # Price update (smart ranges around known prices)
    UPDATE_PRICE_PADDING = 200

    # Scrape import API key (for distributed scraping from PCs)
    SCRAPE_API_KEY = os.getenv('SCRAPE_API_KEY', '')

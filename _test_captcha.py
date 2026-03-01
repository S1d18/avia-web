"""Quick test: scrape 5 days LED<->CEK with extension-based captcha solving."""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)

from dotenv import load_dotenv
load_dotenv()

from app.services.parse_playwright import scrape_all

data = scrape_all(
    days_ahead=5,
    routes=[('LED', 'CEK'), ('CEK', 'LED')],
    headless=False,
    captcha_api_key=os.getenv('CAPTCHA_API_KEY'),
)

total = 0
for (origin, dest), route_data in data.items():
    for date_str, flights in route_data.items():
        print(f'  {origin}->{dest} {date_str}: {len(flights)} flights')
        total += len(flights)

print(f'\nTotal: {total} flights')

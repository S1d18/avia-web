import logging
import os
from apscheduler.schedulers.background import BackgroundScheduler
from config import Config

logger = logging.getLogger(__name__)

_scheduler = None


def init_scheduler(app):
    """Initialize and start APScheduler.

    Primary data source: Playwright on PCs → POST /api/scrape/import every 10 min.

    Scheduled jobs on RPi:
    - link_poll: daily at 00:00 — PFD only, fills in affiliate links for existing flights
    - update_airlines: every 24h — airlines directory cache

    First run with clean DB:
    1. Run Playwright from PC: python scrape_and_send.py --days 90
    2. link_poll will then fill affiliate links for discovered flights
    """
    global _scheduler

    # In debug mode with reloader, skip the parent process
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        logger.info('Skipping scheduler in reloader parent process')
        return

    from app.services.price_tracker import PriceTracker
    tracker = PriceTracker(app)

    # Store tracker on app for access from routes
    app.tracker = tracker

    _scheduler = BackgroundScheduler(daemon=True)

    # Daily: affiliate link update (PFD only) at 00:00
    _scheduler.add_job(
        tracker.link_poll,
        'cron',
        hour=0, minute=0,
        id='link_poll',
        replace_existing=True,
    )

    # Update airlines directory every 24h
    _scheduler.add_job(
        tracker.update_airlines,
        'interval',
        hours=Config.AIRLINES_UPDATE_HOURS,
        id='update_airlines',
        replace_existing=True,
    )

    _scheduler.start()
    logger.info('Scheduler started: link_poll at 00:00, airlines every %d h',
                Config.AIRLINES_UPDATE_HOURS)

    # On startup: update airlines only (link_poll will run at 00:00)
    _scheduler.add_job(
        tracker.update_airlines,
        id='airlines_init',
        replace_existing=True,
    )

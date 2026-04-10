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
    - discovery_light: weekly Monday 00:00 — PFD API for 6 months, discovers new flights
      and updates affiliate links (does NOT overwrite prices from Playwright)
    - update_airlines: every 24h — airlines directory cache
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

    # Weekly (Monday 00:00): discover new flights + update links (PFD API, 6 months)
    _scheduler.add_job(
        tracker.discovery_light,
        'cron',
        day_of_week='mon',
        hour=0, minute=0,
        id='discovery_light',
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
    logger.info('Scheduler started: discovery_light at 00:00, airlines every %d h',
                Config.AIRLINES_UPDATE_HOURS)

    # On startup: update airlines only (link_poll will run at 00:00)
    _scheduler.add_job(
        tracker.update_airlines,
        id='airlines_init',
        replace_existing=True,
    )

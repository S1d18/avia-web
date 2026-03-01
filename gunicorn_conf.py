import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)


def post_fork(server, worker):
    from main import app
    from app.services.scheduler import init_scheduler
    app.debug = False
    init_scheduler(app)
    server.log.info('Scheduler started in worker %s', worker.pid)

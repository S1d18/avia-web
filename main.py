import logging
from app import create_app

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)

app = create_app()

if __name__ == '__main__':
    from app.services.scheduler import init_scheduler
    app.debug = True
    init_scheduler(app)
    app.run(host='127.0.0.1', port=5000, debug=True)

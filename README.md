# Avia Web
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

Трекер цен на авиабилеты с мониторингом в реальном времени.

## Возможности

- Мониторинг цен на прямые рейсы
- Календарь с ценами по дням
- История изменения цен
- Интеграция с Travelpayouts API
- Скрапинг aviasales.ru через Playwright
- Аффилиатные ссылки на бронирование
- REST API для данных
- Автоматическое обновление по расписанию (APScheduler)

## Технологии

- Python 3 / Flask
- SQLAlchemy / SQLite
- APScheduler — планировщик задач
- Playwright — скрапинг
- Jinja2 — шаблоны
- Gunicorn — продакшн-сервер

## Установка

```bash
git clone https://github.com/<username>/avia-web.git
cd avia-web
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
pip install -r requirements.txt
playwright install chromium
```

## Настройка

Создайте файл `.env`:
```
AVIA_API=your-travelpayouts-api-token
AVIA_ID=your-marker-id
SCRAPE_API_KEY=your-scrape-api-key
CAPTCHA_API_KEY=your-2captcha-api-key
SCRAPE_PROXIES=
SCRAPE_INTERVAL=30
```

## Запуск

### Разработка
```bash
python main.py
```

### Продакшн
```bash
gunicorn -c gunicorn_conf.py "app:create_app()"
```

### Скрапер (отдельно)
```bash
python scrape_and_send.py
```

## Архитектура

```
avia_web/
├── app/
│   ├── models.py          # Модели: Flight, PriceHistory, Airline
│   ├── routes/
│   │   ├── main_routes.py # Веб-страницы + API календаря
│   │   └── scrape_routes.py # API импорта данных
│   ├── services/
│   │   ├── api_client.py  # Клиент Travelpayouts API
│   │   ├── link_builder.py # Генератор аффилиатных ссылок
│   │   ├── price_tracker.py # Обновление цен
│   │   └── scheduler.py   # Планировщик задач
│   ├── static/            # CSS, JS
│   └── templates/         # HTML шаблоны
├── config.py              # Конфигурация
├── main.py                # Точка входа (dev)
└── scrape_and_send.py     # Скрапер
```

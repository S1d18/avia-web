# Flight Price Tracker — План масштабирования на всю Россию

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Цель:** Превратить трекер цен LED↔CEK в полноценный сервис мониторинга цен на авиабилеты по всей России (496 направлений), развёрнутый на Raspberry Pi 4 (8GB), с поддержкой 2000-5000 пользователей в день и монетизацией через партнёрскую программу Travelpayouts.

**Уникальное преимущество:** Отслеживание истории изменения цен — чего нет у других сайтов (Aviasales, Skyscanner показывают только текущую цену).

**Платформа:** Raspberry Pi 4 (8GB RAM, ARM64, Debian 13, Python 3.13)

**Текущий стек:** Flask 3.1 + SQLAlchemy + APScheduler + SQLite + Vanilla JS

---с

## Оглавление

1. [Фаза 0: Подготовка инфраструктуры на RPi](#фаза-0-подготовка-инфраструктуры-на-rpi)
2. [Фаза 1: Динамические маршруты](#фаза-1-динамические-маршруты)
3. [Фаза 2: Умный планировщик опроса](#фаза-2-умный-планировщик-опроса)
4. [Фаза 3: Новый UI — поиск и выбор маршрутов](#фаза-3-новый-ui--поиск-и-выбор-маршрутов)
5. [Фаза 4: Оптимизация производительности](#фаза-4-оптимизация-производительности)
6. [Фаза 5: Пользователи и подписки](#фаза-5-пользователи-и-подписки)
7. [Фаза 6: Telegram-бот с уведомлениями](#фаза-6-telegram-бот-с-уведомлениями)
8. [Фаза 7: SEO и монетизация](#фаза-7-seo-и-монетизация)
9. [Фаза 8: Международные направления](#фаза-8-международные-направления)
10. [API лимиты и бюджет запросов](#api-лимиты-и-бюджет-запросов)
11. [Архитектура целевой системы](#архитектура-целевой-системы)

---

## Текущее состояние (что есть сейчас)

| Компонент | Текущее | Целевое |
|---|---|---|
| Маршруты | 2 (LED↔CEK, хардкод) | ~496 (вся Россия, из БД) |
| БД | SQLite | PostgreSQL |
| Сервер | Flask dev server | Gunicorn + Nginx |
| Хостинг | Windows localhost | Raspberry Pi 4 |
| Пользователи | 0 | 2000-5000/день |
| Авторизация | нет | OAuth / Telegram Login |
| Уведомления | нет | Telegram-бот |
| Опрос | каждые 3 мин, все маршруты | приоритетный, с ротацией |

## API лимиты и бюджет запросов

### Лимиты Travelpayouts (на эндпоинт, в минуту)

| Эндпоинт | Лимит/мин |
|---|---|
| `/v3/search_by_price_range` (SBPR) | 600 |
| `/v3/prices_for_dates` (PFD) | 600 |
| `/data/*.json` (справочники) | 600 |
| `/v1/city-directions` | 600 |

### Бюджет на 496 маршрутов (вся Россия внутренняя)

| Режим | SBPR запросов | PFD запросов | Время цикла |
|---|---|---|---|
| Минимум (1 SBPR + 1 PFD) | 496 | 496 | ~1 мин |
| Базовый (3 SBPR + 3 PFD) | 1 488 | 1 488 | ~3 мин |
| Полный (6 SBPR + 3 PFD) | 2 976 | 1 488 | ~5 мин |
| Текущий (8 SBPR + 3 PFD) | 3 968 | 1 488 | ~7 мин |

**Вывод:** Базовый режим (3+3) покрывает всю Россию за 3 минуты. Полный (6+3) — за 5 минут. Оба укладываются в лимит 600/мин.

### Реальная статистика маршрутов (из API routes.json)

| Категория | Количество |
|---|---|
| Аэропортов в РФ | 351 |
| Внутренних прямых направлений | 496 (253 пары) |
| Международных прямых из/в РФ | 1 808 |
| Прямых по всему миру | 64 917 |

### Топ-10 городов по внутренним направлениям

| Город | Код | Направлений |
|---|---|---|
| Москва | MOW | 224 |
| Санкт-Петербург | LED | 81 |
| Хабаровск | KHV | 38 |
| Новосибирск | OVB | 35 |
| Екатеринбург | SVX | 31 |
| Иркутск | IKT | 27 |
| Красноярск | KJA | 27 |
| Владивосток | VVO | 24 |
| Якутск | YKS | 22 |
| Уфа | UFA | 19 |

---

## Фаза 0: Подготовка инфраструктуры на RPi

**Цель:** Перенести проект на Raspberry Pi с production-стеком.

### Task 0.1: Установка PostgreSQL на RPi

**На RPi выполнить:**
```bash
sudo apt update && sudo apt install -y postgresql postgresql-contrib libpq-dev
sudo -u postgres createuser avia_user -P  # пароль: задать надёжный
sudo -u postgres createdb avia_tracker -O avia_user
```

**Почему PostgreSQL вместо SQLite:**
- SQLite блокирует всю БД при записи — при опросе 496 маршрутов (5 мин непрерывной записи) сайт будет тормозить
- PostgreSQL поддерживает параллельные чтение + запись
- PostgreSQL лучше работает с большими объёмами данных (сотни тысяч записей)
- Полнотекстовый поиск для поиска городов

### Task 0.2: Установка Nginx + Gunicorn

```bash
sudo apt install -y nginx
pip install gunicorn psycopg2-binary
```

**Конфиг Nginx** (`/etc/nginx/sites-available/avia`):
```nginx
server {
    listen 80;
    server_name avia.example.com;  # или IP

    location /static/ {
        alias /home/pi/avia_web/app/static/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Gunicorn** (systemd сервис `/etc/systemd/system/avia.service`):
```ini
[Unit]
Description=Avia Price Tracker
After=network.target postgresql.service

[Service]
User=pi
WorkingDirectory=/home/pi/avia_web
ExecStart=/home/pi/avia_web/venv/bin/gunicorn -w 4 -b 127.0.0.1:8000 main:app
Restart=always
RestartSec=5
Environment=PATH=/home/pi/avia_web/venv/bin:/usr/bin

[Install]
WantedBy=multi-user.target
```

### Task 0.3: Миграция SQLite → PostgreSQL

**Файлы:**
- Изменить: `config.py` — `SQLALCHEMY_DATABASE_URI`
- Изменить: `requirements.txt` — добавить `psycopg2-binary`
- Изменить: `.env` — добавить `DATABASE_URL`

**config.py:**
```python
class Config:
    # ...
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'sqlite:///avia_tracker.db'  # fallback для локальной разработки
    )
```

**.env на RPi:**
```
DATABASE_URL=postgresql://avia_user:PASSWORD@localhost/avia_tracker
```

**Миграция данных:**
```bash
# На Windows: экспорт
python -c "
from app import create_app
from app.database import db
from app.models import Flight, PriceHistory, Airline
import json

app = create_app()
with app.app_context():
    flights = [{'origin': f.origin, 'destination': f.destination,
                'depart_date': f.depart_date.isoformat(), 'airline': f.airline,
                'depart_time': f.depart_time, 'flight_number': f.flight_number,
                'price': f.price, 'departure_at': f.departure_at,
                'duration': f.duration, 'link': f.link,
                'found_at': f.found_at.isoformat() if f.found_at else None,
                'updated_at': f.updated_at.isoformat() if f.updated_at else None}
               for f in Flight.query.all()]
    json.dump(flights, open('export_flights.json', 'w'))
    print(f'Exported {len(flights)} flights')
"

# На RPi: импорт
python -c "
from app import create_app
from app.database import db
from app.models import Flight
import json
from datetime import date, datetime

app = create_app()
with app.app_context():
    db.create_all()
    flights = json.load(open('export_flights.json'))
    for f in flights:
        flight = Flight(
            origin=f['origin'], destination=f['destination'],
            depart_date=date.fromisoformat(f['depart_date']),
            airline=f['airline'], depart_time=f['depart_time'],
            flight_number=f['flight_number'], price=f['price'],
            departure_at=f['departure_at'], duration=f['duration'],
            link=f['link'],
            found_at=datetime.fromisoformat(f['found_at']) if f['found_at'] else datetime.utcnow(),
            updated_at=datetime.fromisoformat(f['updated_at']) if f['updated_at'] else datetime.utcnow(),
        )
        db.session.add(flight)
    db.session.commit()
    print(f'Imported {len(flights)} flights')
"
```

### Task 0.4: Настройка домена и HTTPS

**Вариант A — Домен + Cloudflare Tunnel (без белого IP):**
```bash
# Установка cloudflared
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb
cloudflared tunnel login
cloudflared tunnel create avia
cloudflared tunnel route dns avia avia.твой-домен.ru
```

**Вариант B — Белый IP + Let's Encrypt:**
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d avia.твой-домен.ru
```

---

## Фаза 1: Динамические маршруты

**Цель:** Заменить хардкод `ROUTES = [('LED', 'CEK'), ('CEK', 'LED')]` на таблицу маршрутов из БД, автоматически загруженную из API.

### Task 1.1: Новые модели — City и Route

**Файл:** `app/models.py`

```python
class City(db.Model):
    """Город с аэропортом."""
    __tablename__ = 'cities'

    code = db.Column(db.String(3), primary_key=True)       # IATA код (LED, MOW, CEK)
    name_ru = db.Column(db.String(200), nullable=False)     # Санкт-Петербург
    name_en = db.Column(db.String(200))                     # Saint Petersburg
    country_code = db.Column(db.String(2))                  # RU

    __table_args__ = (
        db.Index('idx_city_country', 'country_code'),
    )


class Route(db.Model):
    """Маршрут для мониторинга цен."""
    __tablename__ = 'routes'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    origin = db.Column(db.String(3), db.ForeignKey('cities.code'), nullable=False)
    destination = db.Column(db.String(3), db.ForeignKey('cities.code'), nullable=False)
    priority = db.Column(db.String(10), default='warm')     # hot / warm / cold
    is_active = db.Column(db.Boolean, default=True)
    subscriber_count = db.Column(db.Integer, default=0)     # для авто-приоритета
    last_polled_at = db.Column(db.DateTime)
    poll_interval_minutes = db.Column(db.Integer, default=10)
    sbpr_ranges = db.Column(db.Integer, default=3)          # кол-во ценовых диапазонов

    origin_city = db.relationship('City', foreign_keys=[origin])
    destination_city = db.relationship('City', foreign_keys=[destination])

    __table_args__ = (
        db.UniqueConstraint('origin', 'destination', name='uq_route'),
        db.Index('idx_route_priority', 'priority', 'is_active'),
    )
```

**Приоритеты маршрутов:**

| Приоритет | Интервал опроса | SBPR диапазонов | Условие авто-назначения |
|---|---|---|---|
| `hot` | 5 мин | 6 | 10+ подписчиков или ТОП-20 направлений |
| `warm` | 15 мин | 3 | 1-9 подписчиков или прямые из крупных городов |
| `cold` | 60 мин | 1 | 0 подписчиков, редкие направления |

### Task 1.2: Загрузка городов и маршрутов из API

**Файл:** `app/services/route_loader.py` (новый)

```python
import logging
from app.database import db
from app.models import City, Route
from app.services.api_client import TravelpayoutsClient

logger = logging.getLogger(__name__)

# ТОП-20 городов для hot приоритета
HOT_CITIES = {'MOW', 'LED', 'KHV', 'OVB', 'SVX', 'IKT', 'KJA', 'VVO',
              'AER', 'KRR', 'UFA', 'KZN', 'ROV', 'VOG', 'TJM'}


def load_cities(client: TravelpayoutsClient):
    """Загрузить справочник городов из API."""
    cities_data = client.fetch_json('/data/ru/cities.json')
    count = 0
    for c in cities_data:
        code = c.get('code')
        if not code or c.get('country_code') != 'RU':
            continue
        name_ru = c.get('name') or c.get('name_translations', {}).get('ru', code)
        name_en = c.get('name_translations', {}).get('en', '')

        existing = db.session.get(City, code)
        if existing:
            existing.name_ru = name_ru
            existing.name_en = name_en
        else:
            db.session.add(City(code=code, name_ru=name_ru, name_en=name_en,
                                country_code='RU'))
        count += 1

    db.session.commit()
    logger.info('Cities loaded: %d Russian cities', count)
    return count


def load_routes(client: TravelpayoutsClient):
    """Загрузить маршруты из API routes.json.
    Только прямые рейсы внутри России."""
    airports_data = client.fetch_json('/data/ru/airports.json')

    # Маппинг аэропорт -> город
    airport_to_city = {}
    ru_airports = set()
    for a in airports_data:
        code = a.get('code')
        if code and a.get('country_code') == 'RU':
            ru_airports.add(code)
            airport_to_city[code] = a.get('city_code', code)

    routes_data = client.fetch_json('/data/routes.json')

    seen_pairs = set()
    count = 0
    for r in routes_data:
        if r.get('transfers', 0) > 0:
            continue
        dep = r.get('departure_airport_iata')
        arr = r.get('arrival_airport_iata')
        if dep not in ru_airports or arr not in ru_airports:
            continue

        origin = airport_to_city.get(dep, dep)
        dest = airport_to_city.get(arr, arr)
        if origin == dest:
            continue

        pair = (origin, dest)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        # Определить приоритет
        if origin in HOT_CITIES and dest in HOT_CITIES:
            priority = 'hot'
        elif origin in HOT_CITIES or dest in HOT_CITIES:
            priority = 'warm'
        else:
            priority = 'cold'

        existing = Route.query.filter_by(origin=origin, destination=dest).first()
        if not existing:
            db.session.add(Route(
                origin=origin, destination=dest,
                priority=priority, is_active=True,
                sbpr_ranges=6 if priority == 'hot' else 3 if priority == 'warm' else 1,
            ))
            count += 1

    db.session.commit()
    logger.info('Routes loaded: %d new routes (total pairs: %d)', count, len(seen_pairs))
    return count
```

### Task 1.3: Добавить `fetch_json` в api_client.py

**Файл:** `app/services/api_client.py`

Добавить универсальный метод:
```python
def fetch_json(self, path):
    """Fetch any JSON endpoint from Travelpayouts API."""
    try:
        resp = self.session.get(f'{API_BASE}{path}', timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logger.exception('Failed to fetch %s', path)
        return []
```

### Task 1.4: Обновить price_tracker — маршруты из БД

**Файл:** `app/services/price_tracker.py`

Заменить хардкод `ROUTES` на запрос из БД:
```python
def poll_prices(self):
    """Main polling cycle: fetch flights for routes due for polling."""
    logger.info('Starting price poll...')
    with self.app.app_context():
        routes = self._get_routes_to_poll()
        logger.info('Polling %d routes this cycle', len(routes))

        for i, route in enumerate(routes):
            if i > 0:
                time.sleep(0.1)  # Минимальная задержка для rate limit
            self._poll_route(route.origin, route.destination)
            route.last_polled_at = datetime.now(timezone.utc)
            db.session.commit()

        self.last_update = datetime.now(timezone.utc)
    logger.info('Price poll complete: %d routes updated.', len(routes))

def _get_routes_to_poll(self):
    """Выбрать маршруты, которые пора обновить."""
    now = datetime.now(timezone.utc)
    routes = (Route.query
              .filter_by(is_active=True)
              .order_by(Route.last_polled_at.asc().nullsfirst())
              .all())

    due = []
    for r in routes:
        if r.last_polled_at is None:
            due.append(r)
        else:
            elapsed = (now - r.last_polled_at.replace(tzinfo=timezone.utc)).total_seconds() / 60
            if elapsed >= r.poll_interval_minutes:
                due.append(r)

    # Ограничить количество маршрутов за цикл (чтобы уложиться в лимит API)
    # 600 SBPR/мин, 600 PFD/мин. Безопасно: ~50 маршрутов за цикл
    MAX_PER_CYCLE = 50
    return due[:MAX_PER_CYCLE]
```

### Task 1.5: Обновить main_routes.py — динамические маршруты

**Файл:** `app/routes/main_routes.py`

Убрать хардкод `ALLOWED_ROUTES` и `ROUTE_NAMES`:
```python
from app.models import Flight, PriceHistory, Airline, City, Route

@main_bp.route('/')
def index():
    """Главная — популярные направления."""
    hot_routes = (Route.query
                  .filter_by(is_active=True, priority='hot')
                  .order_by(Route.subscriber_count.desc())
                  .limit(20).all())

    routes_data = []
    for r in hot_routes:
        cheapest = (Flight.query
                    .filter_by(origin=r.origin, destination=r.destination)
                    .filter(Flight.depart_date >= date.today())
                    .order_by(Flight.price.asc())
                    .first())
        routes_data.append({
            'origin': r.origin,
            'destination': r.destination,
            'origin_name': r.origin_city.name_ru,
            'dest_name': r.destination_city.name_ru,
            'cheapest': cheapest,
        })

    return render_template('index.html', routes=routes_data)


@main_bp.route('/route/<origin>/<destination>')
def route_calendar(origin, destination):
    """Календарь цен — любой маршрут из БД."""
    origin = origin.upper()
    destination = destination.upper()
    route = Route.query.filter_by(origin=origin, destination=destination).first()
    if not route:
        return 'Route not found', 404

    return render_template('calendar.html',
                           origin=origin, destination=destination,
                           origin_name=route.origin_city.name_ru,
                           dest_name=route.destination_city.name_ru)
```

### Task 1.6: API поиска городов

**Файл:** `app/routes/main_routes.py`

```python
@main_bp.route('/api/search_cities')
def api_search_cities():
    """Поиск городов для автокомплита."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])

    cities = (City.query
              .filter(City.country_code == 'RU')
              .filter(db.or_(
                  City.name_ru.ilike(f'{q}%'),
                  City.name_en.ilike(f'{q}%'),
                  City.code.ilike(f'{q}%'),
              ))
              .limit(10).all())

    return jsonify([{
        'code': c.code,
        'name': c.name_ru,
    } for c in cities])
```

---

## Фаза 2: Умный планировщик опроса

**Цель:** Вместо фиксированного интервала — адаптивный планировщик, который учитывает приоритеты и лимиты API.

### Task 2.1: Rate limiter для API

**Файл:** `app/services/rate_limiter.py` (новый)

```python
import time
import threading
from collections import defaultdict

class RateLimiter:
    """Потокобезопасный rate limiter по эндпоинтам."""

    def __init__(self):
        self.requests = defaultdict(list)  # endpoint -> [timestamp, ...]
        self.limits = {
            'search_by_price_range': 600,
            'prices_for_dates': 600,
        }
        self.lock = threading.Lock()

    def wait_if_needed(self, endpoint):
        """Подождать если лимит исчерпан."""
        limit = self.limits.get(endpoint, 600)
        with self.lock:
            now = time.time()
            # Убрать запросы старше 60 сек
            self.requests[endpoint] = [t for t in self.requests[endpoint] if now - t < 60]

            if len(self.requests[endpoint]) >= limit:
                # Подождать до освобождения слота
                oldest = self.requests[endpoint][0]
                sleep_time = 60 - (now - oldest) + 0.1
                if sleep_time > 0:
                    time.sleep(sleep_time)

            self.requests[endpoint].append(time.time())
```

### Task 2.2: Авто-приоритет на основе подписчиков

**Файл:** `app/services/price_tracker.py`

```python
def _update_route_priorities(self):
    """Обновить приоритеты маршрутов на основе подписчиков."""
    routes = Route.query.filter_by(is_active=True).all()
    for r in routes:
        if r.subscriber_count >= 10:
            r.priority = 'hot'
            r.poll_interval_minutes = 5
            r.sbpr_ranges = 6
        elif r.subscriber_count >= 1:
            r.priority = 'warm'
            r.poll_interval_minutes = 15
            r.sbpr_ranges = 3
        else:
            r.priority = 'cold'
            r.poll_interval_minutes = 60
            r.sbpr_ranges = 1
    db.session.commit()
```

### Task 2.3: Адаптивные ценовые диапазоны

**Файл:** `app/services/api_client.py`

Вместо одного набора `PRICE_RANGES` — функция, которая возвращает N диапазонов:

```python
def get_price_ranges(count):
    """Вернуть N ценовых диапазонов для SBPR запросов."""
    ALL_RANGES = [
        (1, 3000),
        (3001, 5000),
        (5001, 6500),
        (6501, 8000),
        (8001, 10000),
        (10001, 15000),
        (15001, 25000),
        (25001, 50000),
        (50001, 100000),
    ]
    if count >= len(ALL_RANGES):
        return ALL_RANGES
    # Равномерно выбрать count диапазонов
    step = len(ALL_RANGES) / count
    return [ALL_RANGES[int(i * step)] for i in range(count)]
```

---

## Фаза 3: Новый UI — поиск и выбор маршрутов

**Цель:** Пользователь выбирает откуда-куда, видит календарь цен с историей.

### Task 3.1: Новая главная страница

**Файл:** `app/templates/index.html`

Вместо двух карточек LED↔CEK — поисковая форма:

```html
<div class="search-section">
    <h1>Мониторинг цен на авиабилеты</h1>
    <p>Отслеживаем изменение цен по всей России. Видите историю — покупаете в лучший момент.</p>

    <form class="search-form" id="searchForm">
        <div class="search-field">
            <label>Откуда</label>
            <input type="text" id="originInput" placeholder="Москва" autocomplete="off">
            <div class="search-dropdown" id="originDropdown"></div>
        </div>
        <button type="button" class="swap-btn" id="swapBtn">⇄</button>
        <div class="search-field">
            <label>Куда</label>
            <input type="text" id="destInput" placeholder="Сочи" autocomplete="off">
            <div class="search-dropdown" id="destDropdown"></div>
        </div>
        <button type="submit" class="search-btn">Показать цены</button>
    </form>
</div>

<!-- Популярные направления -->
<div class="popular-routes">
    <h2>Популярные направления</h2>
    <div class="route-cards">
        {% for r in routes %}
        <a href="/route/{{ r.origin }}/{{ r.destination }}" class="route-card">
            ...
        </a>
        {% endfor %}
    </div>
</div>
```

### Task 3.2: Автокомплит городов (JS)

**Файл:** `app/static/js/search.js` (новый)

```javascript
class CitySearch {
    constructor(inputId, dropdownId, onSelect) {
        this.input = document.getElementById(inputId);
        this.dropdown = document.getElementById(dropdownId);
        this.onSelect = onSelect;
        this.selectedCode = null;
        this.debounceTimer = null;

        this.input.addEventListener('input', () => this.onInput());
        this.input.addEventListener('focus', () => this.onInput());
        document.addEventListener('click', (e) => {
            if (!this.input.contains(e.target)) this.dropdown.classList.remove('open');
        });
    }

    onInput() {
        clearTimeout(this.debounceTimer);
        const q = this.input.value.trim();
        if (q.length < 2) {
            this.dropdown.classList.remove('open');
            return;
        }
        this.debounceTimer = setTimeout(() => this.search(q), 200);
    }

    async search(q) {
        const resp = await fetch(`/api/search_cities?q=${encodeURIComponent(q)}`);
        const cities = await resp.json();

        this.dropdown.innerHTML = '';
        cities.forEach(c => {
            const item = document.createElement('div');
            item.className = 'dropdown-item';
            item.textContent = `${c.name} (${c.code})`;
            item.addEventListener('click', () => {
                this.input.value = c.name;
                this.selectedCode = c.code;
                this.dropdown.classList.remove('open');
                this.onSelect(c);
            });
            this.dropdown.appendChild(item);
        });

        if (cities.length) this.dropdown.classList.add('open');
    }
}
```

### Task 3.3: Страница маршрута с графиком цен

Добавить визуализацию истории цен (график min цены по дням):

```javascript
// В calendar page — мини-график цен за последние 30 дней
// Использовать <canvas> + нативный JS (без Chart.js для скорости)
function drawPriceChart(canvasId, priceData) {
    const canvas = document.getElementById(canvasId);
    const ctx = canvas.getContext('2d');
    // ... нативная отрисовка линейного графика
}
```

---

## Фаза 4: Оптимизация производительности

**Цель:** Обеспечить отзывчивость при 2000-5000 пользователях/день на RPi 4.

### Task 4.1: Кэширование API ответов

**Файл:** `app/services/cache.py` (новый)

```python
import time
from functools import wraps

_cache = {}

def cached(ttl_seconds=60):
    """Простой in-memory кэш с TTL."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = f'{func.__name__}:{args}:{kwargs}'
            if key in _cache:
                value, ts = _cache[key]
                if time.time() - ts < ttl_seconds:
                    return value
            result = func(*args, **kwargs)
            _cache[key] = (result, time.time())
            return result
        return wrapper
    return decorator
```

Применить к `api_calendar`:
```python
@cached(ttl_seconds=30)
def _get_calendar_data(origin, destination, year, month):
    """Закэшированные данные календаря."""
    # ... текущая логика из api_calendar
```

### Task 4.2: Индексы БД для скорости

```python
# В models.py — дополнительные индексы
class Flight(db.Model):
    __table_args__ = (
        db.UniqueConstraint('origin', 'destination', 'depart_date',
                            'airline', 'depart_time', name='uq_flight_route'),
        db.Index('idx_flights_route', 'origin', 'destination', 'depart_date'),
        db.Index('idx_flights_price', 'origin', 'destination', 'price'),  # НОВЫЙ
        db.Index('idx_flights_date_future', 'depart_date'),               # НОВЫЙ
    )
```

### Task 4.3: Gzip-сжатие в Nginx

```nginx
gzip on;
gzip_types application/json text/css text/javascript application/javascript;
gzip_min_length 1000;
gzip_comp_level 6;
```

### Task 4.4: Статика — кэширование и минификация

Nginx уже отдаёт статику с `expires 7d`. Дополнительно:
- CSS/JS версионирование: `style.css?v={{ version }}`
- Можно добавить `flask-assets` для минификации

### Task 4.5: Пагинация для тяжёлых запросов

Главная страница с 20 популярными маршрутами — это 20 SQL-запросов на cheapest. Оптимизировать одним запросом:

```python
# Один запрос вместо 20
from sqlalchemy import func

cheapest_subq = (
    db.session.query(
        Flight.origin, Flight.destination,
        func.min(Flight.price).label('min_price')
    )
    .filter(Flight.depart_date >= date.today())
    .group_by(Flight.origin, Flight.destination)
    .subquery()
)
```

---

## Фаза 5: Пользователи и подписки

**Цель:** Регистрация, личные маршруты, подписка на снижение цен.

### Task 5.1: Модель пользователя

**Файл:** `app/models.py`

```python
class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.BigInteger, unique=True)    # Telegram Login
    username = db.Column(db.String(100))
    display_name = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    subscriptions = db.relationship('Subscription', backref='user', cascade='all, delete-orphan')


class Subscription(db.Model):
    """Подписка пользователя на маршрут."""
    __tablename__ = 'subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    route_id = db.Column(db.Integer, db.ForeignKey('routes.id'), nullable=False)
    max_price = db.Column(db.Integer)                       # Уведомить если цена ниже
    notify_any_change = db.Column(db.Boolean, default=False)  # Уведомлять о любом изменении
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    route = db.relationship('Route')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'route_id', name='uq_user_route'),
    )
```

### Task 5.2: Telegram Login Widget

**Почему Telegram Login, а не email:**
- Целевая аудитория — русскоязычная, у всех есть Telegram
- Не нужно хранить пароли
- Готовый виджет от Telegram
- Подписки на уведомления автоматически через Telegram

**Файл:** `app/templates/base.html`

```html
<script async src="https://telegram.org/js/telegram-widget.js?22"
        data-telegram-login="AviaPriceBot"
        data-size="medium"
        data-auth-url="/auth/telegram"
        data-request-access="write"></script>
```

### Task 5.3: Личный кабинет

- Список подписок (маршруты + порог цены)
- Добавить/удалить маршрут
- Настроить уведомления

---

## Фаза 6: Telegram-бот с уведомлениями

**Цель:** Бот отправляет пользователю сообщение когда цена на его маршрут упала.

### Task 6.1: Базовый бот

**Файл:** `app/services/telegram_bot.py` (новый)

```python
import requests
import logging

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, token):
        self.token = token
        self.api_url = f'https://api.telegram.org/bot{token}'

    def send_price_alert(self, chat_id, route, flight, old_price, new_price):
        """Отправить уведомление о снижении цены."""
        diff = old_price - new_price
        text = (
            f"✈️ *{route.origin_city.name_ru} → {route.destination_city.name_ru}*\n\n"
            f"💰 Цена снизилась: ~~{old_price}~~ → *{new_price} ₽*\n"
            f"📉 Экономия: {diff} ₽\n"
            f"🗓 Дата: {flight.depart_date.strftime('%d.%m.%Y')}\n"
            f"✈ {flight.airline} {flight.flight_number}\n\n"
            f"[Купить билет]({build_booking_url(flight.link)})"
        )

        try:
            resp = requests.post(f'{self.api_url}/sendMessage', json={
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': True,
            })
            resp.raise_for_status()
        except Exception:
            logger.exception('Failed to send Telegram notification to %s', chat_id)
```

### Task 6.2: Интеграция с price_tracker

При записи в PriceHistory — проверить подписки и отправить уведомления:

```python
def _notify_subscribers(self, flight, old_price, new_price):
    """Проверить подписки и отправить уведомления."""
    if new_price >= old_price:
        return  # Уведомляем только о снижении

    subs = (Subscription.query
            .join(Route)
            .filter(Route.origin == flight.origin,
                    Route.destination == flight.destination)
            .all())

    for sub in subs:
        if sub.max_price and new_price > sub.max_price:
            continue
        if not sub.notify_any_change and not sub.max_price:
            continue

        self.notifier.send_price_alert(
            sub.user.telegram_id,
            sub.route, flight, old_price, new_price
        )
```

---

## Фаза 7: SEO и монетизация

**Цель:** Привлечь органический трафик и максимизировать доход от партнёрки.

### Task 7.1: SEO-оптимизация

**Семантические URL:**
```
/flights/moscow-sochi/                    — календарь Москва→Сочи
/flights/moscow-sochi/2026-03/            — конкретный месяц
/flights/moscow-sochi/2026-03-15/         — конкретная дата
```

**Meta-теги:**
```html
<title>Авиабилеты Москва — Сочи от 3 450 ₽ | История цен</title>
<meta name="description" content="Мониторинг цен на прямые рейсы Москва — Сочи.
      Отслеживаем изменения цен, показываем историю. Купить дёшево.">
```

**Structured data (JSON-LD):**
```html
<script type="application/ld+json">
{
    "@context": "https://schema.org",
    "@type": "Product",
    "name": "Авиабилет Москва — Сочи",
    "offers": {
        "@type": "AggregateOffer",
        "lowPrice": "3450",
        "priceCurrency": "RUB"
    }
}
</script>
```

### Task 7.2: Sitemap.xml

```python
@main_bp.route('/sitemap.xml')
def sitemap():
    """Генерация sitemap для всех активных маршрутов."""
    routes = Route.query.filter_by(is_active=True).all()
    # ... XML sitemap с приоритетами для hot маршрутов
```

### Task 7.3: Оптимизация конверсии

- Кнопка "Купить" — крупная, заметная, на каждой карточке
- Показывать "Цена снизилась на X₽" — мотивирует купить сейчас
- Показывать график цен — "Текущая цена — минимальная за месяц"

### Task 7.4: Рекламные блоки (опционально)

- Яндекс.Директ (РСЯ) — баннеры между маршрутами
- Не перегружать страницу — максимум 2 блока на страницу

---

## Фаза 8: Международные направления (будущее)

**Цель:** Расширить покрытие за пределы России.

### Этап 8.1: СНГ (1 808 направлений)

Международные прямые из/в Россию уже есть в routes.json. Добавить их с приоритетом `cold` и включать по мере появления подписчиков.

### Этап 8.2: Весь мир (64 917 направлений)

- On-demand: пользователь ищет маршрут → создаётся Route с приоритетом cold
- Если набирает подписчиков → повышается приоритет
- Лимиты: 64 917 маршрутов × 2 запроса = ~3 часа полного цикла (PFD only)

---

## Архитектура целевой системы

```
                    ┌──────────────────┐
                    │   Cloudflare     │
                    │   (DNS + CDN)    │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │     Nginx        │
                    │  (reverse proxy  │
                    │   + static)      │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   Gunicorn       │
                    │  (4 workers)     │
                    │   Flask App      │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
    ┌─────────▼──┐  ┌───────▼────┐  ┌──────▼─────┐
    │ PostgreSQL │  │ APScheduler│  │  Telegram   │
    │  (data)    │  │  (polling) │  │   Bot API   │
    └────────────┘  └────────────┘  └─────────────┘
```

### Потребление ресурсов на RPi 4 (8GB)

| Компонент | RAM | CPU |
|---|---|---|
| PostgreSQL | ~100 MB | ~5% idle |
| Gunicorn (4 workers) | ~200 MB | ~10% при запросах |
| APScheduler + polling | ~150 MB | ~30% при опросе |
| Nginx | ~10 MB | ~1% |
| Telegram bot | ~30 MB | ~1% |
| **Итого** | **~500 MB** | **~50% peak** |
| **Свободно** | **~7.1 GB** | **~50%** |

---

## Порядок реализации (рекомендуемый)

| # | Фаза | Время | Зависимости |
|---|---|---|---|
| 0 | Инфраструктура RPi | 1-2 дня | — |
| 1 | Динамические маршруты | 2-3 дня | Фаза 0 |
| 2 | Умный планировщик | 1-2 дня | Фаза 1 |
| 3 | Новый UI | 3-5 дней | Фаза 1 |
| 4 | Оптимизация | 1-2 дня | Фаза 3 |
| 5 | Пользователи | 3-5 дней | Фаза 3 |
| 6 | Telegram-бот | 2-3 дня | Фаза 5 |
| 7 | SEO + монетизация | 2-3 дня | Фаза 3 |
| 8 | Международные | 1-2 дня | Фаза 2 |

**Общее время: ~3-4 недели** при активной разработке.

---

## Стек обновлений (requirements.txt)

```
Flask==3.1.0
Flask-SQLAlchemy==3.1.1
APScheduler==3.10.4
requests==2.32.3
python-dotenv==1.0.1
python-dateutil==2.9.0
psycopg2-binary==2.9.9      # PostgreSQL драйвер
gunicorn==22.0.0             # Production WSGI сервер
python-telegram-bot==21.0    # Telegram бот (для Фазы 6)
```

---

## Ключевые метрики для отслеживания

| Метрика | Как мерить | Цель |
|---|---|---|
| Время опроса всех маршрутов | Логи price_tracker | < 10 мин |
| Время ответа страницы | Nginx access.log | < 200ms |
| Конверсия в клики "Купить" | Travelpayouts dashboard | > 5% |
| Доход от партнёрки | Travelpayouts dashboard | > 0 после Фазы 7 |
| Уникальных посетителей/день | Nginx logs / Яндекс.Метрика | 2000-5000 |
| Подписчиков Telegram-бота | БД | растёт |

---

*План создан: 2026-02-12*
*Автор: Claude + @s1dus*

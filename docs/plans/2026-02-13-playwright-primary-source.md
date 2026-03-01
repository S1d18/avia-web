# Playwright как основной источник данных

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Перевести систему на Playwright как основной (и единственный надёжный) источник цен, рейсов, багажа и остатка билетов. Data API оставить только для партнёрских deeplink-ссылок.

**Architecture:** ПК с Chrome парсит aviasales.ru каждые 10 минут через Playwright, отправляет данные на RPi. RPi хранит всё в SQLite, показывает на сайте. Data API (PFD) запускается раз в сутки только для обогащения партнёрскими deeplink-ссылками (поле `link` с `t=` параметром). `price_update_poll` убирается полностью. `discovery_poll` заменяется на `link_poll` (только PFD, без SBPR).

**Tech Stack:** Flask, SQLAlchemy, Playwright, APScheduler, requests

---

## Обоснование решений

### Почему Playwright — primary source?
- **Точные цены** — реальные цены со страницы поиска, а не кэш API
- **Все рейсы** — не ограничен "1 самый дешёвый на дату на авиакомпанию"
- **Багаж** — `baggage_count`, `baggage_weight` (API не даёт)
- **Тарифы** — `fare_name` (Лайт, Стандарт, Бизнес)
- **Остаток билетов** — `seats_available` ("Осталось 6 билетов по этой цене")
- **Самолёт** — `equipment` (Boeing 737, Airbus A320)
- **Доступность** — если Playwright не видит рейс, значит он реально отсутствует → можно зачёркивать

### Почему убираем price_update_poll?
- SBPR возвращает 1 cheapest на дату на авиакомпанию — нельзя точно сопоставить с конкретным рейсом
- Нет `flight_number`, нет разделения тарифов, цены прыгают
- Playwright даёт те же данные, но точнее и чаще (каждые 10 мин)

### Как работают партнёрские ссылки?
```
Кнопка "Купить" → tp.media/r?marker=548874&p=4114&u=aviasales.ru/search/LED1402CEK1
  → tp.media ставит cookie + перенаправляет на aviasales
  → пользователь покупает → комиссия
```
**Любой URL на aviasales через tp.media даёт комиссию** — не нужен точный `t=` параметр.
Простой search URL `/search/LED1402CEK1` уже работает.
PFD deeplink (`t=DP1771025700...`) — бонус для UX (пользователь сразу видит конкретный рейс).

### is_available и зачёркивание
Playwright — единственный надёжный способ определить доступность:
- Рейс есть в результатах → `is_available = True`
- Рейса нет → `is_available = False` → зачёркиваем на сайте
- Data API нельзя доверять (кэш, лимит 1 на дату)

---

## Новая схема

```
ПК (каждые 10 мин)                      Малинка (сервер)
──────────────────                       ──────────────────
Playwright → Chrome                      POST /api/scrape/import
  ↓ все рейсы                              ↓ upsert Flight
  ↓ цены, багаж, тарифы                   ↓ PriceHistory
  ↓ seats_available                        ↓ is_available
  ↓ equipment                              ↓
  POST → avia-ai.ru ──────────────────→  БД (Flight)

                                         PFD раз в день (00:00)
                                           ↓ обновляет link поле
                                           ↓ (deeplink для "Купить")

                                         Сайт: цены, багаж,
                                         "Осталось X", зачёркнутые,
                                         "Купить" → tp.media
```

---

## Task 1: Расширить parse_results_chunk — извлечь seats_available и arrival_unix

**Files:**
- Modify: `app/services/parse_playwright.py:96-138`

**Step 1: Добавить seats_available в extraction loop**

В функции `parse_results_chunk`, внутри цикла `for proposal in ticket.get('proposals', [])`:

```python
# После строки baggage_weight = baggage.get('weight')
seats_available = ft.get('seats_available')
```

И добавить в dict каждого price:
```python
prices.append({
    'price': int(price_val),
    'baggage_count': baggage_count,
    'baggage_weight': baggage_weight,
    'fare_name': fare_name,
    'agent_id': agent_id,
    'carrier_code': carrier_code,
    'flight_number': carrier_number,
    'seats_available': seats_available,     # NEW
})
```

**Step 2: Добавить arrival_unix в результат рейса**

В основном теле цикла `for ticket in tickets`, после `dep_unix`:

Поле `arr_unix` уже извлекается (строка 84), просто добавить в результат:

```python
results.append({
    'origin': origin,
    'destination': destination,
    'operating_carrier': operating_carrier,
    'operating_number': operating_number,
    'depart_date': depart_date,
    'depart_time_local': depart_time,
    'arrive_time_local': arrive_time,
    'departure_unix': dep_unix,
    'arrival_unix': arr_unix,           # NEW — нужен для deeplink
    'duration_min': duration_min,
    'equipment': equipment,
    'prices': prices,
})
```

**Step 3: Проверить что парсинг работает**

Run: `python _test_scrape.py` (2-3 дня, LED->CEK)
Expected: в выводе видны seats_available и arrival_unix

---

## Task 2: Расширить модель Flight — новые колонки

**Files:**
- Modify: `app/models.py:5-35`

**Step 1: Добавить колонки**

```python
class Flight(db.Model):
    # ... existing fields ...

    # New fields from Playwright
    baggage_count = db.Column(db.Integer)          # кол-во мест багажа (0 = без багажа)
    baggage_weight = db.Column(db.Integer)         # вес багажа (кг)
    fare_name = db.Column(db.String(100))          # название тарифа (Лайт, Стандарт)
    seats_available = db.Column(db.Integer)         # "Осталось X билетов"
    equipment = db.Column(db.String(100))           # тип самолёта (Boeing 737-800)
    arrive_time_local = db.Column(db.String(5))     # HH:MM local время прилёта
```

**Step 2: Применить миграцию**

SQLite + `db.create_all()` не добавляет колонки в существующие таблицы.
Нужно добавить ALTER TABLE в `app/__init__.py`:

```python
# After db.create_all()
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
        db.session.execute(text(f'ALTER TABLE flights ADD COLUMN {col_name} {col_type}'))
db.session.commit()
```

**Step 3: Проверить что приложение запускается**

Run: `python main.py` — должно запуститься без ошибок, новые колонки появятся в БД.

---

## Task 3: Обновить scrape_and_send.py — отправлять новые поля

**Files:**
- Modify: `scrape_and_send.py:45-100` (transform_flights)

**Step 1: Добавить новые поля в transform**

В функции `transform_flights`, для каждого рейса извлечь данные из cheapest price:

```python
# После cheapest_price
cheapest = f['prices'][0] if f.get('prices') else {}
cheapest_price = cheapest.get('price', 0)
baggage_count = cheapest.get('baggage_count')
baggage_weight = cheapest.get('baggage_weight')
fare_name = cheapest.get('fare_name', '')
seats_available = cheapest.get('seats_available')

# В flights.append({...})
flights.append({
    ...
    'price': cheapest_price,
    'baggage_count': baggage_count,
    'baggage_weight': baggage_weight,
    'fare_name': fare_name,
    'seats_available': seats_available,
    'equipment': f.get('equipment', ''),
    'arrive_time_local': f.get('arrive_time_local', ''),
    'arrival_unix': f.get('arrival_unix', 0),
    ...
})
```

**Step 2: Построить deeplink вместо простого search URL**

Если есть arrival_unix, можно построить deeplink с `t=` параметром:

```python
dep_unix = f.get('departure_unix', 0)
arr_unix = f.get('arrival_unix', 0)
airline = f['operating_carrier']
origin = f['origin']
dest = f['destination']

if dep_unix and arr_unix:
    route_code = f'{origin}{dest}'
    t_param = f'{airline}{dep_unix}{arr_unix}000001{route_code}'
    link = f'/search/{origin}{d.day:02d}{d.month:02d}{dest}1?t={t_param}'
else:
    link = f'/search/{origin}{d.day:02d}{d.month:02d}{dest}1'
```

> **Примечание:** формат `t=` параметра может быть неточным (среднее поле `000001` —
> гипотеза). Если deeplink не работает, откатиться на простой search URL.
> Простой search URL через tp.media УЖЕ даёт комиссию.

---

## Task 4: Обновить scrape_routes.py — принимать и сохранять новые поля

**Files:**
- Modify: `app/routes/scrape_routes.py:98-178`

**Step 1: Извлечь новые поля в _upsert_scraped_flight**

```python
def _upsert_scraped_flight(item, now, stats):
    # ... existing field extraction ...
    baggage_count = item.get('baggage_count')
    baggage_weight = item.get('baggage_weight')
    fare_name = item.get('fare_name', '')
    seats_available = item.get('seats_available')
    equipment = item.get('equipment', '')
    arrive_time_local = item.get('arrive_time_local', '')
```

**Step 2: Обновлять поля при upsert**

В блоке `if existing:` (update):
```python
    existing.baggage_count = baggage_count
    existing.baggage_weight = baggage_weight
    existing.fare_name = fare_name or existing.fare_name
    existing.seats_available = seats_available
    existing.equipment = equipment or existing.equipment
    existing.arrive_time_local = arrive_time_local or existing.arrive_time_local
```

В блоке `else:` (create):
```python
    flight = Flight(
        ...
        baggage_count=baggage_count,
        baggage_weight=baggage_weight,
        fare_name=fare_name,
        seats_available=seats_available,
        equipment=equipment,
        arrive_time_local=arrive_time_local,
    )
```

---

## Task 5: Заменить price_update_poll на link_poll

**Files:**
- Modify: `app/services/price_tracker.py`
- Modify: `app/services/scheduler.py`
- Modify: `config.py`

**Step 1: Создать link_poll в price_tracker.py**

Новый метод — только PFD, только обновление `link` поля:

```python
def link_poll(self):
    """Daily affiliate link update: PFD only, update link field for existing flights."""
    logger.info('Starting link poll (PFD for affiliate links)...')
    with self.app.app_context():
        for origin, dest in ROUTES:
            self._update_links(origin, dest)
        self.last_update = datetime.now(timezone.utc)
    logger.info('Link poll complete.')

def _update_links(self, origin, destination):
    """Fetch PFD and update link field for matching flights in DB."""
    today = date.today()

    for m_offset in range(3):
        month = today.month + m_offset
        year = today.year
        if month > 12:
            month -= 12
            year += 1
        month_str = f'{year}-{month:02d}'

        time.sleep(0.2)
        pfd_tickets = self.client.prices_for_dates(origin, destination, month_str)

        for t in pfd_tickets:
            if t.get('transfers', 0) > 0:
                continue
            airline_code = t.get('airline', '')
            dep_at = t.get('departure_at', '')
            link = t.get('link', '')
            if not airline_code or not dep_at or not link:
                continue

            try:
                dt = isoparse(dep_at)
                dt_utc = dt.astimezone(timezone.utc)
                depart_time = dt_utc.strftime('%H:%M')
                depart_date = dt.date()
            except (ValueError, TypeError):
                continue

            # Find matching flight and update link
            flight = Flight.query.filter_by(
                origin=origin,
                destination=destination,
                depart_date=depart_date,
                airline=airline_code,
                depart_time=depart_time,
            ).first()

            if flight and link:
                flight.link = link

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception('Link update commit failed')

    logger.info('Links updated for %s->%s', origin, destination)
```

**Step 2: Удалить price_update_poll из scheduler.py**

Убрать job `price_update` и добавить `link_poll`:

```python
# УБРАТЬ:
# scheduler.add_job(tracker.price_update_poll, 'interval',
#                   minutes=app.config['POLL_INTERVAL_MINUTES'], ...)

# ДОБАВИТЬ:
scheduler.add_job(tracker.link_poll, 'cron',
                  hour=0, minute=0,
                  id='link_poll', replace_existing=True)
```

**Step 3: Убрать discovery_poll или сделать его опциональным**

Discovery_poll тоже можно убрать (Playwright находит все рейсы). Оставить только `link_poll` раз в сутки и `update_airlines` раз в 24ч.

Или: оставить discovery_poll как fallback на случай если ПК не работает, но запускать раз в сутки:

```python
scheduler.add_job(tracker.discovery_poll, 'cron',
                  hour=0, minute=30,
                  id='discovery_poll', replace_existing=True)
```

**Step 4: Обновить config.py**

```python
# Убрать: POLL_INTERVAL_MINUTES = 3 (больше не нужен)
# Убрать: UPDATE_PRICE_PADDING = 200 (больше не нужен)
# Оставить: DISCOVERY_INTERVAL_MINUTES (для fallback)
LINK_POLL_ENABLED = True   # включить обновление affiliate ссылок
```

---

## Task 6: Обновить is_available логику по данным Playwright

**Files:**
- Modify: `app/routes/scrape_routes.py`

**Step 1: Добавить обработку is_available в import endpoint**

После upsert всех рейсов, пометить недоступными те рейсы, которых Playwright не прислал:

```python
@scrape_bp.route('/api/scrape/import', methods=['POST'])
def scrape_import():
    # ... existing code ...

    # После основного цикла upsert:
    # Собрать ключи всех присланных рейсов
    seen_keys = set()
    for item in flights_data:
        key = (item.get('origin',''), item.get('destination',''),
               item.get('depart_date',''), item.get('airline',''),
               item.get('depart_time',''))
        if all(key):
            seen_keys.add(key)

    # Пометить unavailable рейсы на те даты, которые были просканированы
    scanned_dates = set()
    for item in flights_data:
        d = item.get('depart_date', '')
        o = item.get('origin', '')
        dest = item.get('destination', '')
        if d and o and dest:
            scanned_dates.add((o, dest, d))

    marked_unavailable = 0
    for (o, dest, d) in scanned_dates:
        flights_on_date = Flight.query.filter_by(
            origin=o, destination=dest,
            depart_date=date.fromisoformat(d),
            is_available=True,
        ).all()
        for f in flights_on_date:
            key = (f.origin, f.destination, f.depart_date.isoformat(),
                   f.airline, f.depart_time)
            if key not in seen_keys:
                f.is_available = False
                marked_unavailable += 1

    stats['marked_unavailable'] = marked_unavailable
```

---

## Task 7: Обновить API calendar — отдавать новые поля

**Files:**
- Modify: `app/routes/main_routes.py:126-138`

**Step 1: Добавить новые поля в flight_data dict**

```python
flight_data = {
    'airline': f.airline,
    'airline_name': airline_name,
    'airline_logo': f'http://pics.avs.io/36/36/{f.airline}.png',
    'flight_number': f.flight_number or '',
    'price': f.price,
    'departure_at': f.departure_at or '',
    'duration': f.duration,
    'transfers': 0,
    'booking_url': build_booking_url(f.link),
    'price_history': history,
    'is_available': f.is_available,
    # New fields:
    'baggage_count': f.baggage_count,
    'baggage_weight': f.baggage_weight,
    'fare_name': f.fare_name or '',
    'seats_available': f.seats_available,
    'equipment': f.equipment or '',
    'arrive_time_local': f.arrive_time_local or '',
}
```

---

## Task 8: Обновить фронтенд — показать багаж, остаток, зачёркивание

**Files:**
- Modify: `app/templates/calendar.html` (или соответствующий JS)

**Step 1: Иконка багажа**

```html
<!-- Если baggage_count > 0 -->
<span class="baggage-badge" title="Багаж: {{ baggage_weight }}кг">
  🧳 {{ baggage_count }}×{{ baggage_weight }}кг
</span>
<!-- Если baggage_count == 0 -->
<span class="no-baggage-badge" title="Без багажа">
  Без багажа
</span>
```

**Step 2: Остаток билетов**

```html
<!-- Если seats_available <= 5 -->
<span class="seats-warning">
  Осталось {{ seats_available }} билетов
</span>
```

**Step 3: Зачёркивание недоступных**

```css
.flight-card.unavailable {
    opacity: 0.5;
    text-decoration: line-through;
}
```

```html
<div class="flight-card {% if not is_available %}unavailable{% endif %}">
```

**Step 4: Тип самолёта**

```html
<span class="equipment-info">{{ equipment }}</span>
```

---

## Task 9: Деплой на малинку

**Step 1: Скопировать обновлённые файлы**

```bash
scp app/models.py app/__init__.py app/services/parse_playwright.py \
    app/services/price_tracker.py app/services/scheduler.py \
    app/routes/scrape_routes.py app/routes/main_routes.py \
    config.py s1d18@192.168.50.13:~/avia_web/
```

**Step 2: Перезапустить сервис**

```bash
ssh s1d18@192.168.50.13 'sudo systemctl restart avia-web'
```

**Step 3: Проверить что миграция прошла**

```bash
ssh s1d18@192.168.50.13 'cd ~/avia_web && venv/bin/python -c "
from app import create_app; app = create_app()
with app.app_context():
    from sqlalchemy import text
    from app.database import db
    r = db.session.execute(text(\"PRAGMA table_info(flights)\")).fetchall()
    for col in r: print(col)
"'
```

Expected: колонки baggage_count, seats_available, equipment и т.д.

**Step 4: Тест end-to-end с ПК**

```bash
python scrape_and_send.py --days 2 --routes LED-CEK
```

Expected: Server response includes created/updated counts, новые поля заполнены.

---

## Порядок реализации

1. Task 1 — parse_playwright.py (seats_available, arrival_unix)
2. Task 2 — models.py + миграция (новые колонки)
3. Task 3 — scrape_and_send.py (отправка новых полей)
4. Task 4 — scrape_routes.py (приём и сохранение)
5. Task 5 — scheduler + price_tracker (link_poll, убрать price_update)
6. Task 6 — is_available логика (зачёркивание)
7. Task 7 — main_routes.py (API отдаёт новые поля)
8. Task 8 — фронтенд (багаж, остаток, зачёркивание, самолёт)
9. Task 9 — деплой и тест

---

## Верификация

- [ ] `seats_available` появляется в парсинге Playwright
- [ ] Новые колонки в БД (baggage_count, seats_available, equipment, etc.)
- [ ] scrape_and_send.py отправляет все поля
- [ ] Эндпоинт принимает и сохраняет
- [ ] price_update_poll удалён, link_poll работает в 00:00
- [ ] is_available=False для рейсов не найденных Playwright'ом
- [ ] Фронтенд показывает: багаж, "Осталось X", зачёркнутые, самолёт
- [ ] Кнопка "Купить" → tp.media → комиссия

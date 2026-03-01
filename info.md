# Avia Web — Flight Price Tracker

Мониторинг цен на авиабилеты LED (Санкт-Петербург) <-> CEK (Челябинск), прямые рейсы.

**Сайт:** https://avia-ai.ru
**Стек:** Flask 3.1 + SQLAlchemy + APScheduler + Jinja2 + Vanilla JS

---

## Архитектура

Два компонента:

1. **Веб-сервер (RPi)** — Flask-приложение, хранит данные в SQLite, отдаёт сайт.
2. **Скрейпер (ПК)** — Playwright парсит aviasales.ru, отправляет данные на сервер через API.

```
  ПК (Windows)                       RPi (Raspberry Pi 4)
  ┌─────────────────┐               ┌──────────────────────┐
  │ scrape_and_send  │──POST /api──>│ Flask (gunicorn:6000) │
  │ + Playwright     │  /scrape/    │ + SQLite + APScheduler│
  │ + Chrome         │  import      │ + Cloudflare Tunnel   │
  └─────────────────┘               └──────────────────────┘
```

### Сервер (RPi)
- `main.py` — точка входа, Flask dev server (localhost:5000)
- `gunicorn_conf.py` — production: gunicorn на порту 6000
- `app/__init__.py` — фабрика приложения, миграции SQLite
- `app/models.py` — модели: Flight, PriceHistory, Airline
- `app/routes/main_routes.py` — страницы + JSON API для фронтенда
- `app/routes/scrape_routes.py` — POST /api/scrape/import (приём данных от скрейпера)
- `app/services/price_tracker.py` — link_poll (ежедневно, PFD для affiliate-ссылок), update_airlines
- `app/services/api_client.py` — Travelpayouts Data API клиент
- `app/services/scheduler.py` — APScheduler: link_poll в 00:00, airlines каждые 24ч
- `app/services/link_builder.py` — формирование affiliate-ссылок (tp.media)
- `app/services/parse_playwright.py` — парсер aviasales через Playwright
- `app/static/` — CSS + JS фронтенд
- `app/templates/` — Jinja2 шаблоны (index.html, calendar.html, base.html)

### Скрейпер (ПК)
- `scrape_and_send.py` — главный скрипт: парсит → трансформирует → POST на сервер
- `scraper_setup.bat` — первичная настройка на новой машине (venv, pip, playwright)
- `scraper_run.bat` — запуск цикла парсинга (30 дней, каждые 30 мин)
- `.env.example` — шаблон переменных окружения

---

## Переменные окружения (.env)

```
AVIA_API=your_travelpayouts_api_token
AVIA_ID=548874
SCRAPE_API_KEY=shared_secret_for_scraper_auth
SCRAPE_API_URL=https://avia-ai.ru
SCRAPE_PROXIES=,http://user:pass@proxy1:port,http://user:pass@proxy2:port
```

- `AVIA_API` — токен Travelpayouts для Data API (link_poll, airlines)
- `SCRAPE_API_KEY` — ключ авторизации скрейпера (должен совпадать на ПК и сервере)
- `SCRAPE_PROXIES` — ротация прокси для Playwright (пустой = direct, через запятую)

---

## База данных (SQLite)

`instance/avia_tracker.db`

### Таблица flights
Уникальный ключ: `(origin, destination, depart_date, airline, depart_time)`

| Поле | Тип | Описание |
|------|-----|----------|
| origin | String(3) | IATA код откуда (LED) |
| destination | String(3) | IATA код куда (CEK) |
| depart_date | Date | Дата вылета |
| airline | String(10) | IATA код авиакомпании (DP, SU, N4) |
| depart_time | String(5) | Время вылета HH:MM UTC |
| flight_number | String(20) | Номер рейса |
| price | Integer | Цена в рублях (cheapest без багажа) |
| departure_at | String(50) | ISO datetime |
| duration | Integer | Длительность в минутах |
| link | Text | Affiliate-ссылка (заполняется PFD) |
| is_available | Boolean | Рейс доступен (False = исчез при последнем сканировании) |
| baggage_count | Integer | Количество мест багажа (0 = без багажа) |
| baggage_weight | Integer | Вес багажа в кг |
| fare_name | String(100) | Название тарифа (Лайт, Стандарт) |
| seats_available | Integer | Осталось билетов по этой цене |
| equipment | String(100) | Тип самолёта (Boeing 737-800) |
| arrive_time_local | String(5) | Время прилёта HH:MM локальное |

### Таблица price_history
| Поле | Тип | Описание |
|------|-----|----------|
| flight_id | FK -> flights | |
| old_price | Integer | Старая цена |
| new_price | Integer | Новая цена |
| changed_at | DateTime | Время изменения |

Порог записи в историю: разница >= 20 руб.

### Таблица airlines
| Поле | Тип | Описание |
|------|-----|----------|
| iata_code | String(10) PK | Код (DP, SU, N4) |
| name_ru | String(200) | Название на русском |
| name_en | String(200) | Название на английском |
| is_lowcost | Boolean | Лоукостер |

---

## Playwright парсер

Файл: `app/services/parse_playwright.py`

- Открывает aviasales.ru в Chrome (system Chrome на Windows, Chromium на Linux)
- 5 вкладок параллельно (BATCH_SIZE=5)
- Перехватывает JSON ответы `v3.2/results`
- Блокирует тяжёлые ресурсы (картинки, шрифты, аналитика)
- Persistent Chrome profile (`_chrome_profile/`) для сохранения cookies
- Авто-определение captcha (abort если нет данных вообще)
- На Linux без дисплея: Xvfb через pyvirtualdisplay

Тайминги:
- Батч: до 35 сек, обычно 9-12 сек
- Между батчами: 8 сек
- Между маршрутами: 30 сек
- 30 дней × 2 направления = ~5 мин на цикл

---

## Деплой на Raspberry Pi

- **Хост:** raspbot (192.168.50.13), Debian 13, Python 3.13, 8GB RAM
- **Пользователь:** s1d18
- **Проект:** ~/avia_web/ с venv
- **Gunicorn:** порт 6000 (порт 5000 занят crypto_parser)
- **Домен:** avia-ai.ru (Reg.ru -> Cloudflare NS)
- **Cloudflare Tunnel:** `avia` (ID: b2799bfb-ae32-4790-b54f-8e3cf27b5381)
- **Systemd:** `avia-web` (gunicorn), `cloudflared` (tunnel)

Провайдер блокирует длительные HTTP/2 к Cloudflare — решение: системный прокси на малинке.

```bash
# Перезапуск сервиса
ssh s1d18@192.168.50.13 "sudo systemctl restart avia-web"

# Обновить код
scp -r app/ s1d18@192.168.50.13:~/avia_web/app/

# Логи
ssh s1d18@192.168.50.13 "journalctl -u avia-web -f"
```

---

## Запуск скрейпера на другой машине

1. Скопировать проект на ПК
2. Создать `.env` из `.env.example`, заполнить `SCRAPE_API_KEY`
3. Запустить `scraper_setup.bat` (один раз)
4. Запустить `scraper_run.bat` (для работы)
5. Для автозагрузки: ярлык `scraper_run.bat` в `shell:startup`

---

## API (Travelpayouts Data API)

Используется для:
- **PFD** (`/v3/prices_for_dates`) — affiliate-ссылки (link_poll, раз в сутки)
- **Airlines** (`/data/ru/airlines.json`) — справочник авиакомпаний

Лимиты: 600 запросов/мин на эндпоинт.

Affiliate-ссылки: `https://tp.media/r?marker=548874&p=4114&u=<encoded_aviasales_url>`

---

## Структура проекта (после очистки)

```
avia_web/
├── main.py                  # Entry point (dev server)
├── config.py                # Config class
├── gunicorn_conf.py         # Production WSGI config
├── requirements.txt         # Python dependencies
├── scrape_and_send.py       # Standalone scraper script
├── scraper_setup.bat        # Setup for new PC
├── scraper_run.bat          # Run scraper loop
├── .env                     # Secrets (not in git)
├── .env.example             # Template
├── info.md                  # This file
├── app/
│   ├── __init__.py          # App factory + migrations
│   ├── database.py          # SQLAlchemy db instance
│   ├── models.py            # Flight, PriceHistory, Airline
│   ├── routes/
│   │   ├── main_routes.py   # Web pages + JSON API
│   │   └── scrape_routes.py # POST /api/scrape/import
│   ├── services/
│   │   ├── api_client.py    # Travelpayouts API client
│   │   ├── link_builder.py  # Affiliate URL builder
│   │   ├── parse_playwright.py  # Aviasales scraper
│   │   ├── price_tracker.py # link_poll, update_airlines
│   │   └── scheduler.py     # APScheduler config
│   ├── static/
│   │   ├── css/style.css
│   │   └── js/app.js
│   └── templates/
│       ├── base.html
│       ├── index.html
│       └── calendar.html
├── instance/
│   └── avia_tracker.db      # SQLite database
├── tests/
├── docs/                    # API docs, планы
├── future/                  # План масштабирования на всю Россию
└── _chrome_profile/         # Persistent Chrome profile (cookies)
```

---

## Известные особенности

- **Капча aviasales:** Срабатывает после ~180 вкладок за 15 мин. Кулдаун 1-2 часа. Не зависит от IP.
- **seats_available:** Показываем бейдж "Осталось X бил." только при <= 5. Значение 9 означает "9 и более".
- **is_available:** Если Playwright просканировал дату, но не нашёл рейс — помечаем False.
- **Цена:** Берём cheapest тариф без багажа (baggage_count == 0).
- **Chrome profile:** Отдельный профиль на каждый прокси (хэш от адреса прокси в имени папки).
- **WAL mode:** SQLite в WAL для безопасного параллельного доступа.

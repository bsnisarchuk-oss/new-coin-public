# TokenListings — CEX Listing Tracker Bot

[![CI](https://github.com/bsnisarchuk-oss/new-coin/actions/workflows/ci.yml/badge.svg)](https://github.com/bsnisarchuk-oss/new-coin/actions/workflows/ci.yml)

Telegram-бот для мониторинга новых листингов криптовалют на крупнейших биржах.
Уведомляет в реальном времени, поддерживает фильтры, watchlist, ценовые алерты и дайджесты.

---

## Возможности

- **5 бирж**: Binance, Bybit, OKX, MEXC, Coinbase
- **Типы рынков**: Spot и Futures (Perpetual)
- **Детект делистингов** — уведомление при удалении пары с биржи
- **Скоринг листингов** (0–100) с risk-флагами:
  - `NO_USDT_PAIR` — нет пары с USDT
  - `LOW_LIQUIDITY` — низкая ликвидность
  - `HIGH_SPREAD` — высокий спред
- **Обогащение данных**: текущая цена, объём за 5 минут, спред
- **Сравнение цен (арбитраж)** — при листинге показывает цену монеты на всех биржах где она торгуется, выделяет самую дешёвую/дорогую и арбитражный спред
- **CoinGecko-блок** — описание монеты, год запуска, ссылка на сайт прямо в уведомлении
- **Дедупликация** — одно событие не придёт дважды в течение N часов
- **Post-listing трекинг** — отчёты через 15 минут, 1 час, 4 часа и 24 часа
- **Watchlist** — приоритетные уведомления по выбранным тикерам
- **Ценовые алерты** — уведомление при достижении цены
- **Дайджест-режим** — сводка раз в час вместо мгновенных уведомлений
- **Пресеты фильтров** — сохранение и загрузка настроек
- **Rate limiting** — защита от спама (20 команд/минуту на пользователя)
- **Мониторинг** — уведомление администратору при сбоях

---

## Стек

| Компонент | Технология |
|-----------|-----------|
| Язык | Python 3.11+ |
| Telegram | aiogram 3 |
| БД | PostgreSQL 16 + SQLAlchemy async |
| Миграции | Alembic (auto-apply при старте) |
| Планировщик | APScheduler |
| HTTP | aiohttp |
| Контейнеры | Docker + Docker Compose |

---

## Быстрый старт (Deploy in 10 min)

### Требования

| Инструмент | Версия |
|-----------|--------|
| Docker | 24+ |
| Docker Compose | v2 (`docker compose`, не `docker-compose`) |
| Telegram Bot Token | от [@BotFather](https://t.me/BotFather) |

Проверить версии:
```bash
docker --version        # Docker version 24.x.x
docker compose version  # Docker Compose version v2.x.x
```

### Шаг 1 — Клонировать репозиторий

```bash
git clone https://github.com/bsnisarchuk-oss/new-coin.git
cd new-coin
```

### Шаг 2 — Создать `.env`

```bash
cp .env.example .env
```

Открыть `.env` и заполнить **обязательные** поля:

```env
BOT_TOKEN=1234567890:ABCdef...   # Токен от @BotFather
ADMIN_ID=123456789               # Ваш Telegram ID (узнать: @userinfobot)
POSTGRES_PASSWORD=change_me      # Пароль БД для docker compose
```

Остальные настройки можно оставить по умолчанию.

### Шаг 3 — Запустить

```bash
docker compose up --build -d
```

Это автоматически:
1. Поднимет PostgreSQL
2. Применит миграции Alembic
3. Запустит бота в polling-режиме

### Шаг 4 — Проверить что бот работает

```bash
# Смотреть логи в реальном времени
docker compose logs -f bot

# Убедиться что оба контейнера healthy
docker compose ps
```

Ожидаемый вывод в логах:
```
INFO  Bot started. Polling...
INFO  Bootstrap snapshots for binance/spot with 2145 instruments
INFO  Bootstrap snapshots for bybit/spot with 876 instruments
...
```

После bootstrap-а бот готов к работе. Откройте Telegram, напишите боту `/start`.

> Для локальной разработки используйте отдельный dev compose:
> `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build`

---

## Вариант 2 — Локальный запуск (разработка)

**Требования:** Python 3.11+, PostgreSQL 16

```bash
# 1. Установить зависимости
pip install -e ".[dev]"

# 2. Поднять только базу данных
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres

# 3. Скопировать и заполнить .env
cp .env.example .env
# Для локального запуска поправить DATABASE_URL на localhost

# 4. Запустить бота (миграции применятся автоматически)
python -m app.main
```

---

## Настройка (.env)

```env
# ── Обязательно ──────────────────────────────────────────────
BOT_TOKEN=YOUR_BOT_TOKEN_HERE   # Токен от @BotFather

# ── База данных ───────────────────────────────────────────────
POSTGRES_DB=new_coin_bot
POSTGRES_USER=new_coin_bot
POSTGRES_PASSWORD=change_me
# Для docker compose оставить как есть:
DATABASE_URL=postgresql+asyncpg://new_coin_bot:change_me@postgres:5432/new_coin_bot
# Для локального запуска:
# DATABASE_URL=postgresql+asyncpg://new_coin_bot:change_me@localhost:5432/new_coin_bot

# ── Мониторинг ────────────────────────────────────────────────
# Узнать свой ID: написать @userinfobot в Telegram
ADMIN_ID=123456789

# ── Интервалы ─────────────────────────────────────────────────
POLL_INTERVAL_SEC=60            # Как часто опрашивать биржи (секунды)
DEDUP_TTL_HOURS=24              # Окно дедупликации (часы)
MAX_NOTIFICATIONS_PER_HOUR=20  # Лимит уведомлений на пользователя в час

# ── Фильтры по умолчанию для новых пользователей ─────────────
DEFAULT_ENABLED_EXCHANGES=binance,bybit,coinbase,okx,mexc
DEFAULT_ENABLED_MARKET_TYPES=spot,futures
DEFAULT_ONLY_USDT=false
DEFAULT_MIN_SCORE=0

# ── Пороги для risk-флагов ────────────────────────────────────
MIN_VOL_5M=10000                # Минимальный объём за 5 минут (USD)
MAX_SPREAD=0.02                 # Максимальный спред (2%)

# ── Логи ──────────────────────────────────────────────────────
LOG_FORMAT=text                 # "text" (human) или "json" (для Loki/Grafana)

# ── Monitoring endpoints ──────────────────────────────────────
METRICS_PORT=9090               # 0 = отключить metrics server
HEALTH_PORT=8080
```

---

## Команды бота

### Основные
| Команда | Описание |
|---------|---------|
| `/start` | Регистрация + онбординг (выбор бирж, типов рынка, режима) |
| `/help` | Список всех команд |
| `/status` | Текущие фильтры и статистика листингов |

### Фильтры
| Команда | Описание |
|---------|---------|
| `/filters` | Показать текущие настройки (inline-клавиатура) |
| `/filters exchange <биржа> on\|off` | Включить/выключить биржу |
| `/filters market spot\|futures on\|off` | Включить/выключить тип рынка |
| `/filters only_usdt on\|off` | Только пары с USDT |
| `/filters min_score <0..100>` | Минимальный скор листинга |

Доступные биржи: `binance`, `bybit`, `coinbase`, `okx`, `mexc`

### Watchlist
| Команда | Описание |
|---------|---------|
| `/watch BTC` | Добавить тикер (уведомление всегда, независимо от фильтров) |
| `/watchlist` | Показать список (лимит 50 тикеров) |
| `/unwatch BTC` | Удалить тикер |

### Управление уведомлениями
| Команда | Описание |
|---------|---------|
| `/pause 30m` | Пауза на 30 минут |
| `/pause 2h` | Пауза на 2 часа |
| `/pause 1d` | Пауза на 1 день |
| `/pause` | Снять паузу досрочно |
| `/digest on\|off` | Дайджест раз в час вместо мгновенных |

### История и аналитика
| Команда | Описание |
|---------|---------|
| `/history` | Последние листинги с пагинацией |
| `/history <exchange>` | История листингов по конкретной бирже |
| `/analytics` | Статистика по биржам |

### Ценовые алерты
| Команда | Описание |
|---------|---------|
| `/alert BTC > 100000` | Уведомить когда BTC > $100k |
| `/alert ETH < 2000` | Уведомить когда ETH < $2k |
| `/alerts` | Список активных алертов (лимит 10) |
| `/unalert <ID>` | Удалить алерт |

### Пресеты фильтров
| Команда | Описание |
|---------|---------|
| `/preset save <name>` | Сохранить текущие фильтры |
| `/preset load <name>` | Загрузить пресет |
| `/preset list` | Список всех пресетов (лимит 5) |
| `/preset delete <name>` | Удалить пресет |

### Администратор
> Команды доступны только пользователю с `ADMIN_ID` из `.env`.

| Команда | Описание |
|---------|---------|
| `/admin stats` | Статистика: пользователи, события за 24ч |
| `/admin broadcast <текст>` | Рассылка всем пользователям |
| `/admin user <id>` | Настройки и статистика конкретного пользователя |

---

## Как работает детектор

```
Каждые 60 секунд:
  Для каждой биржи и типа рынка:
    1. Запросить текущий список инструментов с биржи
       (3 попытки с exponential backoff: 1s → 2s → 4s)
    2. Сравнить с сохранённым снепшотом в БД
    3. Новые инструменты → событие листинга
    4. Исчезнувшие инструменты → событие делистинга
    5. Обновить снепшот
    6. Разослать уведомления пользователям (с учётом их фильтров)
```

При **первом запуске** бот сохраняет текущий список как точку отсчёта (`BOOTSTRAP_ON_EMPTY=true`) — уведомлений не будет, пока не появятся новые пары.

---

## Скоринг листингов

| Условие | Баллы |
|---------|-------|
| Binance | +35 |
| Bybit | +30 |
| OKX | +25 |
| MEXC | +20 |
| Coinbase | +20 |
| Пара с USDT | +10 |
| `LOW_LIQUIDITY` | −10 |
| `HIGH_SPREAD` | −10 |

Пользователь может выставить `/filters min_score 30` чтобы получать только "качественные" листинги.

---

## APScheduler джобы

| ID | Интервал | Описание |
|----|----------|---------|
| `detector_poll` | 60 сек | Опрос бирж, детект листингов и делистингов |
| `digest_send` | 1 час | Рассылка дайджестов |
| `price_alert_check` | 5 мин | Проверка ценовых алертов |
| `announcement_check` | 10 мин | Мониторинг анонсов бирж (Binance, OKX) |
| `track:{uuid}` | по дате | Отчёт через 15 мин / 1ч / 4ч / 24ч после листинга |

---

## Таблицы БД

| Таблица | Назначение |
|---------|-----------|
| `users` | Пользователи и их настройки (JSONB) |
| `events` | Обнаруженные листинги |
| `deliveries` | Доставленные уведомления (дедупликация) |
| `market_snapshots` | Текущий снепшот инструментов на биржах |
| `watchlist` | Watchlist пользователей |
| `mutes` | Заглушённые биржи/тикеры/ключевые слова |
| `tracking_subscriptions` | Подписки на post-listing трекинг |
| `digest_queue` | Очередь для дайджестов |
| `price_alerts` | Ценовые алерты пользователей |
| `filter_presets` | Сохранённые пресеты фильтров |
| `callback_tokens` | Токены для inline-кнопок |
| `analytics_events` | Аналитика действий пользователей |

---

## Структура проекта

```
app/
├── main.py              # Точка входа
├── config.py            # Настройки из .env
├── bot/
│   ├── dispatcher.py    # Диспетчер, rate limiting middleware
│   ├── callback_data.py # CallbackData классы
│   ├── handlers/        # Обработчики команд
│   └── keyboards/       # Inline-клавиатуры
├── exchanges/
│   ├── base.py          # Абстрактный коннектор
│   ├── binance.py
│   ├── bybit.py
│   ├── coinbase.py
│   ├── okx.py
│   └── mexc.py
├── services/
│   ├── detector.py      # Детектор новых листингов
│   ├── notifier.py      # Рассылка уведомлений
│   ├── tracker.py       # Post-listing трекинг (15m/1h)
│   ├── enrich.py        # Обогащение данными о цене
│   ├── arbitrage.py     # Сравнение цен между биржами
│   ├── coingecko.py     # Метаданные монет (CoinGecko)
│   ├── scoring.py       # Скоринг событий
│   ├── filtering.py     # Фильтрация по настройкам пользователя
│   ├── dedup.py         # Дедупликация уведомлений
│   ├── digest.py        # Дайджест-рассылка
│   ├── price_alerts.py  # Ценовые алерты
│   └── delisting.py     # Уведомления о делистингах
├── db/
│   ├── models.py        # ORM-модели
│   ├── session.py       # Фабрика сессий
│   └── repo/            # Репозитории (CRUD)
└── jobs/
    └── scheduler.py     # APScheduler джобы
alembic/                 # Миграции БД
tests/                   # Unit tests
```

---

## Обновление (Update Guide)

```bash
# 1. Получить изменения
git pull origin master

# 2. Пересобрать и перезапустить
#    Миграции применятся автоматически при старте бота
docker compose up --build -d

# 3. Проверить логи
docker compose logs -f bot
```

> ⚠️ Бот автоматически применяет миграции Alembic при старте. Если миграция упала — бот не запустится (защита от запуска с битой схемой).

> Smoke-test чеклист после обновления: см. `docs/SMOKE_TEST.md`

---

## Бэкап базы данных

```bash
# Создать дамп
docker exec new-coin-postgres-1 pg_dump -U postgres new_coin_bot \
  | gzip > backup_$(date +%Y%m%d_%H%M).sql.gz

# Восстановить из дампа
gunzip -c backup_20260301_1200.sql.gz \
  | docker exec -i new-coin-postgres-1 psql -U postgres new_coin_bot
```

Рекомендуется настроить cron для автоматических бэкапов:
```bash
# Каждый день в 3:00 UTC
0 3 * * * cd /path/to/new-coin && docker exec new-coin-postgres-1 pg_dump -U postgres new_coin_bot | gzip > /backups/backup_$(date +\%Y\%m\%d).sql.gz
```

---

## Troubleshooting

### Бот не запускается

**Ошибка: `BOT_TOKEN is required`**
```bash
# Проверить что .env существует и токен заполнен
cat .env | grep BOT_TOKEN
```

**Ошибка: `could not connect to server` (PostgreSQL)**
```bash
# Убедиться что postgres запущен и healthy
docker compose ps postgres
# Перезапустить postgres
docker compose restart postgres
# Подождать 10 секунд и запустить бота
docker compose restart bot
```

**Ошибка при миграции: `relation already exists`**
```bash
# Alembic пытается создать таблицы повторно — обычно безопасно
# Если блокирует запуск, проверить версию миграций:
docker compose run --rm --no-deps bot python -m alembic current
docker compose run --rm --no-deps bot python -m alembic history
```

### Уведомления не приходят

1. Убедитесь что написали боту `/start`
2. Проверьте настройки: `/filters` и `/status`
3. При первом запуске бот делает bootstrap (сохраняет снепшот) — уведомлений не будет пока не появится новый листинг
4. Проверьте логи на ошибки API бирж:
```bash
docker compose logs bot | grep ERROR
```

### Бот внезапно перестал работать

```bash
# Проверить состояние
docker compose ps

# Посмотреть последние ошибки
docker compose logs --tail=50 bot

# Перезапустить
docker compose restart bot
```

### Много одинаковых уведомлений

Увеличьте `DEDUP_TTL_HOURS` в `.env` (по умолчанию 24 часа):
```env
DEDUP_TTL_HOURS=48
```
Затем перезапустите бота.

---

## Симуляция листинга (для тестирования)

```bash
# Создаёт тестовое событие SIMxxxx/USDT и запускает полную цепочку уведомлений
docker compose run --rm --no-deps bot python -m app.scripts.simulate_event
```

---

## Тесты

```bash
# Установить dev-зависимости
pip install -e ".[dev]"

# Запустить все тесты
pytest tests/ -v

# С покрытием (если установлен pytest-cov)
pytest tests/ --cov=app --cov-report=term-missing
```

Текущий рабочий набор также проверяется через:

```bash
python -m pytest -q -p no:cacheprovider tests
python -m ruff check .
```

---

## Лицензия

MIT — см. [LICENSE](LICENSE)

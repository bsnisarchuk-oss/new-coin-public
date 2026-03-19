# TokenListings — Crypto Listing Tracker Bot

[![CI](https://github.com/bsnisarchuk-oss/new-coin/actions/workflows/ci.yml/badge.svg)](https://github.com/bsnisarchuk-oss/new-coin/actions/workflows/ci.yml)

> A production-ready Telegram bot that detects new cryptocurrency listings and delistings on major exchanges in real time — with enrichment, scoring, post-listing tracking, and per-user filtering.

**[🇷🇺 Русская версия](README_RU.md)**

---

## Overview

New listings on centralized exchanges are often time-sensitive trading opportunities. TokenListings monitors five major CEXes — Binance, Bybit, OKX, MEXC, and Coinbase — polling their instrument lists every 60 seconds. When a new trading pair appears (or disappears), registered users receive an instant Telegram notification enriched with price, volume, spread, cross-exchange price comparison, and CoinGecko metadata.

The bot is designed for traders, analysts, and crypto enthusiasts who want to stay ahead of listing activity without manually checking each exchange. It is fully self-hosted and configurable per user.

---

## Features

### Detection & Coverage
- **5 exchanges**: Binance, Bybit, OKX, MEXC, Coinbase
- **Market types**: Spot and Futures (Perpetual)
- **Delisting detection**: users are notified when a trading pair is removed
- **Bootstrap safety**: on first run, the bot takes a snapshot without firing notifications — only genuinely new listings trigger alerts

### Notification Enrichment
- Current price, 5-minute volume, and bid/ask spread at time of listing
- **Cross-exchange price comparison**: shows the price of the listed token across all exchanges where it already trades, highlighting cheapest/most expensive and the arbitrage spread
- **CoinGecko block**: coin description, launch year, and website link embedded directly in the notification

### Scoring & Filtering
- **Listing score (0–100)** based on exchange reputation, USDT pair presence, liquidity, and spread
- Per-user **minimum score filter** — e.g. `/filters min_score 30` to receive only higher-quality listings
- Risk flags: `NO_USDT_PAIR`, `LOW_LIQUIDITY`, `HIGH_SPREAD`
- Per-user exchange and market type filters, USDT-only toggle

### Post-Listing Tracking
- Automatic follow-up reports at **15 min, 1 h, 4 h, and 24 h** after a listing
- Each report shows price change, volume, and a Unicode sparkline chart

### User Controls
- **Watchlist**: up to 50 tickers that always notify regardless of filters
- **Price alerts**: notify when a token crosses a user-defined price threshold
- **Digest mode**: receive an hourly summary instead of instant notifications
- **Pause**: silence notifications for 30 min / 2 h / 1 day
- **Mutes**: mute specific tickers, exchanges, or keywords
- **Filter presets**: save and load filter configurations by name (up to 5 presets)

### Exchange Announcements
- Monitors Binance and OKX announcement channels every 10 minutes for early listing signals

### Platform & Operations
- **Rate limiting**: 20 commands per minute per user
- **Deduplication**: the same event will not be delivered twice within a configurable window
- **Admin panel**: broadcast messages, view user stats, inspect individual user settings
- **Bilingual**: full Russian and English support (`/lang ru|en`)
- **Analytics**: user action tracking stored in the database
- **Prometheus metrics** endpoint and HTTP health check endpoint

---

## How It Works

```
Every 60 seconds:
  For each exchange × market type:
    1. Fetch the current instrument list from the exchange API
       (3 retries with exponential backoff: 1s → 2s → 4s)
    2. Compare with the stored snapshot in PostgreSQL
    3. New instruments  → listing event
    4. Removed instruments → delisting event
    5. Update the snapshot
    6. Enrich each new event (price, volume, spread, arbitrage, CoinGecko)
    7. Score the event (0–100)
    8. Deliver to each user who passes the filter check
       (watchlist overrides filters; dedup prevents duplicates)
```

Post-listing tracking jobs are scheduled per subscription and restored from the database on restart.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Telegram | aiogram 3 |
| Database | PostgreSQL 16 + SQLAlchemy (async) |
| Migrations | Alembic (auto-applied on startup) |
| Scheduler | APScheduler |
| HTTP | aiohttp |
| Containers | Docker + Docker Compose |
| Linting | Ruff |
| CI | GitHub Actions |

---

## Project Structure

```
app/
├── main.py              # Entry point
├── config.py            # Settings loaded from environment
├── i18n.py              # RU/EN translations
├── bot/
│   ├── dispatcher.py    # Bot dispatcher, rate-limiting middleware
│   ├── callback_data.py # CallbackData definitions
│   ├── handlers/        # Command and callback handlers
│   └── keyboards/       # Inline keyboard builders
├── exchanges/
│   ├── base.py          # Abstract exchange connector
│   ├── binance.py
│   ├── bybit.py
│   ├── coinbase.py
│   ├── okx.py
│   └── mexc.py
├── services/
│   ├── detector.py      # Listing/delisting detector
│   ├── notifier.py      # Notification fanout
│   ├── tracker.py       # Post-listing price reports (15m/1h/4h/24h)
│   ├── enrich.py        # Price, volume, spread enrichment
│   ├── arbitrage.py     # Cross-exchange price comparison
│   ├── coingecko.py     # CoinGecko metadata
│   ├── scoring.py       # Listing scoring (0–100)
│   ├── filtering.py     # Per-user filter evaluation
│   ├── dedup.py         # Notification deduplication
│   ├── digest.py        # Hourly digest delivery
│   ├── price_alerts.py  # Price threshold alerts
│   ├── delisting.py     # Delisting notifications
│   └── formatter.py     # Notification message formatting
├── db/
│   ├── models.py        # ORM models
│   ├── session.py       # Async session factory
│   └── repo/            # Repository layer (CRUD per table)
└── jobs/
    └── scheduler.py     # APScheduler job definitions
alembic/                 # Database migration scripts
tests/                   # Unit tests
docs/                    # Additional documentation
```

---

## Database Schema

| Table | Purpose |
|-------|---------|
| `users` | Registered users and their settings (JSONB) |
| `events` | Detected listing events |
| `deliveries` | Delivered notifications (used for deduplication) |
| `market_snapshots` | Current instrument snapshots per exchange |
| `watchlist` | Per-user ticker watchlists |
| `mutes` | Muted tickers, exchanges, or keywords |
| `tracking_subscriptions` | Post-listing tracking subscriptions |
| `digest_queue` | Events queued for hourly digests |
| `price_alerts` | User-defined price alert rules |
| `filter_presets` | Saved filter configurations |
| `callback_tokens` | Tokens for inline button actions |
| `analytics_events` | User action analytics |

---

## Scheduled Jobs

| Job ID | Interval | Description |
|--------|----------|-------------|
| `detector_poll` | 60 s (configurable) | Poll exchanges, detect listings and delistings |
| `digest_send` | 1 h | Send hourly digest to subscribed users |
| `price_alert_check` | 5 min | Check and fire price alerts |
| `announcement_check` | 10 min | Monitor exchange announcement channels |
| `track:{uuid}` | date-triggered | Send post-listing report at 15m / 1h / 4h / 24h |

---

## Listing Score

The score (0–100) is computed at enrichment time to give users a quick quality signal.

| Condition | Points |
|-----------|--------|
| Listed on Binance | +35 |
| Listed on Bybit | +30 |
| Listed on OKX | +25 |
| Listed on MEXC | +20 |
| Listed on Coinbase | +20 |
| Has a USDT pair | +10 |
| Volume ≥ $100k (5 min) | +15 |
| Volume ≥ $10k (5 min) | +5 |
| Volume < $1k (5 min) | −10 |
| `LOW_LIQUIDITY` flag | −10 |
| `HIGH_SPREAD` flag | −10 |

Users can set `/filters min_score 30` to receive only listings that meet a minimum quality threshold.

---

## Bot Commands Reference

### General
| Command | Description |
|---------|-------------|
| `/start` | Register and complete onboarding (choose exchanges, market types, mode) |
| `/help` | Show all available commands |
| `/status` | Show current filters and listing statistics |
| `/lang ru\|en` | Switch interface language |

### Filters
| Command | Description |
|---------|-------------|
| `/filters` | Show current settings (inline keyboard) |
| `/filters exchange <name> on\|off` | Enable or disable an exchange |
| `/filters market spot\|futures on\|off` | Enable or disable a market type |
| `/filters only_usdt on\|off` | Receive only USDT pairs |
| `/filters min_score <0..100>` | Set minimum listing score |

### Watchlist
| Command | Description |
|---------|-------------|
| `/watch BTC` | Add ticker to watchlist (always notified, ignores filters) |
| `/watchlist` | Show watchlist (limit: 50 tickers) |
| `/unwatch BTC` | Remove ticker from watchlist |

### Notification Control
| Command | Description |
|---------|-------------|
| `/pause 30m` | Pause notifications for 30 minutes |
| `/pause 2h` | Pause for 2 hours |
| `/pause 1d` | Pause for 1 day |
| `/pause` | Resume notifications immediately |
| `/digest on\|off` | Switch to hourly digest instead of instant alerts |

### Price Alerts
| Command | Description |
|---------|-------------|
| `/alert BTC > 100000` | Alert when BTC exceeds $100,000 |
| `/alert ETH < 2000` | Alert when ETH drops below $2,000 |
| `/alerts` | List active alerts (limit: 10) |
| `/unalert <ID>` | Remove an alert |

### History & Analytics
| Command | Description |
|---------|-------------|
| `/history` | Browse recent listings with pagination |
| `/history <exchange>` | Filter history by exchange |
| `/analytics` | Exchange activity statistics |

### Filter Presets
| Command | Description |
|---------|-------------|
| `/preset save <name>` | Save current filters as a named preset |
| `/preset load <name>` | Load a saved preset |
| `/preset list` | List all presets (limit: 5) |
| `/preset delete <name>` | Delete a preset |

### Admin (ADMIN_ID only)
| Command | Description |
|---------|-------------|
| `/admin stats` | User count and 24-hour event statistics |
| `/admin broadcast <text>` | Send a message to all users (rate-limited) |
| `/admin user <id>` | View settings and stats for a specific user |

---

## Quick Start (Docker — recommended)

### Requirements

| Tool | Version |
|------|---------|
| Docker | 24+ |
| Docker Compose | v2 (`docker compose`, not `docker-compose`) |
| Telegram Bot Token | from [@BotFather](https://t.me/BotFather) |

### Step 1 — Clone

```bash
git clone https://github.com/bsnisarchuk-oss/new-coin.git
cd new-coin
```

### Step 2 — Configure

```bash
cp .env.example .env
```

Open `.env` and fill in the required fields:

```env
BOT_TOKEN=YOUR_BOT_TOKEN_HERE   # From @BotFather
ADMIN_ID=123456789               # Your Telegram user ID (get it from @userinfobot)
POSTGRES_PASSWORD=change_me      # Database password for Docker Compose
```

All other settings have sensible defaults and can be left as-is.

### Step 3 — Start

```bash
docker compose up --build -d
```

This will automatically:
1. Start PostgreSQL 16
2. Apply Alembic migrations
3. Start the bot in polling mode

### Step 4 — Verify

```bash
# Follow live logs
docker compose logs -f bot

# Check both containers are healthy
docker compose ps
```

Expected startup output:
```
INFO  Bot started. Polling...
INFO  Bootstrap snapshots for binance/spot with 2145 instruments
INFO  Bootstrap snapshots for bybit/spot with 876 instruments
...
```

After the bootstrap phase completes, open Telegram and send `/start` to the bot.

---

## Local Development Setup

**Requirements:** Python 3.11+, PostgreSQL 16

```bash
# 1. Install all dependencies (including dev extras)
pip install -e ".[dev]"

# 2. Start only the database
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres

# 3. Configure environment
cp .env.example .env
# For local runs, update DATABASE_URL to use localhost instead of postgres

# 4. Start the bot (migrations run automatically)
python -m app.main
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BOT_TOKEN` | Yes | — | Telegram bot token from @BotFather |
| `ADMIN_ID` | No | — | Telegram user ID for admin commands and error alerts |
| `DATABASE_URL` | No | `postgresql+asyncpg://...@postgres:5432/new_coin_bot` | PostgreSQL connection string |
| `POSTGRES_DB` | No | `new_coin_bot` | Database name (Docker Compose) |
| `POSTGRES_USER` | No | `new_coin_bot` | Database user (Docker Compose) |
| `POSTGRES_PASSWORD` | No | `change_me` | Database password (Docker Compose) |
| `POLL_INTERVAL_SEC` | No | `60` | Exchange polling interval in seconds |
| `DEDUP_TTL_HOURS` | No | `24` | Deduplication window in hours |
| `MAX_NOTIFICATIONS_PER_HOUR` | No | `20` | Per-user notification rate cap |
| `MIN_VOL_5M` | No | `10000` | Minimum 5-minute volume (USD) for risk flagging |
| `MAX_SPREAD` | No | `0.02` | Maximum spread (2%) for risk flagging |
| `BOOTSTRAP_ON_EMPTY` | No | `true` | On first run, snapshot current state without notifying |
| `DEFAULT_ONLY_USDT` | No | `false` | Default filter for new users |
| `DEFAULT_MIN_SCORE` | No | `0` | Default minimum score for new users |
| `DEFAULT_ENABLED_EXCHANGES` | No | all five | Comma-separated list of enabled exchanges for new users |
| `DEFAULT_ENABLED_MARKET_TYPES` | No | `spot,futures` | Enabled market types for new users |
| `LOG_FORMAT` | No | `text` | `text` for human-readable logs, `json` for structured logs (Loki/Grafana) |
| `METRICS_PORT` | No | `9090` | Prometheus metrics HTTP port. Set to `0` to disable. |
| `HEALTH_PORT` | No | `8080` | Health check HTTP port |

---

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# With coverage report
pytest tests/ --cov=app --cov-report=term-missing

# Lint
ruff check .
```

CI runs on every push: lint (Ruff), unit tests with 45% coverage requirement, and a pip-audit security scan.

### Event Simulation

To test the full notification pipeline without waiting for a real listing:

```bash
docker compose run --rm --no-deps bot python -m app.scripts.simulate_event
```

This creates a synthetic `SIMxxxx/USDT` event and runs it through the complete detection and delivery pipeline.

---

## Deployment Notes

- The bot uses **long polling** — no webhook or public URL required. Any machine with Docker and internet access is sufficient.
- Alembic migrations run automatically at startup. The bot **will not start** if a migration fails, preventing a schema mismatch from causing silent data corruption.
- Tracking jobs that were in progress when the bot was restarted are restored from the database on startup.
- For production, set `LOG_FORMAT=json` for structured log ingestion (e.g. Grafana Loki).
- The Prometheus metrics endpoint (`METRICS_PORT=9090`) and health endpoint (`HEALTH_PORT=8080`) are available for external monitoring.

### Database Backup

```bash
# Create a compressed dump
docker exec new-coin-postgres-1 pg_dump -U new_coin_bot new_coin_bot \
  | gzip > backup_$(date +%Y%m%d_%H%M).sql.gz

# Restore from dump
gunzip -c backup_20260301_1200.sql.gz \
  | docker exec -i new-coin-postgres-1 psql -U new_coin_bot new_coin_bot
```

Recommended cron for daily backups:
```bash
0 3 * * * cd /path/to/new-coin && docker exec new-coin-postgres-1 \
  pg_dump -U new_coin_bot new_coin_bot \
  | gzip > /backups/backup_$(date +\%Y\%m\%d).sql.gz
```

### Updating

```bash
git pull origin master
docker compose up --build -d
docker compose logs -f bot
```

Migrations are applied automatically on the next startup.

---

## Business Value

This project demonstrates a complete, production-oriented Telegram bot with:

- **Multi-source data pipeline**: five independent exchange connectors, each with retry logic and snapshot-based change detection
- **Layered enrichment**: price data, volume, spread, cross-exchange arbitrage, and third-party (CoinGecko) metadata — all assembled before delivery
- **Per-user personalization at scale**: every user has their own filter configuration, watchlist, mutes, and presets stored in PostgreSQL
- **Robust async architecture**: fully async from HTTP requests to database queries, with APScheduler managing background jobs
- **Operational completeness**: structured logging, Prometheus metrics, health checks, admin broadcast, and database backup tooling are included — not afterthoughts
- **Maintainability**: Alembic migrations, GitHub Actions CI (lint + tests + security audit), and a clear module separation make the codebase easy to extend

For a buyer or employer, this represents a working system that covers the full lifecycle: data acquisition, processing, delivery, and operations.

---

## Customization Options

- **Add an exchange**: implement the `BaseExchange` abstract class in `app/exchanges/` and register it in the detector and enrichment service
- **Adjust scoring weights**: edit `app/services/scoring.py` — scores and thresholds are defined as named constants
- **Change default user settings**: set the `DEFAULT_*` environment variables — new users inherit these defaults on `/start`
- **Notification format**: all message templates are in `app/services/formatter.py` and `app/i18n.py`
- **Poll frequency**: `POLL_INTERVAL_SEC` controls how often exchanges are queried (minimum practical value depends on exchange API rate limits)
- **Risk thresholds**: `MIN_VOL_5M` and `MAX_SPREAD` control when risk flags are applied

---

## Limitations & Notes

- The bot uses public exchange REST APIs. No API keys are required for listing detection or price enrichment.
- CoinGecko metadata uses the public (unauthenticated) API — subject to rate limits. Under heavy load, enrichment may be partial.
- Exchange announcement monitoring (Binance, OKX) relies on their public announcement endpoints — availability and format may change.
- The deduplication window (`DEDUP_TTL_HOURS`) prevents the same listing from being delivered twice, but if a pair is delisted and re-listed within that window, the re-listing will be suppressed.
- The Prometheus and health endpoints are plain HTTP with no authentication. Do not expose them publicly without a reverse proxy or firewall rule.
- There is no built-in webhook mode. For environments where polling is restricted, a webhook setup would require additional code.

---

## Roadmap / Possible Improvements

The following are natural extensions not yet implemented:

- Webhook mode as an alternative to long polling
- Web dashboard for admin statistics
- Support for additional data sources (e.g. DEX listings, on-chain data)
- Configurable CoinGecko API key for higher rate limits
- Per-user notification history and statistics in-bot
- Multi-language extension beyond RU/EN

---

## License

MIT — see [LICENSE](LICENSE)

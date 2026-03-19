# Changelog

All notable changes to this project will be documented in this file.

Format: [Semantic Versioning](https://semver.org/)

---

## [Unreleased]

### Added
- `docker-compose.dev.yml` for explicit local development flow
- Structured JSON logging via `python-json-logger` (enable with `LOG_FORMAT=json`)
- Exponential backoff in exchange connector calls (3 attempts, 1/2/4s delays)
- In-memory cache for ArbitrageService with 90s TTL — reduces exchange API calls
- User notification when auto-switched to digest mode after hitting rate limit
- Watchlist limit: max 50 tickers per user
- `CHANGELOG.md`, `LICENSE` (MIT)
- `docs/SMOKE_TEST.md`, `docs/BUYER_HANDOFF.md`, `docs/RELEASE_NOTES_2026-03-17.md`
- Persistent service state for announcement monitor and volume spike detector

### Fixed
- **Scoring**: OKX (+25), MEXC (+20), Coinbase (+20) scores now applied correctly
  (previously all three exchanges scored 0, blocking notifications for users with `min_score > 0`)
- **`/analytics`**: `AttributeError` when asyncpg returns plain `str` instead of `MarketType` enum
- **`Dockerfile`**: container no longer runs as root; added `HEALTHCHECK`
- **`session.py`**: database connection pool configured (`pool_size=10`, `max_overflow=20`, `pool_recycle=1800`)
- **`main.py`**: migration failures now abort startup with exit code 1
- **`main.py`**: `scheduler.shutdown(wait=True)` — tracking jobs no longer dropped on SIGTERM
- **`.env.example`**: removed real bot token and admin ID
- **Deploy flow**: `.env.example` now matches Docker Compose defaults
- **Delistings**: delivery path restored in scheduler
- **OKX spot enrichment**: instrument IDs now use `BTC-USDT` instead of invalid `BTC-USDT-SPOT`
- **Health/readiness**: healthcheck now reflects app startup state instead of raw DB connectivity
- **i18n**: onboarding, main menu and bot command descriptions now have English equivalents

### Tests
- Fixed `test_filtering.py`: removed invalid `redis_url` field from `Settings`
- Extended `test_scoring.py`: full coverage for all 5 exchanges + edge cases
- Added `test_arbitrage.py`: cache hit, cache expiry, case-insensitive key
- Added `test_analytics_enum.py`: enum coercion safety tests

---

## [0.2.0] — 2026-02-24

### Added
- Arbitrage service: cross-exchange price comparison (5 exchanges in parallel)
- `simulate_event.py` script: `python -m app.scripts.simulate_event BTC USDT`
- Analytics events & hooks tracking

### Changed
- Event message now includes arbitrage block when ≥2 exchanges responded

---

## [0.1.0] — 2026-02-19

### Added
- Initial release
- Listing/delisting detection across Binance, Bybit, OKX, MEXC, Coinbase
- User filters: exchanges, market types, USDT-only, min_score
- Mute rules: by ticker, exchange, keyword
- Watchlist + delisting notifications
- Tracking subscriptions: 15m / 1h post-listing reports
- Digest mode (hourly aggregation)
- Price alerts (`/alert`, `/alerts`, `/unalert`)
- Filter presets (`/preset save|load|list|delete`)
- APScheduler jobs: detector (60s), digest (1h), price alerts (5m), announcements (10m)
- Alembic migrations (auto-applied on startup)
- Docker + docker-compose deployment

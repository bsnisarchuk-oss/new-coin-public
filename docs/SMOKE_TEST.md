# Smoke Test

Use this checklist on a fresh server before calling the build release-ready.

## 1. Prepare

```bash
cp .env.example .env
# fill BOT_TOKEN / ADMIN_ID / POSTGRES_PASSWORD
docker compose up --build -d
```

## 2. Runtime checks

```bash
docker compose ps
docker compose logs --tail=100 bot
docker inspect --format='{{json .State.Health}}' new-coin-bot-1
```

Expected:
- `postgres` is healthy
- `bot` is healthy
- logs show migrations completed and polling started

## 3. Telegram checks

1. Send `/start`
2. Complete onboarding in your target language
3. Run `/status`, `/help`, `/lang en`, `/lang ru`
4. Create and remove one watchlist item
5. Create and remove one price alert

## 4. Data checks

```bash
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select count(*) from users;"
```

## 5. Optional dev-only endpoints

When using `docker-compose.dev.yml`:

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:9090/metrics
```

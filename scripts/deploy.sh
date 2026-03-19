#!/usr/bin/env bash
set -Eeuo pipefail

BRANCH="${1:-master}"

echo "==> Deploy branch: ${BRANCH}"
echo "==> Repo: $(pwd)"

if ! command -v git >/dev/null 2>&1; then
  echo "git is not installed" >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not installed" >&2
  exit 1
fi

git fetch origin "${BRANCH}"
git checkout "${BRANCH}"
git pull --ff-only origin "${BRANCH}"

docker compose up -d postgres
docker compose run --rm --no-deps bot python -m alembic upgrade head
docker compose up -d --build bot

echo "==> Service status"
docker compose ps

echo "==> Bot logs (tail)"
docker compose logs --tail=100 bot || true

echo "==> Deploy complete"

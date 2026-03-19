# Buyer Handoff

Include these files in the sale package:

- source code
- `.env.example`
- `README.md`
- `CHANGELOG.md`
- `LICENSE`
- `docs/SMOKE_TEST.md`

Recommended extras:

- short demo video or GIF
- screenshots of onboarding, alerts, analytics and export
- a tested `.env` template for the buyer's target environment
- deployment notes for Docker host / VPS

What to say honestly:

- bot uses long polling
- base compose file is production-safe; `docker-compose.dev.yml` is for local work only
- metrics are internal by default
- no web panel / billing is included

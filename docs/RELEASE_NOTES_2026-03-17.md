# Release Notes — 2026-03-17

## Highlights

- fixed broken Docker onboarding in `.env.example`
- restored delisting delivery path in the scheduler
- fixed OKX spot enrichment instrument IDs
- split production and development compose flows
- made health/readiness checks reflect app startup state
- persisted announcement and volume-spike state across restarts
- improved English UX for onboarding, menu labels and bot commands

## Validation

- `python -m pytest -q -p no:cacheprovider tests`
- `python -m ruff check .`

## Known limits

- polling + scheduler still run in the same process
- delivery fanout is still not queue-based
- no web panel or billing is included

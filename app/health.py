"""Lightweight HTTP healthcheck server (aiohttp)."""
from __future__ import annotations

import logging
import time
from typing import Any

from aiohttp import web

LOGGER = logging.getLogger(__name__)

_start_time = time.time()
_health_state: dict[str, Any] = {
    "ready": False,
    "phase": "startup",
}


def set_readiness(ready: bool, *, phase: str) -> None:
    _health_state["ready"] = ready
    _health_state["phase"] = phase


async def _handle(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok" if _health_state["ready"] else "starting",
        "ready": _health_state["ready"],
        "phase": _health_state["phase"],
        "uptime_sec": int(time.time() - _start_time),
    })


async def start_health_server(port: int = 8080) -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", _handle)
    app.router.add_get("/health", _handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    LOGGER.info("Health server listening on :%d", port)
    return runner

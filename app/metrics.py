"""Prometheus metrics definitions and HTTP server startup."""
from __future__ import annotations

import logging

from prometheus_client import Counter, Gauge, Histogram, start_http_server

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------

listings_detected = Counter(
    "listings_detected_total",
    "Total listing events detected",
    ["exchange", "market_type"],
)

notifications_sent = Counter(
    "notifications_sent_total",
    "Total notifications delivered to users",
    ["delivery_mode"],  # instant | digest | instant_retry
)

price_alerts_triggered = Counter(
    "price_alerts_triggered_total",
    "Total price alerts triggered",
)

job_errors = Counter(
    "job_errors_total",
    "Total scheduler job failures",
    ["job_id"],
)

# ---------------------------------------------------------------------------
# Gauges
# ---------------------------------------------------------------------------

active_users = Gauge(
    "active_users_total",
    "Number of registered users",
)

# ---------------------------------------------------------------------------
# Histograms
# ---------------------------------------------------------------------------

detector_job_duration = Histogram(
    "detector_job_duration_seconds",
    "Time spent in detector poll job",
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
)

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

def start_metrics_server(port: int = 9090) -> bool:
    """Start the Prometheus HTTP metrics server on the given port."""
    if port <= 0:
        LOGGER.info("Prometheus metrics server disabled")
        return False
    try:
        start_http_server(port)
        LOGGER.info("Prometheus metrics server started on :%d", port)
        return True
    except OSError as exc:
        LOGGER.warning("Could not start metrics server on :%d — %s", port, exc)
        return False

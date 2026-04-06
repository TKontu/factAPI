#!/usr/bin/env python3
"""
fx-refresher: Seeds and updates EUR/USD exchange rates in factAPI.

Usage:
    python fetch_rates.py --seed     # One-time historical seed (idempotent)
    python fetch_rates.py --update   # Daily incremental update (run via cron)

Data source: Frankfurter API (https://api.frankfurter.app), backed by ECB.
No API key required. Rates published on ECB business days ~16:00 CET.
"""

import argparse
import csv
import io
import logging
import os
import sys
import time
from datetime import date, timedelta
from typing import Any

import httpx
import structlog

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FACTAPI_URL = os.environ.get("REFRESHER_FACTAPI_URL", "http://factapi:8000").rstrip("/")
ADMIN_KEY = os.environ.get("REFRESHER_ADMIN_KEY", "")
API_KEY = os.environ.get("REFRESHER_API_KEY", "")
LOG_LEVEL = os.environ.get("REFRESHER_LOG_LEVEL", "info").upper()
STARTUP_WAIT = int(os.environ.get("REFRESHER_STARTUP_WAIT_SECONDS", "60"))

COLLECTION = "fx_rates"
SEED_START = date(1999, 1, 4)  # First ECB EUR reference rate publication
FRANKFURTER_BASE = "https://api.frankfurter.dev/v1"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0  # seconds; doubles each attempt


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def setup_logging() -> structlog.stdlib.BoundLogger:
    """Configure structlog to match factAPI's logging style."""
    level = getattr(logging, LOG_LEVEL, logging.INFO)

    shared_processors: list[Any] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    renderer: Any = (
        structlog.dev.ConsoleRenderer()
        if LOG_LEVEL == "DEBUG"
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    return structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def wait_for_factapi(log: structlog.stdlib.BoundLogger) -> None:
    """Poll GET /health until factAPI is ready or STARTUP_WAIT is exceeded.

    Args:
        log: Bound logger instance.

    Raises:
        SystemExit: If factAPI does not become healthy within the timeout.
    """
    health_url = f"{FACTAPI_URL}/health"
    deadline = time.monotonic() + STARTUP_WAIT
    log.info("waiting_for_factapi", url=health_url, timeout_seconds=STARTUP_WAIT)

    while time.monotonic() < deadline:
        try:
            resp = httpx.get(health_url, timeout=5.0)
            if resp.status_code == 200 and resp.json().get("status") == "healthy":
                log.info("factapi_ready")
                return
        except httpx.RequestError:
            pass  # Still starting up
        time.sleep(3)

    log.error("factapi_startup_timeout", timeout_seconds=STARTUP_WAIT)
    sys.exit(1)


def http_get_with_retry(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    log: structlog.stdlib.BoundLogger,
) -> httpx.Response:
    """GET with exponential-backoff retry.

    4xx errors are not retried (they indicate logic errors, not transient faults).

    Args:
        client: Shared httpx.Client instance.
        url: Full URL to request.
        headers: Request headers.
        log: Bound logger instance.

    Returns:
        Successful httpx.Response.

    Raises:
        httpx.HTTPStatusError: On non-retryable 4xx response.
        SystemExit: After MAX_RETRIES exhausted on transient errors.
    """
    delay = RETRY_BASE_DELAY
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.get(url, headers=headers, timeout=30.0)
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as exc:
            log.warning(
                "http_error",
                url=url,
                status=exc.response.status_code,
                attempt=attempt,
            )
            if exc.response.status_code < 500:
                raise  # 4xx: not retryable
        except httpx.RequestError as exc:
            log.warning("request_error", url=url, error=str(exc), attempt=attempt)

        if attempt < MAX_RETRIES:
            log.info("retry_backoff", delay_seconds=delay, next_attempt=attempt + 1)
            time.sleep(delay)
            delay *= 2

    log.error("max_retries_exceeded", url=url)
    sys.exit(1)


# ---------------------------------------------------------------------------
# factAPI interaction
# ---------------------------------------------------------------------------


def collection_exists(client: httpx.Client, log: structlog.stdlib.BoundLogger) -> bool:
    """Check whether the fx_rates collection exists in factAPI.

    Args:
        client: Shared httpx.Client instance.
        log: Bound logger instance.

    Returns:
        True if collection exists, False if 404.

    Raises:
        SystemExit: On connection errors.
    """
    url = f"{FACTAPI_URL}/api/v1/collections/{COLLECTION}/schema"
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    try:
        resp = client.get(url, headers=headers, timeout=10.0)
        if resp.status_code == 200:
            return True
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
    except httpx.RequestError as exc:
        log.error("schema_check_failed", error=str(exc))
        sys.exit(1)
    return False  # unreachable; satisfies type checker


def get_last_date(
    client: httpx.Client, log: structlog.stdlib.BoundLogger
) -> date | None:
    """Return the most recent date stored in the fx_rates collection.

    Args:
        client: Shared httpx.Client instance.
        log: Bound logger instance.

    Returns:
        Most recent date, or None if the collection is empty.

    Raises:
        SystemExit: If the stored date value cannot be parsed.
    """
    url = f"{FACTAPI_URL}/api/v1/collections/{COLLECTION}"
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    resp = http_get_with_retry(client, f"{url}?_sort=-date&_limit=1", headers, log)
    rows = resp.json().get("data", [])
    if not rows:
        log.warning("collection_empty", collection=COLLECTION)
        return None
    raw = rows[0].get("date")
    try:
        return date.fromisoformat(raw)
    except (ValueError, TypeError) as exc:
        log.error("invalid_date_in_collection", date_value=raw, error=str(exc))
        sys.exit(1)


def create_collection(
    client: httpx.Client, csv_bytes: bytes, log: structlog.stdlib.BoundLogger
) -> None:
    """POST CSV to create the fx_rates collection.

    Args:
        client: Shared httpx.Client instance.
        csv_bytes: UTF-8 CSV content to upload.
        log: Bound logger instance.
    """
    url = f"{FACTAPI_URL}/api/v1/admin/collections"
    headers = {"X-Admin-Key": ADMIN_KEY} if ADMIN_KEY else {}
    resp = client.post(
        url,
        headers=headers,
        data={"name": COLLECTION},
        files={"file": ("fx_rates.csv", csv_bytes, "text/csv")},
        timeout=60.0,  # Historical seed ~6700+ rows; NAS hardware can be slow
    )
    resp.raise_for_status()
    meta = resp.json()
    log.info(
        "collection_created", collection=COLLECTION, row_count=meta.get("row_count")
    )


def append_to_collection(
    client: httpx.Client, csv_bytes: bytes, log: structlog.stdlib.BoundLogger
) -> None:
    """POST CSV to append rows to the fx_rates collection.

    Args:
        client: Shared httpx.Client instance.
        csv_bytes: UTF-8 CSV content to upload. Headers must match collection schema.
        log: Bound logger instance.
    """
    url = f"{FACTAPI_URL}/api/v1/admin/collections/{COLLECTION}/append"
    headers = {"X-Admin-Key": ADMIN_KEY} if ADMIN_KEY else {}
    resp = client.post(
        url,
        headers=headers,
        files={"file": ("fx_rates_update.csv", csv_bytes, "text/csv")},
        timeout=30.0,
    )
    resp.raise_for_status()
    meta = resp.json()
    log.info(
        "collection_appended",
        collection=COLLECTION,
        total_row_count=meta.get("row_count"),
    )


# ---------------------------------------------------------------------------
# Frankfurter API
# ---------------------------------------------------------------------------


def fetch_frankfurter_range(
    client: httpx.Client,
    start: date,
    end: date,
    log: structlog.stdlib.BoundLogger,
) -> dict[str, dict[str, float]]:
    """Fetch EUR/USD rates for a date range from the Frankfurter API.

    Non-business days (weekends, ECB holidays) are silently omitted by
    Frankfurter — an empty dict is a valid, non-error response.

    Frankfurter returns a flat format for single-date requests:
        {"rates": {"USD": 1.09}}
    vs the nested format for ranges:
        {"rates": {"2024-01-15": {"USD": 1.09}}}
    Both are normalised to the nested form here.

    Args:
        client: Shared httpx.Client instance.
        start: Start date (inclusive).
        end: End date (inclusive).
        log: Bound logger instance.

    Returns:
        Dict mapping ISO date strings to {"USD": float}. May be empty.
    """
    url = f"{FRANKFURTER_BASE}/{start.isoformat()}..{end.isoformat()}?from=EUR&to=USD"
    log.info("fetching_frankfurter", start=str(start), end=str(end))
    resp = http_get_with_retry(client, url, headers={}, log=log)
    data = resp.json()
    rates: dict[str, Any] = data.get("rates", {})

    # Normalise single-date flat response {"USD": 1.09} → {"2024-01-15": {"USD": 1.09}}
    if rates and not isinstance(next(iter(rates.values())), dict):
        single_date = data.get("start_date") or data.get("end_date")
        rates = {single_date: rates} if single_date else {}

    log.info("frankfurter_fetched", business_day_count=len(rates))
    return rates  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# CSV generation
# ---------------------------------------------------------------------------


def rates_to_csv(rates: dict[str, dict[str, float]]) -> bytes:
    """Convert a Frankfurter rates dict to CSV bytes for factAPI.

    Args:
        rates: Mapping of ISO date string → {"USD": float}.

    Returns:
        UTF-8-encoded CSV with headers: date,eur_to_usd,usd_to_eur
        Rows are sorted ascending by date.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "eur_to_usd", "usd_to_eur"])
    for date_str in sorted(rates):
        usd_rate = rates[date_str].get("USD")
        if not usd_rate:  # None or 0.0 — skip bad/missing data
            continue
        writer.writerow([date_str, round(usd_rate, 6), round(1.0 / usd_rate, 6)])
    return buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_seed(client: httpx.Client, log: structlog.stdlib.BoundLogger) -> None:
    """Seed all historical EUR/USD rates from 1999-01-04 to today.

    Idempotent: exits cleanly if the collection already exists.

    Args:
        client: Shared httpx.Client instance.
        log: Bound logger instance.
    """
    log.info("seed_start")

    if collection_exists(client, log):
        log.info("seed_skipped", reason="collection_already_exists")
        return

    today = date.today()
    rates = fetch_frankfurter_range(client, SEED_START, today, log)

    if not rates:
        log.error("seed_failed", reason="frankfurter_returned_no_rates")
        sys.exit(1)

    csv_bytes = rates_to_csv(rates)
    row_count = csv_bytes.count(b"\n") - 1  # subtract header row
    log.info("seed_csv_ready", row_count=row_count)
    create_collection(client, csv_bytes, log)
    log.info("seed_complete", row_count=row_count)


def cmd_update(client: httpx.Client, log: structlog.stdlib.BoundLogger) -> None:
    """Append any new EUR/USD rates since the last stored date.

    Gap detection: queries factAPI for the most recent date stored, then
    fetches everything from the next day to today. Handles multi-day gaps
    caused by container downtime or ECB holidays transparently.

    Deduplication: the `last_date >= yesterday` check ensures the same rate
    is never submitted twice (ECB publishes at ~15:00 UTC; cron fires at
    18:30 UTC, so if today's rate exists it is already stored).

    Args:
        client: Shared httpx.Client instance.
        log: Bound logger instance.
    """
    log.info("update_start")

    if not collection_exists(client, log):
        log.info("collection_missing", action="seeding_first")
        cmd_seed(client, log)
        return  # Seed already fetched up to today

    last_date = get_last_date(client, log)
    today = date.today()
    yesterday = today - timedelta(days=1)

    if last_date is None:
        # Collection exists but has no rows — re-seed from the beginning
        log.warning("collection_empty_reseeding")
        rates = fetch_frankfurter_range(client, SEED_START, today, log)
        if rates:
            append_to_collection(client, rates_to_csv(rates), log)
        return

    if last_date >= yesterday:
        log.info(
            "update_skipped",
            reason="already_up_to_date",
            last_date=str(last_date),
            today=str(today),
        )
        return

    fetch_start = last_date + timedelta(days=1)
    rates = fetch_frankfurter_range(client, fetch_start, today, log)

    if not rates:
        log.info(
            "update_skipped",
            reason="no_new_rates",
            note="all_non_business_days_in_range",
            fetch_start=str(fetch_start),
            fetch_end=str(today),
        )
        return

    csv_bytes = rates_to_csv(rates)
    new_rows = csv_bytes.count(b"\n") - 1
    log.info("appending_new_rates", new_rows=new_rows, from_date=str(fetch_start))
    append_to_collection(client, csv_bytes, log)
    log.info("update_complete", new_rows=new_rows, last_date=str(last_date))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    log = setup_logging()

    parser = argparse.ArgumentParser(
        description="Seed and update EUR/USD exchange rates in factAPI."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seed", action="store_true", help="Seed all historical rates")
    group.add_argument(
        "--update", action="store_true", help="Append new rates since last stored date"
    )
    args = parser.parse_args()

    wait_for_factapi(log)

    with httpx.Client() as client:
        if args.seed:
            cmd_seed(client, log)
        else:
            cmd_update(client, log)


if __name__ == "__main__":
    main()

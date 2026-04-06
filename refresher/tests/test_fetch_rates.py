"""
Unit tests for fetch_rates.py.

All HTTP calls are mocked — no real network or factAPI instance required.
Run with:
    PYTHONPATH=refresher pytest refresher/tests/ -v
"""

import csv
import io
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import fetch_rates
import httpx
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_csv(csv_bytes: bytes) -> list[dict[str, str]]:
    """Parse CSV bytes into a list of dicts."""
    return list(csv.DictReader(io.StringIO(csv_bytes.decode())))


def mock_response(status: int = 200, json_body: object = None) -> MagicMock:
    """Build a minimal mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.json.return_value = json_body or {}
    if status >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            str(status), request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# TestRatesToCsv
# ---------------------------------------------------------------------------


class TestRatesToCsv:
    def test_headers_are_correct(self) -> None:
        rows = parse_csv(fetch_rates.rates_to_csv({"2024-01-15": {"USD": 1.0964}}))
        assert list(rows[0].keys()) == ["date", "eur_to_usd", "usd_to_eur"]

    def test_eur_to_usd_value(self) -> None:
        rows = parse_csv(fetch_rates.rates_to_csv({"2024-01-15": {"USD": 1.0964}}))
        assert float(rows[0]["eur_to_usd"]) == pytest.approx(1.0964, rel=1e-4)

    def test_usd_to_eur_is_reciprocal(self) -> None:
        rows = parse_csv(fetch_rates.rates_to_csv({"2024-01-15": {"USD": 1.0964}}))
        assert float(rows[0]["usd_to_eur"]) == pytest.approx(1.0 / 1.0964, rel=1e-4)

    def test_rows_sorted_ascending(self) -> None:
        rates = {
            "2024-01-17": {"USD": 1.09},
            "2024-01-15": {"USD": 1.11},
            "2024-01-16": {"USD": 1.10},
        }
        rows = parse_csv(fetch_rates.rates_to_csv(rates))
        dates = [r["date"] for r in rows]
        assert dates == sorted(dates)

    def test_empty_input_produces_header_only(self) -> None:
        rows = parse_csv(fetch_rates.rates_to_csv({}))
        assert rows == []

    def test_skips_entry_missing_usd_key(self) -> None:
        rates = {
            "2024-01-15": {"GBP": 0.85},  # No USD key
            "2024-01-16": {"USD": 1.0964},
        }
        rows = parse_csv(fetch_rates.rates_to_csv(rates))
        assert len(rows) == 1
        assert rows[0]["date"] == "2024-01-16"

    def test_skips_zero_rate(self) -> None:
        """usd_rate == 0.0 would cause ZeroDivisionError — must be skipped."""
        rates = {
            "2024-01-15": {"USD": 0.0},
            "2024-01-16": {"USD": 1.0964},
        }
        rows = parse_csv(fetch_rates.rates_to_csv(rates))
        assert len(rows) == 1
        assert rows[0]["date"] == "2024-01-16"

    def test_precision_at_most_six_decimals(self) -> None:
        rows = parse_csv(
            fetch_rates.rates_to_csv({"2024-01-15": {"USD": 1.0964123456789}})
        )
        decimal_part = rows[0]["eur_to_usd"].split(".")[-1]
        assert len(decimal_part) <= 6


# ---------------------------------------------------------------------------
# TestFetchFrankfurterRange — single-date normalisation
# ---------------------------------------------------------------------------


class TestFetchFrankfurterRange:
    def test_normalises_single_date_flat_response(self) -> None:
        """Frankfurter returns flat {"USD": 1.09} for single-date requests."""
        flat_resp = mock_response(
            json_body={
                "start_date": "2024-01-15",
                "end_date": "2024-01-15",
                "rates": {"USD": 1.0964},
            }
        )
        mock_client = MagicMock()
        mock_log = MagicMock()

        with patch.object(fetch_rates, "http_get_with_retry", return_value=flat_resp):
            result = fetch_rates.fetch_frankfurter_range(
                mock_client, date(2024, 1, 15), date(2024, 1, 15), mock_log
            )

        assert result == {"2024-01-15": {"USD": 1.0964}}

    def test_returns_empty_for_all_weekend_range(self) -> None:
        """Empty rates dict is valid — not an error."""
        empty_resp = mock_response(json_body={"rates": {}})
        mock_log = MagicMock()

        with patch.object(fetch_rates, "http_get_with_retry", return_value=empty_resp):
            result = fetch_rates.fetch_frankfurter_range(
                MagicMock(), date(2024, 1, 13), date(2024, 1, 14), mock_log
            )

        assert result == {}

    def test_multi_date_range_returned_unchanged(self) -> None:
        rates_data = {
            "2024-01-15": {"USD": 1.09},
            "2024-01-16": {"USD": 1.10},
        }
        resp = mock_response(json_body={"rates": rates_data})
        mock_log = MagicMock()

        with patch.object(fetch_rates, "http_get_with_retry", return_value=resp):
            result = fetch_rates.fetch_frankfurter_range(
                MagicMock(), date(2024, 1, 15), date(2024, 1, 16), mock_log
            )

        assert result == rates_data


# ---------------------------------------------------------------------------
# TestCollectionExists
# ---------------------------------------------------------------------------


class TestCollectionExists:
    def test_returns_true_on_200(self) -> None:
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response(200)
        assert fetch_rates.collection_exists(mock_client, MagicMock()) is True

    def test_returns_false_on_404(self) -> None:
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response(404)
        assert fetch_rates.collection_exists(mock_client, MagicMock()) is False

    def test_exits_on_request_error(self) -> None:
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.RequestError("connection refused")
        with pytest.raises(SystemExit) as exc:
            fetch_rates.collection_exists(mock_client, MagicMock())
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# TestGetLastDate
# ---------------------------------------------------------------------------


class TestGetLastDate:
    def test_returns_parsed_date(self) -> None:
        resp = mock_response(
            json_body={"data": [{"date": "2024-01-15", "eur_to_usd": 1.09}]}
        )
        with patch.object(fetch_rates, "http_get_with_retry", return_value=resp):
            result = fetch_rates.get_last_date(MagicMock(), MagicMock())
        assert result == date(2024, 1, 15)

    def test_returns_none_for_empty_collection(self) -> None:
        resp = mock_response(json_body={"data": []})
        with patch.object(fetch_rates, "http_get_with_retry", return_value=resp):
            result = fetch_rates.get_last_date(MagicMock(), MagicMock())
        assert result is None

    def test_exits_on_invalid_date_value(self) -> None:
        resp = mock_response(json_body={"data": [{"date": "not-a-date"}]})
        with patch.object(fetch_rates, "http_get_with_retry", return_value=resp):
            with pytest.raises(SystemExit):
                fetch_rates.get_last_date(MagicMock(), MagicMock())


# ---------------------------------------------------------------------------
# TestHttpGetWithRetry
# ---------------------------------------------------------------------------


class TestHttpGetWithRetry:
    def test_returns_on_first_success(self) -> None:
        ok = mock_response(200)
        mock_client = MagicMock()
        mock_client.get.return_value = ok
        result = fetch_rates.http_get_with_retry(
            mock_client, "http://x", {}, MagicMock()
        )
        assert result is ok
        assert mock_client.get.call_count == 1

    def test_retries_on_5xx_then_succeeds(self) -> None:
        fail = mock_response(503)
        ok = mock_response(200)
        mock_client = MagicMock()
        mock_client.get.side_effect = [fail, ok]

        with patch("fetch_rates.time.sleep"):
            result = fetch_rates.http_get_with_retry(
                mock_client, "http://x", {}, MagicMock()
            )
        assert result is ok
        assert mock_client.get.call_count == 2

    def test_does_not_retry_on_4xx(self) -> None:
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response(404)

        with pytest.raises(httpx.HTTPStatusError):
            fetch_rates.http_get_with_retry(mock_client, "http://x", {}, MagicMock())
        assert mock_client.get.call_count == 1

    def test_exits_after_max_retries(self) -> None:
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.RequestError("timeout")

        with patch("fetch_rates.time.sleep"), pytest.raises(SystemExit) as exc:
            fetch_rates.http_get_with_retry(mock_client, "http://x", {}, MagicMock())
        assert exc.value.code == 1
        assert mock_client.get.call_count == fetch_rates.MAX_RETRIES

    def test_exponential_backoff_delays(self) -> None:
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.RequestError("timeout")
        sleep_calls: list[float] = []

        with (
            patch(
                "fetch_rates.time.sleep", side_effect=lambda d: sleep_calls.append(d)
            ),
            pytest.raises(SystemExit),
        ):
            fetch_rates.http_get_with_retry(mock_client, "http://x", {}, MagicMock())

        assert len(sleep_calls) == fetch_rates.MAX_RETRIES - 1
        assert sleep_calls[1] == sleep_calls[0] * 2  # each delay doubles


# ---------------------------------------------------------------------------
# TestCmdSeed
# ---------------------------------------------------------------------------


class TestCmdSeed:
    def test_skips_when_collection_exists(self) -> None:
        mock_client = MagicMock()
        with patch.object(fetch_rates, "collection_exists", return_value=True):
            fetch_rates.cmd_seed(mock_client, MagicMock())
        mock_client.post.assert_not_called()

    def test_exits_when_frankfurter_returns_empty(self) -> None:
        with (
            patch.object(fetch_rates, "collection_exists", return_value=False),
            patch.object(fetch_rates, "fetch_frankfurter_range", return_value={}),
            pytest.raises(SystemExit),
        ):
            fetch_rates.cmd_seed(MagicMock(), MagicMock())

    def test_creates_collection_when_rates_returned(self) -> None:
        rates = {"2024-01-15": {"USD": 1.09}, "2024-01-16": {"USD": 1.10}}
        with (
            patch.object(fetch_rates, "collection_exists", return_value=False),
            patch.object(fetch_rates, "fetch_frankfurter_range", return_value=rates),
            patch.object(fetch_rates, "create_collection") as mock_create,
        ):
            fetch_rates.cmd_seed(MagicMock(), MagicMock())
        mock_create.assert_called_once()
        csv_arg = mock_create.call_args[0][1]
        assert b"date,eur_to_usd,usd_to_eur" in csv_arg


# ---------------------------------------------------------------------------
# TestCmdUpdate
# ---------------------------------------------------------------------------


class TestCmdUpdate:
    def test_seeds_first_when_collection_missing(self) -> None:
        with (
            patch.object(fetch_rates, "collection_exists", return_value=False),
            patch.object(fetch_rates, "cmd_seed") as mock_seed,
        ):
            fetch_rates.cmd_update(MagicMock(), MagicMock())
        mock_seed.assert_called_once()

    def test_skips_when_last_date_is_today(self) -> None:
        today = date.today()
        with (
            patch.object(fetch_rates, "collection_exists", return_value=True),
            patch.object(fetch_rates, "get_last_date", return_value=today),
            patch.object(fetch_rates, "fetch_frankfurter_range") as mock_fetch,
        ):
            fetch_rates.cmd_update(MagicMock(), MagicMock())
        mock_fetch.assert_not_called()

    def test_skips_when_last_date_is_yesterday(self) -> None:
        yesterday = date.today() - timedelta(days=1)
        with (
            patch.object(fetch_rates, "collection_exists", return_value=True),
            patch.object(fetch_rates, "get_last_date", return_value=yesterday),
            patch.object(fetch_rates, "fetch_frankfurter_range") as mock_fetch,
        ):
            fetch_rates.cmd_update(MagicMock(), MagicMock())
        mock_fetch.assert_not_called()

    def test_skips_append_when_frankfurter_returns_empty(self) -> None:
        """All-weekend gap: Frankfurter returns no business-day rates."""
        old_date = date.today() - timedelta(days=5)
        with (
            patch.object(fetch_rates, "collection_exists", return_value=True),
            patch.object(fetch_rates, "get_last_date", return_value=old_date),
            patch.object(fetch_rates, "fetch_frankfurter_range", return_value={}),
            patch.object(fetch_rates, "append_to_collection") as mock_append,
        ):
            fetch_rates.cmd_update(MagicMock(), MagicMock())
        mock_append.assert_not_called()

    def test_appends_when_new_rates_available(self) -> None:
        old_date = date.today() - timedelta(days=3)
        rates = {
            str(old_date + timedelta(days=1)): {"USD": 1.09},
            str(old_date + timedelta(days=2)): {"USD": 1.10},
        }
        with (
            patch.object(fetch_rates, "collection_exists", return_value=True),
            patch.object(fetch_rates, "get_last_date", return_value=old_date),
            patch.object(fetch_rates, "fetch_frankfurter_range", return_value=rates),
            patch.object(fetch_rates, "append_to_collection") as mock_append,
        ):
            fetch_rates.cmd_update(MagicMock(), MagicMock())
        mock_append.assert_called_once()

    def test_fetch_start_is_day_after_last_date(self) -> None:
        """Verifies no off-by-one: fetch starts from last_date + 1."""
        last = date(2024, 1, 12)
        with (
            patch.object(fetch_rates, "collection_exists", return_value=True),
            patch.object(fetch_rates, "get_last_date", return_value=last),
            patch.object(
                fetch_rates, "fetch_frankfurter_range", return_value={}
            ) as mock_fetch,
        ):
            fetch_rates.cmd_update(MagicMock(), MagicMock())

        call_start = mock_fetch.call_args[0][1]
        assert call_start == date(2024, 1, 13)

    def test_reseeds_when_collection_empty(self) -> None:
        rates = {"2024-01-15": {"USD": 1.09}}
        with (
            patch.object(fetch_rates, "collection_exists", return_value=True),
            patch.object(fetch_rates, "get_last_date", return_value=None),
            patch.object(fetch_rates, "fetch_frankfurter_range", return_value=rates),
            patch.object(fetch_rates, "append_to_collection") as mock_append,
        ):
            fetch_rates.cmd_update(MagicMock(), MagicMock())
        mock_append.assert_called_once()

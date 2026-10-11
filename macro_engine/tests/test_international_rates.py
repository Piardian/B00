from __future__ import annotations

import datetime as dt
import json
from unittest.mock import patch, MagicMock

import pytest

from data_quality import DataUnavailableError
from ingestion.international_rates import InternationalRatesDataIngestion


def test_fetch_au_and_nz_yield_mock():
    ingest = InternationalRatesDataIngestion(api_key="test_key")

    mock_obs = {
        "observations": [
            {"date": "2026-06-01", "value": "4.10"},
            {"date": "2026-07-01", "value": "4.25"},
            {"date": "2026-08-01", "value": "4.35"},
        ]
    }

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_obs).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        au_data = ingest.fetch_au_yield(as_of=dt.datetime(2026, 8, 15, tzinfo=dt.timezone.utc))
        assert au_data["value"] == 4.35
        assert au_data["prev"] == 4.25
        assert "FRED" in au_data["source"]
        assert au_data["fallback_used"] is False

        nz_data = ingest.fetch_nz_yield(as_of=dt.datetime(2026, 8, 15, tzinfo=dt.timezone.utc))
        assert nz_data["value"] == 4.35
        assert "FRED" in nz_data["source"]


def test_fetch_yield_empty_raises():
    ingest = InternationalRatesDataIngestion(api_key="test_key")

    mock_obs = {"observations": []}

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_obs).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        with pytest.raises(DataUnavailableError):
            ingest.fetch_au_yield()


def test_fetch_yield_missing_key():
    ingest = InternationalRatesDataIngestion(api_key="")
    with pytest.raises(DataUnavailableError, match="FRED_API_KEY is not configured"):
        ingest.fetch_au_yield()

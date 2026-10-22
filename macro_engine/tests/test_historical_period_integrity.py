import datetime as dt
import unittest
from unittest.mock import patch

from data_quality import DataUnavailableError
from ingestion.fred_data import FredDataIngestion
from preprocessing.economic_regimes import _freshness


class HistoricalPeriodIntegrityTests(unittest.TestCase):
    def test_released_gdp_is_not_lost_outside_daily_lookback(self):
        fred = FredDataIngestion(api_key="test-key")
        with patch.object(fred, "_get_observations", return_value=[(dt.date(2024, 7, 1), 3.1)]) as request:
            result = fred._current_and_4w("A191RL1Q225SBEA", dt.date(2025, 1, 5))
        self.assertEqual(result[0], 3.1)
        self.assertLessEqual(request.call_args.args[1], dt.date(2024, 7, 1))
        self.assertEqual(request.call_args.kwargs["realtime_end"], dt.date(2025, 1, 5))

    def test_reference_quarter_start_is_not_publication_date(self):
        fred = {"GDP_QOQ_SAAR": 3.1, "data_quality": {"economic_observation_dates": {"GDP_QOQ_SAAR": "2024-07-01"}}}
        self.assertEqual(_freshness(fred, dt.date(2025, 1, 5))["GDP_QOQ_SAAR"], 97)
        with self.assertRaises(DataUnavailableError):
            _freshness(fred, dt.date(2025, 2, 5))

    def test_unavailable_optional_series_never_becomes_a_fake_date(self):
        fred = {"ISM_MANUFACTURING_PMI": None, "data_quality": {"economic_observation_dates": {"ISM_MANUFACTURING_PMI": "UNAVAILABLE"}}}
        self.assertEqual(_freshness(fred, dt.date(2025, 1, 5)), {})

    def test_future_period_still_rejected(self):
        fred = {"GDP_QOQ_SAAR": 3.1, "data_quality": {"economic_observation_dates": {"GDP_QOQ_SAAR": "2025-01-01"}}}
        with self.assertRaises(DataUnavailableError):
            _freshness(fred, dt.date(2025, 1, 5))

    def test_known_publication_age_preserves_actual_reference_date(self):
        from preprocessing.metrics import MacroMetricsCalculator
        fred={'ICSA':220.,'data_quality':{'observation_dates':{'ICSA':'2025-01-04'},
               'publication_dates':{'ICSA':'2025-01-09'}}}
        self.assertEqual(MacroMetricsCalculator()._validate_fred_freshness(fred,dt.date(2025,1,16))['ICSA'],7)
        self.assertEqual(fred['data_quality']['observation_dates']['ICSA'],'2025-01-04')

    def test_future_publication_does_not_pass_freshness(self):
        from preprocessing.metrics import MacroMetricsCalculator
        fred={'data_quality':{'observation_dates':{'ICSA':'2025-01-04'},'publication_dates':{'ICSA':'2025-01-09'}}}
        with self.assertRaises(DataUnavailableError):
            MacroMetricsCalculator()._validate_fred_freshness(fred,dt.date(2025,1,8))

    def test_pce_reference_month_is_not_confused_with_its_release(self):
        fred={'PCE_YOY':2.4,'data_quality':{'economic_observation_dates':{'PCE_YOY':'2024-11-01'},
                'economic_publication_dates':{'PCE_YOY':'2024-12-20'}}}
        self.assertEqual(_freshness(fred,dt.date(2025,1,31))['PCE_YOY'],42)

    def test_live_legacy_clock_keeps_intraday_time(self):
        from preprocessing import metrics
        original=dt.datetime
        fixed=original.now(dt.timezone.utc).replace(hour=12,minute=34,second=0,microsecond=0)
        class Frozen(original):
            @classmethod
            def now(cls,tz=None):return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)
        with patch.object(metrics.dt,'datetime',Frozen):
            with metrics._fixed_legacy_date(None,state={}):
                self.assertEqual(metrics.dt.datetime.now(dt.timezone.utc),fixed)

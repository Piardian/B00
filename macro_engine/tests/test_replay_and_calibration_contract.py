import datetime as dt
import json
import math
import tempfile
import unittest
from pathlib import Path

from calibration.replay import validate_replay_dataset, chronological_rows
from calibration.surprise_sigma import (
    calibrate_from_csv,
    load_calibration_profile,
    load_observations_csv,
    write_calibration_profile,
)
from data_quality import DataUnavailableError


def _make_csv_row(date_str: str, indicator: str, actual: float, forecast: float, provider: str = "ForexFactory", pit: str = "True") -> str:
    ts = f"{date_str}T13:30:00+00:00"
    return f"{date_str},{ts},{indicator},{actual},{forecast},{provider},{pit}"


CSV_HEADER = "date,event_timestamp_utc,indicator_type,actual,forecast,provider,point_in_time"


class ReplayAndCalibrationContractTests(unittest.TestCase):
    # -------------------------------------------------------------------------
    # Replay Contract Tests
    # -------------------------------------------------------------------------
    def test_replay_rejects_future_market_snapshot(self):
        rows = [{
            "timestamp": "2023-03-13T12:00:00+00:00",
            "market": {"timestamp": "2023-03-13T12:01:00+00:00"},
            "fred": {"timestamp": "2023-03-13T11:59:00+00:00"},
        }]
        with self.assertRaises(DataUnavailableError):
            validate_replay_dataset(rows)

    def test_replay_keeps_scheduled_future_event_without_actual(self):
        rows = [{
            "timestamp": "2023-03-13T12:00:00+00:00",
            "market": {"timestamp": "2023-03-13T11:59:00+00:00"},
            "fred": {"timestamp": "2023-03-13T11:59:00+00:00"},
            "calendar_events": [{
                "title": "CPI",
                "event_time_utc": "2023-03-13T12:15:00+00:00",
                "actual": "",
            }],
        }]
        self.assertEqual(len(validate_replay_dataset(rows)), 1)

    def test_chronological_rows_validates_before_sorting(self):
        rows = [
            {"timestamp": "2023-03-14T12:00:00+00:00", "market": {"timestamp": "2023-03-14T11:59:00+00:00"}, "fred": {"timestamp": "2023-03-14T11:59:00+00:00"}},
            {"timestamp": "2023-03-13T12:00:00+00:00", "market": {"timestamp": "2023-03-13T11:59:00+00:00"}, "fred": {"timestamp": "2023-03-13T11:59:00+00:00"}},
        ]
        ordered = chronological_rows(rows)
        self.assertEqual(ordered[0]["timestamp"], "2023-03-13T12:00:00+00:00")

    # -------------------------------------------------------------------------
    # Calibration Contract Tests
    # -------------------------------------------------------------------------
    def test_empty_calibration_dataset_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 1. Zero data rows raises "empty"
            path = Path(tmp) / "observations.csv"
            path.write_text("date,event_timestamp_utc,indicator_type,actual,forecast,provider,point_in_time\n", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                load_observations_csv(path)
            self.assertIn("empty", str(ctx.exception).lower())

            # 2. Missing required columns raises "missing columns"
            path_bad = Path(tmp) / "bad_cols.csv"
            path_bad.write_text("date,indicator_type,actual,forecast,source\n2023-01-01,cpi,0.3,0.2,test\n", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                load_observations_csv(path_bad)
            self.assertIn("missing columns", str(ctx.exception).lower())

    def test_calibration_fails_when_required_indicator_has_insufficient_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observations.csv"
            rows = [CSV_HEADER]
            # Provide 10 valid observations (below min_observations=30)
            for i in range(10):
                date = dt.date(2024, 1, 1) + dt.timedelta(days=i)
                rows.append(_make_csv_row(date.isoformat(), "cpi", 0.2 + (i % 3) / 10.0, 0.2))
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")

            with self.assertRaises(ValueError) as ctx:
                calibrate_from_csv(
                    path,
                    calibration_end=dt.date(2024, 12, 31),
                    validation_end=dt.date(2025, 6, 30),
                    min_observations=30,
                    required_indicators=("cpi",),
                )
            self.assertIn("Insufficient calibration observations for: cpi", str(ctx.exception))

    def test_calibration_chronological_split_and_no_leakage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observations.csv"
            rows = [CSV_HEADER]
            # 35 obs in 2021 (calibration)
            for i in range(35):
                date = dt.date(2021, 1, 1) + dt.timedelta(days=i * 5)
                rows.append(_make_csv_row(date.isoformat(), "cpi", 0.2 + (i % 4) / 10.0, 0.2))
            # 15 obs in 2022 (validation)
            for i in range(15):
                date = dt.date(2022, 1, 1) + dt.timedelta(days=i * 10)
                rows.append(_make_csv_row(date.isoformat(), "cpi", 0.3 + (i % 3) / 10.0, 0.2))
            # 10 obs in 2023 (out-of-sample)
            for i in range(10):
                date = dt.date(2023, 1, 1) + dt.timedelta(days=i * 10)
                rows.append(_make_csv_row(date.isoformat(), "cpi", 0.25, 0.2))
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")

            cal_end = dt.date(2021, 12, 31)
            val_end = dt.date(2022, 12, 31)
            result = calibrate_from_csv(
                path,
                calibration_end=cal_end,
                validation_end=val_end,
                min_observations=30,
                required_indicators=("cpi",),
            )
            # Verify split counts
            self.assertEqual(result["sample_counts"]["calibration"], 35)
            self.assertEqual(result["sample_counts"]["validation"], 15)
            self.assertEqual(result["sample_counts"]["out_of_sample"], 10)

            # Strict temporal isolation: no observation in calibration may exceed cal_end
            for row in load_observations_csv(path):
                row_date = dt.date.fromisoformat(row["date"])
                if row in result["validation_rows"]:
                    self.assertGreater(row_date, cal_end)
                    self.assertLessEqual(row_date, val_end)
                elif row in result["out_of_sample_rows"]:
                    self.assertGreater(row_date, val_end)

    def test_calibration_minimum_observation_omits_unqualified_indicators(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observations.csv"
            rows = [CSV_HEADER]
            # 32 observations for CPI (qualifies for min_obs=30)
            for i in range(32):
                date = dt.date(2022, 1, 1) + dt.timedelta(days=i * 3)
                rows.append(_make_csv_row(date.isoformat(), "cpi", 0.2 + (i % 3) / 10.0, 0.2))
            # 15 observations for NFP (fails min_obs=30)
            for i in range(15):
                date = dt.date(2022, 1, 1) + dt.timedelta(days=i * 7)
                rows.append(_make_csv_row(date.isoformat(), "nfp", 200000.0 + i * 1000, 190000.0))
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")

            result = calibrate_from_csv(
                path,
                calibration_end=dt.date(2022, 12, 31),
                validation_end=dt.date(2023, 12, 31),
                min_observations=30,
                required_indicators=(),  # Not strictly required
            )
            self.assertIn("cpi", result["sigmas"])
            self.assertNotIn("nfp", result["sigmas"])

            # min_observations <= 1 must be rejected
            with self.assertRaises(ValueError):
                calibrate_from_csv(
                    path,
                    calibration_end=dt.date(2022, 12, 31),
                    validation_end=dt.date(2023, 12, 31),
                    min_observations=1,
                )

    def test_calibration_mad_vs_std_methods(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observations.csv"
            rows = [CSV_HEADER]
            # 34 normal observations around forecast=0.2 (diff ~ 0.05 to 0.1)
            for i in range(34):
                date = dt.date(2022, 1, 1) + dt.timedelta(days=i * 2)
                diff = 0.05 if i % 2 == 0 else -0.05
                rows.append(_make_csv_row(date.isoformat(), "cpi", 0.2 + diff, 0.2))
            # 1 extreme outlier
            rows.append(_make_csv_row("2022-04-01", "cpi", 15.0, 0.2))
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")

            res_mad = calibrate_from_csv(
                path,
                calibration_end=dt.date(2022, 12, 31),
                validation_end=dt.date(2023, 12, 31),
                min_observations=30,
                method="mad",
            )
            res_std = calibrate_from_csv(
                path,
                calibration_end=dt.date(2022, 12, 31),
                validation_end=dt.date(2023, 12, 31),
                min_observations=30,
                method="std",
            )
            sigma_mad = res_mad["sigmas"]["cpi"]
            sigma_std = res_std["sigmas"]["cpi"]

            # MAD must be robust to the single extreme outlier, whereas STD is severely inflated
            self.assertLess(sigma_mad, 0.5)
            self.assertGreater(sigma_std, 2.0)
            self.assertLess(sigma_mad, sigma_std)
            self.assertEqual(res_mad["scale_estimator"], "mad")
            self.assertEqual(res_std["scale_estimator"], "std")

    def test_calibration_covid_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observations.csv"
            rows = [CSV_HEADER]
            # 30 baseline observations outside COVID window with non-zero variance
            for i in range(30):
                date = dt.date(2019, 1, 1) + dt.timedelta(days=i * 10)
                rows.append(_make_csv_row(date.isoformat(), "cpi", 0.2 + (i % 4) / 10.0, 0.2))
            # 4 COVID-era observations (March - July 2020)
            covid_dates = ["2020-03-15", "2020-04-15", "2020-05-15", "2020-06-15"]
            for c_date in covid_dates:
                rows.append(_make_csv_row(c_date, "cpi", 5.0, 0.2))
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")

            # With filter_covid_shock=True
            res_filtered = calibrate_from_csv(
                path,
                calibration_end=dt.date(2020, 12, 31),
                validation_end=dt.date(2021, 12, 31),
                min_observations=30,
                filter_covid_shock=True,
            )
            # With filter_covid_shock=False
            res_unfiltered = calibrate_from_csv(
                path,
                calibration_end=dt.date(2020, 12, 31),
                validation_end=dt.date(2021, 12, 31),
                min_observations=30,
                filter_covid_shock=False,
            )
            self.assertEqual(res_filtered["sample_counts"]["calibration"], 30)
            self.assertEqual(res_unfiltered["sample_counts"]["calibration"], 34)
            self.assertTrue(res_filtered["filter_covid_shock"])
            self.assertFalse(res_unfiltered["filter_covid_shock"])

    def test_calibration_accepts_forexfactory_and_tradingeconomics(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observations.csv"
            rows = [CSV_HEADER]
            for i in range(18):
                d1 = dt.date(2023, 1, 1) + dt.timedelta(days=i * 2)
                rows.append(_make_csv_row(d1.isoformat(), "cpi", 0.22, 0.2, provider="ForexFactory"))
                d2 = dt.date(2023, 1, 2) + dt.timedelta(days=i * 2)
                rows.append(_make_csv_row(d2.isoformat(), "cpi", 0.24, 0.2, provider="TradingEconomics"))
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")

            calibrated = calibrate_from_csv(
                path,
                calibration_end=dt.date(2023, 12, 31),
                validation_end=dt.date(2024, 12, 31),
                min_observations=30,
                required_indicators=("cpi",),
            )
            self.assertIn("cpi", calibrated["sigmas"])
            self.assertGreater(calibrated["sigmas"]["cpi"], 0)

    def test_calibration_rejects_untrusted_provider_and_non_pit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observations.csv"
            # 1. Untrusted provider
            rows_untrusted = [CSV_HEADER, _make_csv_row("2023-01-01", "cpi", 0.3, 0.2, provider="RandomBlog")]
            path.write_text("\n".join(rows_untrusted) + "\n", encoding="utf-8")
            with self.assertRaises(DataUnavailableError):
                load_observations_csv(path)

            # 2. point_in_time is False
            rows_non_pit = [CSV_HEADER, _make_csv_row("2023-01-01", "cpi", 0.3, 0.2, pit="False")]
            path.write_text("\n".join(rows_non_pit) + "\n", encoding="utf-8")
            with self.assertRaises(DataUnavailableError):
                load_observations_csv(path)

            # 3. Date and timestamp date disagree
            row_date_mismatch = "2023-01-01,2023-01-02T13:30:00+00:00,cpi,0.3,0.2,ForexFactory,True"
            path.write_text(f"{CSV_HEADER}\n{row_date_mismatch}\n", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                load_observations_csv(path)
            self.assertIn("disagree", str(ctx.exception))

    def test_calibration_profile_save_load_and_finite_positive_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.json"

            # 1. Valid profile roundtrip
            valid_profile = {
                "sigmas": {
                    "cpi": 0.125,
                    "nfp": 85000.0,
                    "pmi": 1.45,
                }
            }
            write_calibration_profile(valid_profile, profile_path)
            loaded = load_calibration_profile(profile_path)
            self.assertEqual(loaded["cpi"], 0.125)
            self.assertEqual(loaded["nfp"], 85000.0)
            self.assertEqual(loaded["pmi"], 1.45)

            # 2. Rejection of zero or negative sigma
            for invalid_val in [0.0, -1.5]:
                profile_path.write_text(json.dumps({"sigmas": {"cpi": invalid_val}}), encoding="utf-8")
                with self.assertRaises(ValueError) as ctx:
                    load_calibration_profile(profile_path)
                self.assertIn("Invalid calibrated sigma", str(ctx.exception))

            # 3. Rejection of NaN or Inf
            for invalid_val in ["NaN", "Infinity", "-Infinity"]:
                profile_path.write_text(f'{{"sigmas": {{"cpi": {invalid_val}}}}}', encoding="utf-8")
                with self.assertRaises(ValueError) as ctx:
                    load_calibration_profile(profile_path)
                self.assertIn("Invalid calibrated sigma", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)

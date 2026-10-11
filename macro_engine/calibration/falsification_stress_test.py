"""Econometric Falsification and Stress-Testing Engine for Macro Surprises.

Designed to rigorously challenge and attempt to falsify the empirical findings of the
macroeconomic calibration engine. Implements:
  1. 4-Way Model Comparison: Sign(Surprise) vs Raw Surprise vs Classic STD Z vs Robust MAD Z
  2. Bootstrap 95% Confidence Intervals (2,000 resamples) for IC, Hit Rates, and model deltas
  3. Permutation Tests (1,000 permutations) against H0: IC = 0 and H0: Hit Rate = 50%
  4. Event Clustering / De-duplication (collapsing simultaneous releases like NFP + Unemployment)
  5. 3D Decomposition: Year x Indicator x Horizon
  6. Transaction Cost & Spread Haircut (0 bps, 10 bps [1.0 pip], 15 bps [1.5 pips])
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import random
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from calibration.market_response_validation_v2 import (
    HORIZONS_MINUTES,
    audit_event_timestamp,
    calculate_usd_return_bps,
    fetch_mt5_bars,
    parse_observation_event_utc,
    spearman_rank_ic,
)
from core.deterministic_controls import INDICATOR_DIRECTIONS, fit_surprise_sigmas

BROKER_TZ = ZoneInfo("Europe/Helsinki")
UTC = dt.timezone.utc


def bootstrap_ci(
    data: Sequence[Any],
    metric_fn: Any,
    n_resamples: int = 2000,
    alpha: float = 0.05,
    seed: int = 42,
) -> Tuple[float, float, float]:
    """Computes percentile bootstrap confidence interval for a metric.
    
    Returns (point_estimate, ci_lower, ci_upper).
    """
    n = len(data)
    if n == 0:
        return 0.0, 0.0, 0.0
    point_est = float(metric_fn(data))
    if n < 5:
        return point_est, point_est, point_est

    rng = random.Random(seed)
    boot_estimates: List[float] = []
    for _ in range(n_resamples):
        sample = [data[rng.randint(0, n - 1)] for _ in range(n)]
        boot_estimates.append(float(metric_fn(sample)))

    boot_estimates.sort()
    idx_low = int((alpha / 2.0) * n_resamples)
    idx_high = int((1.0 - alpha / 2.0) * n_resamples)
    ci_low = boot_estimates[max(0, min(idx_low, n_resamples - 1))]
    ci_high = boot_estimates[max(0, min(idx_high, n_resamples - 1))]
    return point_est, ci_low, ci_high


def permutation_test_ic(
    x: Sequence[float],
    y: Sequence[float],
    n_permutations: int = 1000,
    seed: int = 42,
) -> float:
    """Computes two-sided empirical p-value for Spearman Rank IC against H0: IC = 0."""
    n = len(x)
    if n < 3:
        return 1.0
    obs_ic = abs(spearman_rank_ic(x, y))
    rng = random.Random(seed)
    y_shuffled = list(y)
    count_extreme = 0
    for _ in range(n_permutations):
        rng.shuffle(y_shuffled)
        perm_ic = abs(spearman_rank_ic(x, y_shuffled))
        if perm_ic >= obs_ic:
            count_extreme += 1
    return float(count_extreme / n_permutations)


def permutation_test_hit_rate(
    hits: Sequence[Mapping[str, Any]],
    z_key: str,
    ret_key: str,
    n_permutations: int = 1000,
    seed: int = 42,
) -> float:
    """Computes empirical p-value for directional hit rate against H0: Hit Rate = 50%."""
    n = len(hits)
    if n == 0:
        return 1.0
    actual_wins = sum(
        1 for r in hits
        if (float(r[z_key]) > 0 and float(r[ret_key]) > 0)
        or (float(r[z_key]) < 0 and float(r[ret_key]) < 0)
    )
    obs_hr = actual_wins / n
    if obs_hr <= 0.5:
        return 1.0

    # Under H0, direction of return is independent coin flip (prob = 0.5)
    rng = random.Random(seed)
    count_as_extreme = 0
    for _ in range(n_permutations):
        sim_wins = sum(1 for _ in range(n) if rng.random() < 0.5)
        sim_hr = sim_wins / n
        if sim_hr >= obs_hr:
            count_as_extreme += 1
    return float(count_as_extreme / n_permutations)


def calculate_hit_rate(records: Sequence[Mapping[str, Any]], z_key: str, ret_key: str, threshold: float = 1.0) -> float:
    """Calculates directional hit rate for signals where |Z| >= threshold."""
    subset = [r for r in records if abs(float(r[z_key])) >= threshold]
    if not subset:
        return 0.0
    wins = sum(
        1 for r in subset
        if (float(r[z_key]) > 0 and float(r[ret_key]) > 0)
        or (float(r[z_key]) < 0 and float(r[ret_key]) < 0)
    )
    return float(wins / len(subset))


def calculate_net_returns(
    records: Sequence[Mapping[str, Any]],
    z_key: str,
    ret_key: str,
    threshold: float = 1.0,
    cost_bps: float = 10.0,
) -> Dict[str, Any]:
    """Evaluates trading performance of |Z| >= threshold net of transaction costs (spread/slippage).
    
    Position: +1 if Z > 0 (Buy USD / Sell EURUSD), -1 if Z < 0 (Sell USD / Buy EURUSD).
    Trade return (bps) = Position * USD_return - cost_bps.
    """
    subset = [r for r in records if abs(float(r[z_key])) >= threshold]
    if not subset:
        return {
            "trade_count": 0,
            "mean_gross_bps": 0.0,
            "mean_net_bps": 0.0,
            "net_win_rate_pct": 0.0,
            "profit_factor": 0.0,
        }

    gross_pnl: List[float] = []
    net_pnl: List[float] = []
    for r in subset:
        pos = 1.0 if float(r[z_key]) > 0 else -1.0
        r_usd = float(r[ret_key])
        trade_gross = pos * r_usd
        trade_net = trade_gross - cost_bps
        gross_pnl.append(trade_gross)
        net_pnl.append(trade_net)

    wins = [x for x in net_pnl if x > 0]
    losses = [abs(x) for x in net_pnl if x < 0]
    sum_wins = sum(wins)
    sum_losses = sum(losses)
    profit_factor = (sum_wins / sum_losses) if sum_losses > 0 else (999.0 if sum_wins > 0 else 0.0)

    return {
        "trade_count": len(subset),
        "mean_gross_bps": round(mean(gross_pnl), 2),
        "mean_net_bps": round(mean(net_pnl), 2),
        "net_win_rate_pct": round(len(wins) / len(subset) * 100, 1),
        "profit_factor": round(profit_factor, 2),
    }


def cluster_simultaneous_events(records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Clusters simultaneous announcements (e.g. NFP + Unemployment at 13:30 UTC) into single event instants.
    
    Prevents artificial inflation of sample size or duplicate counting of single price movements.
    """
    by_time: Dict[str, List[Mapping[str, Any]]] = {}
    for r in records:
        t_key = str(r["event_timestamp_utc"])
        by_time.setdefault(t_key, []).append(r)

    clustered: List[Dict[str, Any]] = []
    for t_key, group in sorted(by_time.items()):
        # Base trade info from the group
        first = group[0]
        # Composite Z is the average of directional surprises across simultaneous releases
        comp_z_mad = mean(float(r["z_mad"]) for r in group)
        comp_z_std = mean(float(r["z_std"]) for r in group)
        comp_raw_surp = mean(float(r["raw_surprise"]) for r in group)
        comp_sign_surp = mean(float(r["sign_surprise"]) for r in group)

        entry = {
            "event_timestamp_utc": t_key,
            "year": first["year"],
            "cluster_size": len(group),
            "indicators": [str(r["indicator"]) for r in group],
            "z_mad": comp_z_mad,
            "z_std": comp_z_std,
            "raw_surprise": comp_raw_surp,
            "sign_surprise": comp_sign_surp,
        }
        for k in first:
            if k.startswith("ret_"):
                entry[k] = float(first[k])
        clustered.append(entry)

    return clustered


def extract_event_records(
    observations_path: Path,
    bar_map: Mapping[dt.datetime, Mapping[str, float]],
    test_years: Sequence[int] = tuple(range(2019, 2026)),
    min_observations: int = 15,
    horizons: Sequence[int] = (15, 30, 60, 240),
) -> List[Dict[str, Any]]:
    """Extracts aligned macro event records with all 4 models: Sign, Raw, STD, and MAD."""
    with observations_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    records: List[Dict[str, Any]] = []

    for year in test_years:
        history = [r for r in rows if dt.date.fromisoformat(r["date"]).year < year]
        mad = fit_surprise_sigmas(history, min_observations=min_observations, method="mad")
        std = fit_surprise_sigmas(history, min_observations=min_observations, method="std")

        for row in rows:
            if dt.date.fromisoformat(row["date"]).year != year:
                continue
            kind = str(row.get("indicator_type", "")).lower()
            if kind not in mad or kind not in std:
                continue
            try:
                actual = float(row["actual"])
                forecast = float(row["forecast"])
                event_utc = parse_observation_event_utc(row)
                direction = INDICATOR_DIRECTIONS.get(kind, 1.0)
                raw_diff = (actual - forecast) * direction
                sign_diff = 1.0 if raw_diff > 0 else (-1.0 if raw_diff < 0 else 0.0)
                z_mad = raw_diff / mad[kind]
                z_std = raw_diff / std[kind]
            except Exception:
                continue

            base_bar = bar_map.get(event_utc)
            if base_bar is None:
                continue

            prices: Dict[int, float] = {}
            complete = True
            for m in horizons:
                b = bar_map.get(event_utc + dt.timedelta(minutes=m))
                if b is None:
                    complete = False
                    break
                prices[m] = float(b["close"])
            if not complete:
                continue

            p0 = float(base_bar["open"])
            entry = {
                "year": year,
                "indicator": kind,
                "event": row.get("event", ""),
                "event_timestamp_utc": event_utc.isoformat(),
                "actual": actual,
                "forecast": forecast,
                "sign_surprise": sign_diff,
                "raw_surprise": raw_diff,
                "z_mad": z_mad,
                "z_std": z_std,
            }
            for m, pr in prices.items():
                entry[f"ret_{m}m"] = calculate_usd_return_bps(p0, pr)
            records.append(entry)

    return records


def run_falsification_analysis(
    records: List[Dict[str, Any]],
    horizons: Sequence[int] = (15, 30, 60, 240),
) -> Dict[str, Any]:
    """Executes the full econometric stress test, bootstrap falsification, and cost analysis."""
    if not records:
        return {"error": "No aligned records"}

    clustered = cluster_simultaneous_events(records)
    n_events = len(records)
    n_clusters = len(clustered)

    # 1. 4-Way Model Comparison across Horizons (Pooled and Clustered)
    models = [
        ("sign_surprise", "Model 0: Sign(Surprise)"),
        ("raw_surprise", "Model 1: Raw Surprise (A - F)"),
        ("z_std", "Model 2: Classic STD Z"),
        ("z_mad", "Model 3: Robust MAD Z"),
    ]

    horse_race: Dict[str, Any] = {}
    for m in horizons:
        ret_key = f"ret_{m}m"
        rets = [r[ret_key] for r in records]
        m_dict: Dict[str, Any] = {}
        for key, name in models:
            scores = [r[key] for r in records]
            ic_val, ic_low, ic_high = bootstrap_ci(
                list(zip(scores, rets)),
                lambda s: spearman_rank_ic([x[0] for x in s], [x[1] for x in s]),
            )
            p_val = permutation_test_ic(scores, rets)

            # Hit rate for actionable (|Z| >= 1.0 for Z-scores, non-zero for Sign/Raw)
            if key in ("z_mad", "z_std"):
                hits = [r for r in records if abs(r[key]) >= 1.0]
                hr_val, hr_low, hr_high = bootstrap_ci(
                    hits,
                    lambda h: calculate_hit_rate(h, key, ret_key, threshold=1.0),
                )
                hr_pval = permutation_test_hit_rate(hits, key, ret_key)
                hit_count = len(hits)
            else:
                hits = [r for r in records if r[key] != 0]
                hr_val, hr_low, hr_high = bootstrap_ci(
                    hits,
                    lambda h: calculate_hit_rate(h, key, ret_key, threshold=0.0001),
                )
                hr_pval = permutation_test_hit_rate(hits, key, ret_key)
                hit_count = len(hits)

            m_dict[key] = {
                "name": name,
                "rank_ic": round(ic_val, 4),
                "rank_ic_95ci": [round(ic_low, 4), round(ic_high, 4)],
                "rank_ic_pvalue": round(p_val, 4),
                "actionable_signal_count": hit_count,
                "directional_hit_rate_pct": round(hr_val * 100, 1),
                "hit_rate_95ci": [round(hr_low * 100, 1), round(hr_high * 100, 1)],
                "hit_rate_pvalue": round(hr_pval, 4),
            }

        # Model Deltas: MAD vs STD, MAD vs Raw
        delta_mad_std, d_low, d_high = bootstrap_ci(
            records,
            lambda recs: spearman_rank_ic([r["z_mad"] for r in recs], [r[ret_key] for r in recs])
            - spearman_rank_ic([r["z_std"] for r in recs], [r[ret_key] for r in recs]),
        )
        m_dict["deltas"] = {
            "mad_minus_std_ic": round(delta_mad_std, 4),
            "mad_minus_std_95ci": [round(d_low, 4), round(d_high, 4)],
            "significant_difference_std": (d_low > 0 or d_high < 0),
        }
        horse_race[f"{m}m"] = m_dict

    # 2. Clustered / De-duplicated Horizon Comparison (Eliminating NFP + Unemployment Double-Counting)
    clustered_race: Dict[str, Any] = {}
    for m in horizons:
        ret_key = f"ret_{m}m"
        rets_c = [r[ret_key] for r in clustered]
        c_dict: Dict[str, Any] = {}
        for key, name in models:
            scores_c = [r[key] for r in clustered]
            ic_val, ic_low, ic_high = bootstrap_ci(
                list(zip(scores_c, rets_c)),
                lambda s: spearman_rank_ic([x[0] for x in s], [x[1] for x in s]),
            )
            if key in ("z_mad", "z_std"):
                hits_c = [r for r in clustered if abs(r[key]) >= 1.0]
                hr_val, hr_low, hr_high = bootstrap_ci(
                    hits_c,
                    lambda h: calculate_hit_rate(h, key, ret_key, threshold=1.0),
                )
            else:
                hits_c = [r for r in clustered if r[key] != 0]
                hr_val, hr_low, hr_high = bootstrap_ci(
                    hits_c,
                    lambda h: calculate_hit_rate(h, key, ret_key, threshold=0.0001),
                )

            c_dict[key] = {
                "rank_ic": round(ic_val, 4),
                "rank_ic_95ci": [round(ic_low, 4), round(ic_high, 4)],
                "hit_count": len(hits_c),
                "directional_hit_rate_pct": round(hr_val * 100, 1),
                "hit_rate_95ci": [round(hr_low * 100, 1), round(hr_high * 100, 1)],
            }
        clustered_race[f"{m}m"] = c_dict

    # 3. Transaction Costs / Net EV Analysis (+30m horizon as baseline execution window)
    ret_30 = "ret_30m" if "ret_30m" in records[0] else f"ret_{horizons[0]}m"
    costs_analysis = {
        "gross_0bps": calculate_net_returns(records, "z_mad", ret_30, threshold=1.0, cost_bps=0.0),
        "low_cost_10bps_1pip": calculate_net_returns(records, "z_mad", ret_30, threshold=1.0, cost_bps=10.0),
        "news_cost_15bps_1.5pips": calculate_net_returns(records, "z_mad", ret_30, threshold=1.0, cost_bps=15.0),
        "std_news_cost_15bps": calculate_net_returns(records, "z_std", ret_30, threshold=1.0, cost_bps=15.0),
    }

    # 4. Indicator x Year Decomposition Matrix
    decomposition: Dict[str, Any] = {}
    unique_inds = sorted({r["indicator"] for r in records})
    unique_years = sorted({r["year"] for r in records})
    for ind in unique_inds:
        ind_records = [r for r in records if r["indicator"] == ind]
        ind_dict: Dict[str, Any] = {"total_n": len(ind_records), "by_year": {}}
        for yr in unique_years:
            sub = [r for r in ind_records if r["year"] == yr]
            if not sub:
                continue
            r30 = [r[ret_30] for r in sub]
            zm = [r["z_mad"] for r in sub]
            zs = [r["z_std"] for r in sub]
            ind_dict["by_year"][str(yr)] = {
                "n": len(sub),
                "mad_ic": round(spearman_rank_ic(zm, r30), 4) if len(sub) >= 3 else 0.0,
                "std_ic": round(spearman_rank_ic(zs, r30), 4) if len(sub) >= 3 else 0.0,
                "mad_ge_1_signals": len([r for r in sub if abs(r["z_mad"]) >= 1.0]),
                "std_ge_1_signals": len([r for r in sub if abs(r["z_std"]) >= 1.0]),
            }
        decomposition[ind] = ind_dict

    return {
        "metadata": {
            "evaluation_time_utc": dt.datetime.now(UTC).isoformat(),
            "sample_size_total_events": n_events,
            "sample_size_clustered_instants": n_clusters,
            "tested_horizons_minutes": list(horizons),
            "simultaneous_duplicates_filtered": n_events - n_clusters,
        },
        "horse_race_4_models": horse_race,
        "clustered_de_duplicated_race": clustered_race,
        "net_of_cost_analysis": costs_analysis,
        "indicator_year_decomposition": decomposition,
    }


def print_falsification_report(res: Mapping[str, Any]) -> None:
    """Prints a clear, scientific console summary of the falsification tests."""
    meta = res.get("metadata", {})
    race = res.get("horse_race_4_models", {})
    clustered = res.get("clustered_de_duplicated_race", {})
    costs = res.get("net_of_cost_analysis", {})

    print("\n" + "=" * 95)
    print(f"EKONOMETRIK FALSIFIKASYON & STRES TESTI RAPORU (EUR/USD, N={meta.get('sample_size_total_events')}, Kumeler={meta.get('sample_size_clustered_instants')})")
    print("=" * 95)

    print("\n1. DORTLU AT YARISI (HORSE RACE) & BOOTSTRAP %95 GUVEN ARALIKLARI:")
    for h_key, data in race.items():
        print(f"\n--- Vade: +{h_key} ---")
        print(f"{'Model':<32} {'Rank IC':>8} {'%95 Guven Araligi':>22} {'p-degeri':>9} | {'Sinyal':>6} {'Isabet %':>9} {'%95 GA':>16}")
        print("-" * 110)
        for m_key in ["sign_surprise", "raw_surprise", "z_std", "z_mad"]:
            m = data.get(m_key, {})
            ci = m.get("rank_ic_95ci", [0.0, 0.0])
            hr_ci = m.get("hit_rate_95ci", [0.0, 0.0])
            print(
                f"{m.get('name', m_key):<32} {m.get('rank_ic', 0.0):>+8.4f} [{ci[0]:>+7.4f}, {ci[1]:>+7.4f}] {m.get('rank_ic_pvalue', 0.0):>8.4f} | "
                f"{m.get('actionable_signal_count', 0):>6} {m.get('directional_hit_rate_pct', 0.0):>8.1f}% [{hr_ci[0]:>5.1f}%, {hr_ci[1]:>5.1f}%]"
            )
        deltas = data.get("deltas", {})
        d_ci = deltas.get("mad_minus_std_95ci", [0.0, 0.0])
        sig = "ANLAMLI FARK VAR (p<0.05)" if deltas.get("significant_difference_std") else "ISTATISTIKSEL ANLAMLI DEGIL (0 iceriyor)"
        print(f"Delta(MAD - STD) IC: {deltas.get('mad_minus_std_ic', 0.0):>+7.4f} [%95 GA: {d_ci[0]:>+7.4f}, {d_ci[1]:>+7.4f}] -> {sig}")

    print("\n2. ESZAMANLI OLAY KUMELEMESI (DE-DUPLICATION) KONTROLU:")
    print(f"Toplam {meta.get('sample_size_total_events')} olay, {meta.get('simultaneous_duplicates_filtered')} eszamanli cifte-sayim ayiklanarak {meta.get('sample_size_clustered_instants')} tekil an kumesine indirgendi.")
    for h_key, data in clustered.items():
        m_mad = data.get("z_mad", {})
        m_std = data.get("z_std", {})
        ci_m = m_mad.get("rank_ic_95ci", [0.0, 0.0])
        hr_ci_m = m_mad.get("hit_rate_95ci", [0.0, 0.0])
        print(
            f"+{h_key:<6} | MAD Kumelenmis IC: {m_mad.get('rank_ic', 0.0):>+7.4f} [{ci_m[0]:>+6.4f}, {ci_m[1]:>+6.4f}] | "
            f"Isabet (N={m_mad.get('hit_count')}): {m_mad.get('directional_hit_rate_pct', 0.0):>5.1f}% [{hr_ci_m[0]:>4.1f}%, {hr_ci_m[1]:>4.1f}%]"
        )

    print("\n3. ISLEM MALIYETI & SPREAD/SLIPPAGE KESINTISI (NET EXPECTED VALUE):")
    print(f"{'Maliyet Senaryosu':<32} {'Islem Sayisi':>14} {'Brut Ort bps':>14} {'Net Ort bps':>14} {'Net Isabet %':>14} {'Profit Factor':>14}")
    print("-" * 105)
    for c_key, label in [
        ("gross_0bps", "Brut (Sifir Maliyet)"),
        ("low_cost_10bps_1pip", "Normal Spread (1.0 pip / 10 bps)"),
        ("news_cost_15bps_1.5pips", "Haber Ani Spike (1.5 pip / 15 bps)"),
        ("std_news_cost_15bps", "STD Modeli (1.5 pip Spike)"),
    ]:
        c = costs.get(c_key, {})
        print(
            f"{label:<32} {c.get('trade_count', 0):>14} {c.get('mean_gross_bps', 0.0):>+13.2f}b {c.get('mean_net_bps', 0.0):>+13.2f}b "
            f"{c.get('net_win_rate_pct', 0.0):>13.1f}% {c.get('profit_factor', 0.0):>14.2f}"
        )
    print("=" * 95 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ekonometrik Falsifikasyon & Stres Testi Motoru")
    parser.add_argument("--observations", type=Path, default=Path(__file__).with_name("surprise_observations.csv"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("falsification_stress_test.json"))
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--timeframe", default="M15", choices=["M5", "M15", "M30", "H1"])
    parser.add_argument("--count", type=int, default=65000)
    args = parser.parse_args()

    tf_horizons = {
        "M5": (5, 15, 30, 60, 240),
        "M15": (15, 30, 60, 240),
        "M30": (30, 60, 240),
        "H1": (60, 240),
    }
    horizons = tf_horizons.get(args.timeframe.upper(), (15, 30, 60, 240))

    print(f"[*] MetaTrader 5 uzerinden {args.symbol} {args.timeframe} barlari cekiliyor...")
    bars = fetch_mt5_bars(args.symbol, timeframe=args.timeframe, count=args.count)
    if not bars:
        raise SystemExit(f"MT5 {args.timeframe} barlari cekilemedi.")

    print(f"[+] {len(bars)} bar yuklendi. Olaylar hizalaniyor ve 4-model karsilastirmasi yapiliyor...")
    records = extract_event_records(args.observations, bars, horizons=horizons)
    print(f"[+] {len(records)} olay basariyla hizalandi. Bootstrap (N=2000) ve permutasyon (N=1000) calistiriliyor...")

    report = run_falsification_analysis(records, horizons=horizons)

    with args.output.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"[+] Sonuclar kaydedildi: {args.output}")

    print_falsification_report(report)


if __name__ == "__main__":
    main()

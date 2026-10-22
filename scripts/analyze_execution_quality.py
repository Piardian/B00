"""Read-only diagnostics of existing trades; never generates entries or returns."""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import statistics
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sfp_orb_engine.execution_policy import NO_FILL_REASONS, utc_time, TRT
from sfp_orb_engine.outcome_tracker import get_friction_config
from sfp_orb_engine.config import is_market_open


def read_bars(database, symbol, start, end):
    if not database.exists():
        return [], 0
    with sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True) as db:
        rows = db.execute("""SELECT bar_time, high, low, first_seen_at FROM bars
            WHERE symbol=? AND timeframe='1m' AND bar_time>=? AND bar_time<?
            ORDER BY bar_time, first_seen_at, rowid""", (symbol, start.isoformat(), end.isoformat())).fetchall()
    # Revisions are a data-quality warning, never silently averaged.
    unique = {}
    revisions = 0
    for time, high, low, seen in rows:
        if time in unique:
            revisions += 1
        unique[time] = {"time": utc_time(time), "high": high, "low": low}
    return list(unique.values()), revisions


def expected_times(symbol, start, end):
    return {t.to_pydatetime() for t in pd.date_range(start, end, freq="min", inclusive="left")
            if is_market_open(symbol, t.to_pydatetime())}


def measure_trade(trade, database, now):
    entry, sl = float(trade["entry"]), float(trade["original_sl"])
    risk = abs(entry - sl)
    friction = get_friction_config(trade["symbol"])
    result = {"id": trade["id"], "symbol": trade["symbol"], "reason": trade.get("close_reason"),
              "net_r_recorded": trade.get("net_r"), "policy": trade.get("policy_version", "legacy"),
              "modeled_spread_buffer_r": entry * friction["spread_ratio"] / risk,
              "modeled_fee_r": trade.get("fee_r", friction["fee_r"]),
              "actual_bid_ask_cost_r": None, "mfe_r": None, "mae_r": None}
    if not trade.get("filled_at"):
        result["excursion_status"] = "NO_FILL_TIMESTAMP"
        return result
    sources = []
    if database.exists():
        with sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True) as db:
            sources = [row[0] for row in db.execute("SELECT DISTINCT source FROM bars WHERE symbol=? AND timeframe='1m'", (trade["symbol"],))]
    retrospective = any("historical_yahoo_1m" in source for source in sources)
    verified_qqq_proxy = bool(sources) and all("ticker=QQQ" in source for source in sources)
    if retrospective and (trade["symbol"] == "XAU/USD" or (trade["symbol"] == "NAS100" and not verified_qqq_proxy)):
        result.update(price_series_status="REJECTED_INSTRUMENT_PROXY",
                      excursion_status="REJECTED_INSTRUMENT_PROXY", post_exit_status="REJECTED_INSTRUMENT_PROXY",
                      price_quality_reason="Historical series is a gold futures or unverified Nasdaq proxy; original instrument parity is unproven")
        return result
    filled = utc_time(trade["filled_at"], legacy_local=True)
    closed = utc_time(trade["closed_at"], legacy_local=True)
    start = pd.Timestamp(filled).ceil("min").to_pydatetime()
    end = pd.Timestamp(closed).floor("min").to_pydatetime()
    bars, revisions = read_bars(database, trade["symbol"], start, end)
    # A gross scale discrepancy invalidates comparison even if all minutes exist.
    if bars:
        anchor = statistics.median((b["high"] + b["low"]) / 2 for b in bars[:5])
        result["provider_anchor_to_recorded_entry_ratio"] = anchor / entry
        if not .8 <= anchor / entry <= 1.2:
            result.update(price_series_status="REJECTED_PRICE_SCALE_MISMATCH",
                          excursion_status="REJECTED_PRICE_SCALE_MISMATCH", post_exit_status="REJECTED_PRICE_SCALE_MISMATCH")
            return result
    result["price_series_status"] = "NOMINAL_SYMBOL_ONLY_ORIGINAL_FEED_UNVERIFIED"
    expected = expected_times(trade["symbol"], start, end)
    actual = {b["time"] for b in bars}
    exact_boundaries = filled == start and closed == end
    complete = bool(expected) and expected <= actual and not revisions and exact_boundaries
    result.update(excursion_status="COMPLETE" if complete else "INSUFFICIENT_OR_AMBIGUOUS_HISTORY",
                  observed_trade_minutes=len(bars), expected_trade_minutes=len(expected), revised_trade_bars=revisions)
    covered_interior = bool(expected) and expected <= actual and not revisions
    if covered_interior:
        long = trade["direction"] == "LONG"
        favorable = [((b["high"] - entry) if long else (entry - b["low"])) / risk for b in bars]
        adverse = [((entry - b["low"]) if long else (b["high"] - entry)) / risk for b in bars]
        result["recorded_window_mfe_r"] = max(0., max(favorable))
        result["recorded_window_mae_r"] = max(0., max(adverse))
        result["recorded_window_semantics"] = "Provider 1m bounds between recorded fill/exit; excludes partial boundary minutes; not exact original execution"
    if complete:
        # OHLC of the exit bar may contain movement after the actual threshold.
        result["mfe_r"] = max(0., max(favorable))
        result["mae_r"] = max(0., max(adverse))
        result["excursion_semantics"] = "1m bar bounds; exit-bar path/order remains unknown"
    if trade.get("close_reason") not in {"STOP_LOSS", "TRAILING_STOP"}:
        return result
    post_start = pd.Timestamp(closed).ceil("min").to_pydatetime()
    post_end = post_start + timedelta(hours=4)
    available_end = min(post_end, pd.Timestamp(now).floor("min").to_pydatetime())
    post, revisions = read_bars(database, trade["symbol"], post_start, available_end)
    expected = expected_times(trade["symbol"], post_start, post_end)
    actual = {b["time"] for b in post}
    ready = now >= post_end and bool(expected) and expected <= actual and not revisions
    result["post_exit_status"] = "COMPLETE" if ready else ("WAITING_FOR_4H" if now < post_end else "INCOMPLETE_HISTORY")
    result["post_exit_observed_minutes"] = len(post)
    result["post_exit_expected_minutes"] = len(expected)
    result["tp1_within_4h"] = None
    result["tp2_within_4h"] = None
    result["original_sl_before_tp2"] = None
    if not ready:
        return result
    long = trade["direction"] == "LONG"
    spread = entry * friction["spread_ratio"]
    tp1 = float(trade["tp1"]) + (spread if long else -spread)
    tp2 = float(trade["tp2"]) + (spread if long else -spread)
    hit = lambda b, level: b["high"] >= level if long else b["low"] <= level
    result["tp1_within_4h"] = any(hit(b, tp1) for b in post)
    result["tp2_within_4h"] = any(hit(b, tp2) for b in post)
    first_target = next((b["time"] for b in post if hit(b, tp2)), None)
    first_stop = next((b["time"] for b in post if (b["low"] <= sl if long else b["high"] >= sl)), None)
    result["original_sl_before_tp2"] = bool(first_stop and (first_target is None or first_stop <= first_target))
    result["same_bar_order_ambiguous"] = bool(first_stop and first_stop == first_target)
    return result


def build_report(ledger, database, start, end, now=None):
    now = utc_time(now or datetime.now(timezone.utc))
    selected = [t for t in ledger if t.get("close_reason") not in NO_FILL_REASONS
                and t.get("closed_at") and start <= utc_time(t["closed_at"], legacy_local=True) < end]
    measured = [measure_trade(t, database, now) for t in selected]
    ratios = [t["modeled_spread_buffer_r"] for t in measured]
    buckets = []
    for label, low, high in [("<=0.15R", -1., .15), ("0.15–0.30R", .15, .30), (">0.30R", .30, float("inf"))]:
        group = [t for t in measured if low < t["modeled_spread_buffer_r"] <= high]
        buckets.append({"bucket": label, "trades": len(group),
                        "stops": sum(t["reason"] == "STOP_LOSS" for t in group),
                        "recorded_net_r": round(sum(float(t["net_r_recorded"] or 0) for t in group), 6)})
    post_groups = []
    for reason in ("STOP_LOSS", "TRAILING_STOP"):
        group = [t for t in measured if t["reason"] == reason]
        complete_group = [t for t in group if t.get("post_exit_status") == "COMPLETE"]
        post_groups.append({"reason": reason, "eligible": len(group), "complete": len(complete_group),
                            "tp1_within_4h": sum(bool(t["tp1_within_4h"]) for t in complete_group),
                            "tp2_within_4h": sum(bool(t["tp2_within_4h"]) for t in complete_group),
                            "tp2_before_original_sl_unambiguous": sum(bool(t["tp2_within_4h"]) and not t["original_sl_before_tp2"] and not t.get("same_bar_order_ambiguous") for t in complete_group)})
    sources = []
    if database.exists():
        with sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True) as db:
            sources = [row[0] for row in db.execute("SELECT DISTINCT source FROM bars")]
    return {"created_at": now.isoformat(), "start_utc": start.isoformat(), "end_utc_exclusive": end.isoformat(),
            "scope": "Existing ledger diagnostics, not a backtest or an optimization",
            "price_sources": sources,
            "trades": len(measured), "policy_counts": dict(Counter(t["policy"] for t in measured)),
            "modeled_spread_buffer_r_median": statistics.median(ratios) if ratios else None,
            "modeled_spread_buffer_r_max": max(ratios) if ratios else None,
            "cost_buckets_exploratory": buckets,
            "complete_excursion_count": sum(t["excursion_status"] == "COMPLETE" for t in measured),
            "covered_recorded_window_count": sum("recorded_window_mfe_r" in t for t in measured),
            "complete_post_exit_count": sum(t.get("post_exit_status") == "COMPLETE" for t in measured),
            "rejected_price_comparisons": sum(t.get("price_series_status", "").startswith("REJECTED") for t in measured),
            "post_exit_groups": post_groups,
            "actual_cost_observations": 0, "details": measured}


def render_report(report):
    median = report["modeled_spread_buffer_r_median"]
    lines = ["# İşlem kalitesi ölçümü", "", f"İncelenen gerçekleşmiş kapanış: **{report['trades']}**.",
             f"Sürüm dağılımı: `{report['policy_counts']}`.", "",
             "Bu çalışma mevcut işlem defterinin ölçümüdür; backtest veya yeni filtre denemesi değildir.", "",
             f"Modeldeki spread tamponu / başlangıç stop mesafesi medyanı: **{median:.3f}R**." if median is not None else "Henüz ölçülecek gerçekleşmiş işlem yok.",
             "Gerçek bid/ask ve broker slipajı ölçülmedi. Tampon mesafesi gerçekleşmiş maliyet gibi toplanmaz.", "",
             "| Model tamponu / stop | İşlem | Stop | Kayıtlı net R |", "|---|---:|---:|---:|"]
    for row in report["cost_buckets_exploratory"]:
        lines.append(f"| {row['bucket']} | {row['trades']} | {row['stops']} | {row['recorded_net_r']:+.2f} |")
    lines += ["", "Gruplar keşif amaçlıdır; nedensellik veya yeni bir eleme eşiği kanıtlamaz.", "",
              f"Fiyat kaynakları: `{report['price_sources']}`.",
              f"Enstrüman/proxy veya fiyat ölçeği nedeniyle reddedilen karşılaştırma: **{report['rejected_price_comparisons']}**.",
              f"Tam 1m iç hareket kapsamı olan işlem: **{report['complete_excursion_count']}**.",
              f"Kayıtlı dolum/kapanış arasındaki tam dakika penceresi kapsanan işlem: **{report['covered_recorded_window_count']}** (gerçek girişten itibaren kesin MAE/MFE değildir).",
              f"Çıkış sonrası 4 saati eksiksiz izlenen işlem: **{report['complete_post_exit_count']}**.",
              "Eksik geçmiş, belirsiz eski zaman damgası veya aynı mum içi sıra için sonuç uydurulmaz. MAE/MFE varsa 1m mum sınırlarıdır; çıkış anından sonraki fitili içerebilir.", "",
              "Stop ve trailing çıkışlarından sonra özgün TP1/TP2 seviyeleri sabit 4 saat gözlenir. Bu takip yeni pozisyon açmaz; alternatif kâr/zarar üretmez.",
              "Yeni arşiv yalnızca gözlendiği andan itibaren kaynak sağlar; 2025 makro kararları geriye dönük oluşturulamaz."]
    lines += ["", "| Çıkış | Toplam | Tam 4h kapsam | Sonra TP1 | Sonra TP2 | TP2, özgün SL'den önce ve belirsizliksiz |",
              "|---|---:|---:|---:|---:|---:|"]
    for row in report["post_exit_groups"]:
        lines.append(f"| {row['reason']} | {row['eligible']} | {row['complete']} | {row['tp1_within_4h']} | {row['tp2_within_4h']} | {row['tp2_before_original_sl_unambiguous']} |")
    lines += ["", "Bu sayılar takip gözlemidir; stopu/trailing'i kaldırarak elde edilecek ek kâr sayılmaz. Sonradan indirilen farklı fiyat kaynağı, özgün canlı fiyat yolunun birebir kanıtı değildir."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="Inclusive TRT date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Exclusive TRT date YYYY-MM-DD")
    parser.add_argument("--database", type=Path, default=ROOT / "data/execution_observations.sqlite3")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.with_suffix(".json").exists() or args.output.with_suffix(".md").exists():
        raise SystemExit("Choose a fresh output name")
    ledger = json.loads((ROOT / "data/trade_ledger.json").read_text(encoding="utf-8"))
    start = datetime.fromisoformat(args.start).replace(tzinfo=TRT).astimezone(timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=TRT).astimezone(timezone.utc)
    result = build_report(ledger, args.database, start, end)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    args.output.with_suffix(".md").write_text(render_report(result), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "details"}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()

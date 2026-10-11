"""Compatibility entrypoint for event-time aligned market-response validation.

The previous implementation mixed UTC MT5 bars with broker-hour approximations. The
canonical implementation now lives in ``market_response_validation_v2`` and uses
DST-aware America/New_York release timestamps plus M5 bars.
"""

from .market_response_validation_v2 import (
    HORIZONS_MINUTES,
    audit_event_timestamp,
    build_records,
    calculate_usd_return_bps,
    fetch_mt5_m5_bars,
    parse_observation_event_utc,
    run_market_response_analysis,
    spearman_rank_ic,
    summarize,
)

# Public compatibility alias. The old helper name is retained, but now returns the
# correctly reconstructed UTC event date/hour rather than broker-server time.
def resolve_event_datetime(row):
    event_utc = parse_observation_event_utc(row)
    return event_utc.date(), event_utc.hour


def calculate_usd_returns(p0, p_close, quote_currency_is_usd=True):
    if quote_currency_is_usd:
        return calculate_usd_return_bps(p0, p_close)
    if p0 <= 0:
        return 0.0
    return (p_close - p0) / p0 * 10000.0


def classify_bucket(z):
    if z < -2.0:
        return "1_strong_neg"
    if z < -1.0:
        return "2_mod_neg"
    if z <= 1.0:
        return "3_in_line"
    if z <= 2.0:
        return "4_mod_pos"
    return "5_strong_pos"


def rank_data(seq):
    indexed = sorted(enumerate(seq), key=lambda item: item[1])
    ranks = [0.0] * len(seq)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg
        i = j + 1
    return ranks


def compute_bucket_metrics(records, z_key, ret_key="ret_30m"):
    labels = {
        "1_strong_neg": "1. Strong Neg (Z < -2.0)",
        "2_mod_neg": "2. Mod Neg (-2.0 <= Z < -1.0)",
        "3_in_line": "3. In-Line (-1.0 <= Z <= +1.0)",
        "4_mod_pos": "4. Mod Pos (+1.0 < Z <= +2.0)",
        "5_strong_pos": "5. Strong Pos (Z > +2.0)",
    }
    out = {}
    for key, label in labels.items():
        values = []
        for row in records:
            if classify_bucket(float(row[z_key])) == key:
                values.append(float(row[ret_key]))
        out[key] = {
            "label": label,
            "count": len(values),
            "mean_usd_bps": round(sum(values) / len(values), 2) if values else 0.0,
        }
    return out


if __name__ == "__main__":
    from .market_response_validation_v2 import main
    main()

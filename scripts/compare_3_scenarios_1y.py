"""
🌺 Begonya 00 - 1 Yıllık 3 Senaryo Karşılaştırmalı Backtest Simülasyonu
Periyot: 10 Ekim 2025 - 10 Ekim 2026 (Tam 1 Yıl)
Hedefler: TP1 = 1.5R (%50 Kâr Al + BE) / TP2 = 3.0R (Kalan %50)
Model: Model 2 (London Judas - Asya Uçları) + %45 Fitil + Grade A+/AAA

3 SENARYO:
1. Senaryo: Yalnızca Hafta İçi (Pazartesi - Cuma, Londra 07-11 UTC + NY 13-17 UTC)
2. Senaryo: 7/24 Açık (Hafta içi FX+Kripto, Hafta sonu Kripto 7/24)
3. Senaryo: Hafta İçi Yalnızca New York Killzone (Pazartesi - Cuma, Yalnızca 13-17 UTC)
"""

import json
import sys
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sfp_orb_engine.multi_period_backtest import MultiPeriodBacktestRunner
from sfp_orb_engine.config import get_asset_sl_buffer

ALL_SYMBOLS = [
    # Forex & Endeksler
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", "USDCAD", "NZDUSD", "EURJPY",
    "NAS100", "XAUUSD",
    # Kriptolar
    "BTCUSD", "ETHUSD", "SOLUSD", "LTCUSD", "XRPUSD"
]

runner = MultiPeriodBacktestRunner(symbols=ALL_SYMBOLS)
df_map = {s: runner.fetch_full_history(s, 70000) for s in ALL_SYMBOLS}

def run_scenario(scenario_type):
    """
    scenario_type:
    - 'weekday_all_sessions': Hafta içi (Londra 07-11 UTC + NY 13-17 UTC)
    - '24_7_crypto': Hafta içi FX+Kripto, Hafta sonu Kriptolar açık
    - 'ny_killzone_only': Hafta içi Yalnızca New York Killzone (13-17 UTC)
    """
    all_trades = []
    start_dt = '2025-10-10'
    end_dt = '2026-10-10'

    for s in ALL_SYMBOLS:
        df = df_map.get(s)
        if df is None:
            continue
        n = len(df)
        opens = df['open'].values
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        ashs = df['ash'].values
        asls = df['asl'].values
        atrs = df['atr'].values
        ema50s = df['htf_ema50'].values
        ema200s = df['htf_ema200'].values
        hours = df['hour'].values
        weekdays = df['datetime'].dt.weekday.values
        dts = df['datetime'].dt.strftime('%Y-%m-%d %H:%M').values

        display_sym = f'{s[:3]}/{s[3:]}' if len(s) == 6 and s.isalpha() else s
        sl_buffer_atr = get_asset_sl_buffer(display_sym)
        is_crypto = any(k in s for k in ['BTC', 'ETH', 'SOL', 'LTC', 'XRP'])

        i = 800
        while i < n - 40:
            dt_str = dts[i]
            if dt_str < start_dt or dt_str > end_dt:
                i += 1
                continue

            wday = weekdays[i]
            hour = hours[i]

            # --- SENARYO FİLTRELERİ ---
            if scenario_type == 'weekday_all_sessions':
                if wday >= 5:
                    i += 1
                    continue
                if not ((7 <= hour <= 11) or (13 <= hour <= 17)):
                    i += 1
                    continue

            elif scenario_type == '24_7_crypto':
                # Hafta sonu ise sadece kriptolara izin ver
                if wday >= 5 and not is_crypto:
                    i += 1
                    continue
                # Seans pencereleri
                if not ((7 <= hour <= 11) or (13 <= hour <= 17)):
                    i += 1
                    continue

            elif scenario_type == 'ny_killzone_only':
                if wday >= 5:
                    i += 1
                    continue
                # YALNIZCA NEW YORK KILLZONE (13:00 - 17:00 UTC)
                if not (13 <= hour <= 17):
                    i += 1
                    continue

            c = closes[i]
            h = highs[i]
            l = lows[i]
            atr = atrs[i]
            ash = ashs[i]
            asl = asls[i]

            htf_bull = ema50s[i] > ema200s[i]
            htf_bear = ema50s[i] < ema200s[i]

            bar_rng = max(h - l, 1e-8)
            upper_wick = (h - max(opens[i], c)) / bar_rng
            lower_wick = (min(opens[i], c) - l) / bar_rng

            # MODEL 2: Asya Uçları Süpürmesi + %45 Fitil
            sweep_high = False
            sweep_low = False
            pool_name = ''
            if upper_wick >= 0.45 and ash > 0.0 and h > ash and c < ash:
                sweep_high = True
                pool_name = 'ASIAN_HIGH'
            elif lower_wick >= 0.45 and asl > 0.0 and l < asl and c > asl:
                sweep_low = True
                pool_name = 'ASIAN_LOW'

            is_mom = is_crypto or (s in ['NAS100', 'XAUUSD'])
            allow_short = htf_bear if is_mom else (not htf_bull)
            allow_long = htf_bull if is_mom else (not htf_bear)

            # SHORT İŞLEM KURGUSU (TP1: 1.5R / TP2: 3.0R)
            if sweep_high and allow_short:
                peak = h
                mss_trig = min(l, lows[i-1])
                mss_ok, entry_idx = False, -1
                for k in range(1, 4):
                    if i + k < n and closes[i+k] < mss_trig:
                        b_rng = max(highs[i+k] - lows[i+k], 1e-8)
                        if abs(closes[i+k] - opens[i+k]) / b_rng >= 0.35:
                            mss_ok, entry_idx = True, i + k
                            break

                if mss_ok:
                    has_fvg = (lows[entry_idx - 2] > highs[entry_idx]) and ((lows[entry_idx - 2] - highs[entry_idx]) >= atr * 0.10)
                    grade = 'AAA' if (htf_bear and has_fvg) else ('A+' if (htf_bear or has_fvg) else 'A')
                    if grade in ['AAA', 'A+']:
                        entry = closes[entry_idx]
                        sl = peak + (atr * sl_buffer_atr)
                        risk = max(sl - entry, atr * 0.2)
                        tp1 = entry - (risk * 1.5)
                        tp2 = entry - (risk * 3.0)

                        cur_sl = sl
                        pos_status = 'OPEN'
                        for m in range(entry_idx + 1, min(entry_idx + 120, n)):
                            bl = lows[m]
                            bh = highs[m]

                            if bl <= tp1 and pos_status == 'OPEN':
                                pos_status = 'TP1_HIT'
                                cur_sl = entry

                            if bl <= tp2:
                                all_trades.append({
                                    'symbol': s, 'direction': 'SHORT', 'grade': grade, 'pool': pool_name,
                                    'r_result': 2.25, 'reason': 'TP2_HIT', 'opened_at': dts[i], 'is_crypto': is_crypto
                                })
                                i = m + 4
                                break
                            elif bh >= cur_sl:
                                if pos_status == 'TP1_HIT':
                                    r_res = 0.75
                                    reas = 'BREAK_EVEN'
                                else:
                                    r_res = -1.0
                                    reas = 'STOP_LOSS'

                                all_trades.append({
                                    'symbol': s, 'direction': 'SHORT', 'grade': grade, 'pool': pool_name,
                                    'r_result': r_res, 'reason': reas, 'opened_at': dts[i], 'is_crypto': is_crypto
                                })
                                i = m + 4
                                break

            # LONG İŞLEM KURGUSU (TP1: 1.5R / TP2: 3.0R)
            elif sweep_low and allow_long:
                valley = l
                mss_trig = max(h, highs[i-1])
                mss_ok, entry_idx = False, -1
                for k in range(1, 4):
                    if i + k < n and closes[i+k] > mss_trig:
                        b_rng = max(highs[i+k] - lows[i+k], 1e-8)
                        if abs(closes[i+k] - opens[i+k]) / b_rng >= 0.35:
                            mss_ok, entry_idx = True, i + k
                            break

                if mss_ok:
                    has_fvg = (lows[entry_idx] > highs[entry_idx - 2]) and ((lows[entry_idx] - highs[entry_idx - 2]) >= atr * 0.10)
                    grade = 'AAA' if (htf_bull and has_fvg) else ('A+' if (htf_bull or has_fvg) else 'A')
                    if grade in ['AAA', 'A+']:
                        entry = closes[entry_idx]
                        sl = valley - (atr * sl_buffer_atr)
                        risk = max(entry - sl, atr * 0.2)
                        tp1 = entry + (risk * 1.5)
                        tp2 = entry + (risk * 3.0)

                        cur_sl = sl
                        pos_status = 'OPEN'
                        for m in range(entry_idx + 1, min(entry_idx + 120, n)):
                            bh = highs[m]
                            bl = lows[m]

                            if bh >= tp1 and pos_status == 'OPEN':
                                pos_status = 'TP1_HIT'
                                cur_sl = entry

                            if bh >= tp2:
                                all_trades.append({
                                    'symbol': s, 'direction': 'LONG', 'grade': grade, 'pool': pool_name,
                                    'r_result': 2.25, 'reason': 'TP2_HIT', 'opened_at': dts[i], 'is_crypto': is_crypto
                                })
                                i = m + 4
                                break
                            elif bl <= cur_sl:
                                if pos_status == 'TP1_HIT':
                                    r_res = 0.75
                                    reas = 'BREAK_EVEN'
                                else:
                                    r_res = -1.0
                                    reas = 'STOP_LOSS'

                                all_trades.append({
                                    'symbol': s, 'direction': 'LONG', 'grade': grade, 'pool': pool_name,
                                    'r_result': r_res, 'reason': reas, 'opened_at': dts[i], 'is_crypto': is_crypto
                                })
                                i = m + 4
                                break

            i += 1
    return all_trades


def analyze(trades, title):
    tot = len(trades)
    if tot == 0:
        return {'title': title, 'total_trades': 0}
    wins = sum(1 for t in trades if t['r_result'] > 0)
    tp2_cnt = sum(1 for t in trades if t['reason'] == 'TP2_HIT')
    be_cnt = sum(1 for t in trades if t['reason'] == 'BREAK_EVEN')
    losses = sum(1 for t in trades if t['r_result'] < 0)

    net_r = round(sum(t['r_result'] for t in trades), 2)
    wr = round(wins / tot * 100, 1)
    gw = sum(t['r_result'] for t in trades if t['r_result'] > 0)
    gl = abs(sum(t['r_result'] for t in trades if t['r_result'] < 0))
    pf = round(gw / max(gl, 1e-5), 2)
    exp = round(net_r / tot, 2)

    # Kripto vs FX Ayrımı
    c_trades = [t for t in trades if t['is_crypto']]
    fx_trades = [t for t in trades if not t['is_crypto']]

    c_net = round(sum(t['r_result'] for t in c_trades), 2)
    c_wr = round(sum(1 for t in c_trades if t['r_result'] > 0) / max(len(c_trades), 1) * 100, 1)
    c_pf = round(sum(t['r_result'] for t in c_trades if t['r_result'] > 0) / max(abs(sum(t['r_result'] for t in c_trades if t['r_result'] < 0)), 1e-5), 2)

    fx_net = round(sum(t['r_result'] for t in fx_trades), 2)
    fx_wr = round(sum(1 for t in fx_trades if t['r_result'] > 0) / max(len(fx_trades), 1) * 100, 1)
    fx_pf = round(sum(t['r_result'] for t in fx_trades if t['r_result'] > 0) / max(abs(sum(t['r_result'] for t in fx_trades if t['r_result'] < 0)), 1e-5), 2)

    # Sembol Dağılımı
    sym_reports = {}
    for s in ALL_SYMBOLS:
        st = [t for t in trades if t['symbol'] == s]
        if st:
            sw = sum(1 for t in st if t['r_result'] > 0)
            sl = sum(1 for t in st if t['r_result'] < 0)
            s_net = round(sum(t['r_result'] for t in st), 2)
            s_gw = sum(t['r_result'] for t in st if t['r_result'] > 0)
            s_gl = abs(sum(t['r_result'] for t in st if t['r_result'] < 0))
            sym_reports[s] = {
                'trades': len(st), 'wins': sw, 'losses': sl,
                'win_rate': round(sw / len(st) * 100, 1),
                'net_r': s_net, 'pf': round(s_gw / max(s_gl, 1e-5), 2)
            }

    return {
        'title': title,
        'total_trades': tot,
        'total_wins': wins,
        'tp2_full_wins': tp2_cnt,
        'tp1_be_half_wins': be_cnt,
        'total_losses': losses,
        'win_rate': wr,
        'net_portfolio_r': net_r,
        'profit_factor': pf,
        'expectancy_r': exp,
        'crypto_net_r': c_net,
        'crypto_trades': len(c_trades),
        'crypto_wr': c_wr,
        'crypto_pf': c_pf,
        'fx_net_r': fx_net,
        'fx_trades': len(fx_trades),
        'fx_wr': fx_wr,
        'fx_pf': fx_pf,
        'symbol_reports': sym_reports
    }

if __name__ == '__main__':
    print('Simulating 1. Senaryo (Hafta İçi - Londra + NY)...')
    t1 = run_scenario('weekday_all_sessions')
    r1 = analyze(t1, '1. Senaryo: Yalnızca Hafta İçi (Londra 07-11 UTC + NY 13-17 UTC)')

    print('Simulating 2. Senaryo (7/24 - Hafta Sonu Kripto Açık)...')
    t2 = run_scenario('24_7_crypto')
    r2 = analyze(t2, '2. Senaryo: 7/24 Açık (Hafta İçi FX+Kripto, Hafta Sonu Kriptolar 7/24)')

    print('Simulating 3. Senaryo (Hafta İçi Yalnızca NY Killzone)...')
    t3 = run_scenario('ny_killzone_only')
    r3 = analyze(t3, '3. Senaryo: Hafta İçi Yalnızca New York Killzone (13-17 UTC)')

    output = {
        'scenario_1_weekday': r1,
        'scenario_2_24_7': r2,
        'scenario_3_ny_only': r3
    }
    print(json.dumps(output, indent=2))

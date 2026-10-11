"""
🌺 Begonya 00 - Son 3 Aylık Hafta İçi 1:3 RR Backtest Simülasyonu
Periyot: 10 Temmuz 2026 - 10 Ekim 2026 (Tam 3 Ay)
Kriterler:
1. Yalnızca Hafta İçi (Pazartesi - Cuma)
2. Minimum 1:3 R Hedefi
3. Model 2 (London Judas - Asya Seansı Uçları) + %45 Fitil Barajı + Grade A+/AAA
"""

import json
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sfp_orb_engine.multi_period_backtest import MultiPeriodBacktestRunner
from sfp_orb_engine.config import get_asset_sl_buffer

runner = MultiPeriodBacktestRunner()
df_map = {s: runner.fetch_full_history(s, 70000) for s in runner.symbols}

def run_simulation(rr_target=3.0, be_at=0.0, use_partial=False):
    all_trades = []
    start_dt = '2026-07-10'
    end_dt = '2026-10-10'

    for s, df in df_map.items():
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

        i = 800
        while i < n - 40:
            dt_str = dts[i]
            if dt_str < start_dt or dt_str > end_dt:
                i += 1
                continue

            # TALİMAT: YALNIZCA HAFTAİÇİ İŞLEM AL (Pazartesi - Cuma)
            wday = weekdays[i]
            if wday >= 5:
                i += 1
                continue

            c = closes[i]
            h = highs[i]
            l = lows[i]
            atr = atrs[i]
            hour = hours[i]
            ash = ashs[i]
            asl = asls[i]

            htf_bull = ema50s[i] > ema200s[i]
            htf_bear = ema50s[i] < ema200s[i]

            bar_rng = max(h - l, 1e-8)
            upper_wick = (h - max(opens[i], c)) / bar_rng
            lower_wick = (min(opens[i], c) - l) / bar_rng

            # MODEL 2: YALNIZCA ASYA SEANSI UÇLARI (LONDON JUDAS) + %45 FITIL
            sweep_high = False
            sweep_low = False
            pool_name = ''
            if upper_wick >= 0.45 and (7 <= hour <= 11) and ash > 0.0 and h > ash and c < ash:
                sweep_high = True
                pool_name = 'ASIAN_HIGH'
            elif lower_wick >= 0.45 and (7 <= hour <= 11) and asl > 0.0 and l < asl and c > asl:
                sweep_low = True
                pool_name = 'ASIAN_LOW'

            is_mom = s in ['BTCUSD', 'ETHUSD', 'NAS100', 'XAUUSD']
            allow_short = htf_bear if is_mom else (not htf_bull)
            allow_long = htf_bull if is_mom else (not htf_bear)

            if not ((7 <= hour <= 11) or (13 <= hour <= 17)):
                i += 1
                continue

            # SHORT İŞLEM KURGUSU (1:3 RR)
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
                        tp = entry - (risk * rr_target)
                        be_price = entry - (risk * be_at) if be_at > 0 else entry

                        cur_sl = sl
                        pos_status = 'OPEN'
                        for m in range(entry_idx + 1, min(entry_idx + 120, n)):
                            bl = lows[m]
                            bh = highs[m]

                            if be_at > 0 and bl <= be_price and pos_status == 'OPEN':
                                pos_status = 'BE_REACHED'
                                cur_sl = entry

                            if bl <= tp:
                                r_res = round(0.5 * be_at + 0.5 * rr_target, 2) if use_partial else rr_target
                                all_trades.append({
                                    'symbol': s, 'direction': 'SHORT', 'grade': grade, 'pool': pool_name,
                                    'r_result': r_res, 'reason': 'TP_3R_HIT', 'opened_at': dts[i]
                                })
                                i = m + 4
                                break
                            elif bh >= cur_sl:
                                if pos_status == 'BE_REACHED':
                                    r_res = round(0.5 * be_at, 2) if use_partial else 0.0
                                    reas = 'BREAK_EVEN'
                                else:
                                    r_res = -1.0
                                    reas = 'STOP_LOSS'
                                all_trades.append({
                                    'symbol': s, 'direction': 'SHORT', 'grade': grade, 'pool': pool_name,
                                    'r_result': r_res, 'reason': reas, 'opened_at': dts[i]
                                })
                                i = m + 4
                                break

            # LONG İŞLEM KURGUSU (1:3 RR)
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
                        tp = entry + (risk * rr_target)
                        be_price = entry + (risk * be_at) if be_at > 0 else entry

                        cur_sl = sl
                        pos_status = 'OPEN'
                        for m in range(entry_idx + 1, min(entry_idx + 120, n)):
                            bh = highs[m]
                            bl = lows[m]

                            if be_at > 0 and bh >= be_price and pos_status == 'OPEN':
                                pos_status = 'BE_REACHED'
                                cur_sl = entry

                            if bh >= tp:
                                r_res = round(0.5 * be_at + 0.5 * rr_target, 2) if use_partial else rr_target
                                all_trades.append({
                                    'symbol': s, 'direction': 'LONG', 'grade': grade, 'pool': pool_name,
                                    'r_result': r_res, 'reason': 'TP_3R_HIT', 'opened_at': dts[i]
                                })
                                i = m + 4
                                break
                            elif bl <= cur_sl:
                                if pos_status == 'BE_REACHED':
                                    r_res = round(0.5 * be_at, 2) if use_partial else 0.0
                                    reas = 'BREAK_EVEN'
                                else:
                                    r_res = -1.0
                                    reas = 'STOP_LOSS'
                                all_trades.append({
                                    'symbol': s, 'direction': 'LONG', 'grade': grade, 'pool': pool_name,
                                    'r_result': r_res, 'reason': reas, 'opened_at': dts[i]
                                })
                                i = m + 4
                                break

            i += 1
    return all_trades


def summarize(trades, model_title):
    tot = len(trades)
    if tot == 0:
        return {'model': model_title, 'total': 0}
    wins = sum(1 for t in trades if t['r_result'] > 0)
    losses = sum(1 for t in trades if t['r_result'] < 0)
    bes = sum(1 for t in trades if t['r_result'] == 0)
    net_r = round(sum(t['r_result'] for t in trades), 2)
    wr = round(wins / tot * 100, 1)
    gw = sum(t['r_result'] for t in trades if t['r_result'] > 0)
    gl = abs(sum(t['r_result'] for t in trades if t['r_result'] < 0))
    pf = round(gw / max(gl, 1e-5), 2)
    exp = round(net_r / tot, 2)

    # Parite Karnesi
    syms = {}
    for s in runner.symbols:
        st = [t for t in trades if t['symbol'] == s]
        if st:
            sw = sum(1 for t in st if t['r_result'] > 0)
            sl = sum(1 for t in st if t['r_result'] < 0)
            s_net = round(sum(t['r_result'] for t in st), 2)
            s_gw = sum(t['r_result'] for t in st if t['r_result'] > 0)
            s_gl = abs(sum(t['r_result'] for t in st if t['r_result'] < 0))
            syms[s] = {
                'trades': len(st), 'wins': sw, 'losses': sl,
                'win_rate': round(sw / len(st) * 100, 1),
                'net_r': s_net, 'pf': round(s_gw / max(s_gl, 1e-5), 2)
            }

    # Havuz Karnesi
    pools = {}
    for p in ['ASIAN_LOW', 'ASIAN_HIGH']:
        pt = [t for t in trades if t['pool'] == p]
        if pt:
            pw = sum(1 for t in pt if t['r_result'] > 0)
            pools[p] = {
                'trades': len(pt), 'win_rate': round(pw / len(pt) * 100, 1),
                'net_r': round(sum(t['r_result'] for t in pt), 2)
            }

    # Grade Karnesi
    grades = {}
    for g in ['A+', 'AAA']:
        gt = [t for t in trades if t['grade'] == g]
        if gt:
            gw_cnt = sum(1 for t in gt if t['r_result'] > 0)
            grades[g] = {
                'trades': len(gt), 'win_rate': round(gw_cnt / len(gt) * 100, 1),
                'net_r': round(sum(t['r_result'] for t in gt), 2)
            }

    # Aylık Dağılım
    months = {}
    for t in sorted(trades, key=lambda x: str(x['opened_at'])):
        m_key = str(t['opened_at'])[:7]
        months[m_key] = round(months.get(m_key, 0.0) + t['r_result'], 2)

    return {
        'model': model_title,
        'period': 'Son 3 Ay (2026-07-10 - 2026-10-10) [Yalnızca Hafta İçi]',
        'total_trades': tot,
        'wins': wins,
        'losses': losses,
        'breakevens': bes,
        'win_rate': wr,
        'net_r': net_r,
        'profit_factor': pf,
        'expectancy_r': exp,
        'monthly_returns': months,
        'pool_breakdown': pools,
        'grade_breakdown': grades,
        'symbol_reports': syms
    }

if __name__ == '__main__':
    # 1. Saf 1:3 RR (Sabit 3.0R Hedef, BE Yok)
    t1 = run_simulation(rr_target=3.0, be_at=0.0, use_partial=False)
    r1 = summarize(t1, '1. Model: Saf 1:3 RR (Sabit 3.0R TP / -1.0R SL)')

    # 2. Korumalı 1:3 RR (1.5R'da BE Çek, 3.0R Hedef)
    t2 = run_simulation(rr_target=3.0, be_at=1.5, use_partial=False)
    r2 = summarize(t2, '2. Model: Korumalı 1:3 RR (1.5R BE Girişe Çek, 3.0R Hedef)')

    # 3. Dinamik 1:3 RR (1.5R %50 Kâr Al + BE, 3.0R Kalan %50)
    t3 = run_simulation(rr_target=3.0, be_at=1.5, use_partial=True)
    r3 = summarize(t3, '3. Model: Dinamik Kısmi Çıkışlı 1:3 RR (1.5R TP1 + BE, 3.0R TP2)')

    report = {
        'pure_1to3': r1,
        'protected_1to3': r2,
        'dynamic_partial_1to3': r3
    }
    print(json.dumps(report, indent=2))

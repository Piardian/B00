"""
🌺 Begonya 00 - Son 3 Aylık Hafta İçi TP1: 1.0R (%50 Kâr + BE) / TP2: 3.0R Backtesti
Periyot: 10 Temmuz 2026 - 10 Ekim 2026 (Tam 3 Ay)
Kriterler:
1. Yalnızca Hafta İçi (Pazartesi - Cuma)
2. TP1: 1.0 R (%50 Kâr Alınıp Stop Başabaşa (BE) Çekilecek -> +0.50 R Cepte)
3. TP2: 3.0 R (Kalan %50 3.0R'a Sürülecek -> Tam Başarıda +2.00 R Net)
4. Model 2 (London Judas - Asya Seansı Uçları) + %45 Fitil Barajı + Grade A+/AAA
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

def run_tp1_1r_tp2_3r():
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

            # SHORT İŞLEM KURGUSU (TP1: 1.0R / TP2: 3.0R)
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
                        tp1 = entry - (risk * 1.0)
                        tp2 = entry - (risk * 3.0)

                        cur_sl = sl
                        pos_status = 'OPEN'
                        for m in range(entry_idx + 1, min(entry_idx + 120, n)):
                            bl = lows[m]
                            bh = highs[m]

                            # TP1 Vuruldu (%50 Kâr Al: +0.50R, Stop'u Girişe Çek)
                            if bl <= tp1 and pos_status == 'OPEN':
                                pos_status = 'TP1_HIT'
                                cur_sl = entry

                            # TP2 Vuruldu (Kalan %50 Kâr Al: +1.50R -> Toplam +2.00R)
                            if bl <= tp2:
                                all_trades.append({
                                    'symbol': s, 'direction': 'SHORT', 'grade': grade, 'pool': pool_name,
                                    'r_result': 2.0, 'reason': 'TP2_HIT', 'opened_at': dts[i]
                                })
                                i = m + 4
                                break

                            # SL veya BE Vuruldu
                            elif bh >= cur_sl:
                                if pos_status == 'TP1_HIT':
                                    # TP1'de alınan %50 kâr cepte kaldı
                                    r_res = 0.50
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

            # LONG İŞLEM KURGUSU (TP1: 1.0R / TP2: 3.0R)
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
                        tp1 = entry + (risk * 1.0)
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
                                    'r_result': 2.0, 'reason': 'TP2_HIT', 'opened_at': dts[i]
                                })
                                i = m + 4
                                break

                            elif bl <= cur_sl:
                                if pos_status == 'TP1_HIT':
                                    r_res = 0.50
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


def summarize_report(trades):
    tot = len(trades)
    wins = sum(1 for t in trades if t['r_result'] > 0)
    tp2_wins = sum(1 for t in trades if t['reason'] == 'TP2_HIT')
    be_wins = sum(1 for t in trades if t['reason'] == 'BREAK_EVEN')
    losses = sum(1 for t in trades if t['r_result'] < 0)

    net_r = round(sum(t['r_result'] for t in trades), 2)
    wr = round(wins / tot * 100, 1) if tot > 0 else 0
    gw = sum(t['r_result'] for t in trades if t['r_result'] > 0)
    gl = abs(sum(t['r_result'] for t in trades if t['r_result'] < 0))
    pf = round(gw / max(gl, 1e-5), 2)
    exp = round(net_r / tot, 2) if tot > 0 else 0

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

    pools = {}
    for p in ['ASIAN_LOW', 'ASIAN_HIGH']:
        pt = [t for t in trades if t['pool'] == p]
        if pt:
            pw = sum(1 for t in pt if t['r_result'] > 0)
            pools[p] = {
                'trades': len(pt), 'win_rate': round(pw / len(pt) * 100, 1),
                'net_r': round(sum(t['r_result'] for t in pt), 2)
            }

    grades = {}
    for g in ['A+', 'AAA']:
        gt = [t for t in trades if t['grade'] == g]
        if gt:
            gw_cnt = sum(1 for t in gt if t['r_result'] > 0)
            grades[g] = {
                'trades': len(gt), 'win_rate': round(gw_cnt / len(gt) * 100, 1),
                'net_r': round(sum(t['r_result'] for t in gt), 2)
            }

    months = {}
    for t in sorted(trades, key=lambda x: str(x['opened_at'])):
        m_key = str(t['opened_at'])[:7]
        months[m_key] = round(months.get(m_key, 0.0) + t['r_result'], 2)

    return {
        'period': 'Son 3 Ay (2026-07-10 - 2026-10-10) [Yalnızca Hafta İçi]',
        'model_name': 'TP1: 1.0R (%50 + BE) / TP2: 3.0R (Kalan %50)',
        'total_trades': tot,
        'total_wins': wins,
        'tp2_full_wins': tp2_wins,
        'tp1_be_half_wins': be_wins,
        'total_losses': losses,
        'win_rate': wr,
        'net_portfolio_r': net_r,
        'profit_factor': pf,
        'expectancy_r': exp,
        'monthly_returns': months,
        'pool_breakdown': pools,
        'grade_breakdown': grades,
        'symbol_reports': syms
    }

if __name__ == '__main__':
    trades = run_tp1_1r_tp2_3r()
    report = summarize_report(trades)
    print(json.dumps(report, indent=2))

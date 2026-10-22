"""Report only completed, covered replay months; never extrapolate a prefix."""
import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sfp_orb_engine.execution_policy import NO_FILL_REASONS


def summarize(row):
    result=row.get('metrics')
    if row.get('exit_code')!=0 or not result or not result.get('complete_return_coverage'):
        return {'status':'INCOMPLETE_PERFORMANCE_WITHHELD','metrics':None,
                'last_reported_progress':row.get('last_reported_progress')}
    output=Path(row['output'])
    closed=json.loads((output/'state/closed.json').read_text())
    filled=[t for t in closed if t.get('close_reason') not in NO_FILL_REASONS]
    filled.sort(key=lambda t:t['closed_at'])
    weighted=[float(t['weighted_net_r']) for t in filled]
    if abs(sum(weighted)-result['weighted_net_r'])>1e-5:
        raise RuntimeError('Ledger and monthly result disagree')
    peak=equity=drawdown=0.0
    for value in weighted:
        equity+=value;peak=max(peak,equity);drawdown=max(drawdown,peak-equity)
    return {'status':'COVERED_RECONSTRUCTED_REPLAY_COMPLETED','metrics':{
        'filled_closed_trades':len(filled),'wins':sum(x>0 for x in weighted),
        'win_rate_pct':round(100*sum(x>0 for x in weighted)/len(filled),2) if filled else None,
        'net_r':round(result['net_r'],6),'risk_weighted_net_r':round(sum(weighted),6),
        'closed_equity_max_drawdown_weighted_r':round(drawdown,6),
        'no_fill_orders':len(closed)-len(filled),
        'open_at_month_end':result['open_at_month_end'],
        'close_reasons':dict(Counter(t['close_reason'] for t in filled)),
        'per_symbol_weighted_r':{s:round(sum(t['weighted_net_r'] for t in filled if t['symbol']==s),6) for s in sorted({t['symbol'] for t in filled})},
        'ledger':str(output/'state/closed.json')}}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT/'data/full_2025_study');args=parser.parse_args()
    state=json.loads((args.root/'resume_status.json').read_text())
    selected=state.get('requested_months',['2025-01','2025-06','2025-11'])
    months={m:summarize(state.get('months',{}).get(m,{})) for m in selected}
    complete=all(x['metrics'] is not None for x in months.values())
    report={'generated_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'requested_months':selected,'requested_study_completed':complete,
            'full_three_month_study_completed':complete and len(selected)==3,
            'scope':'Current paper entry/lifecycle engine; historical data; genuine recomputed current-model macro responses. Not original archived 2025 decisions or broker fills.',
            'credential_profile':state.get('credential_profile'),'months':months,
            'limitations':['Broker bid quotes differ from the archived original live Forex feed.',
                           'Macro market snapshots use completed M15/H1 quotes; some economic publication timing uses conservative previous-day vintages.',
                           'Open month-end positions are retained; P/L is realized closed-trade R, not account return.',
                           'Drawdown is from closed trades only; it excludes intratrade and open-position drawdown.',
                           'Spread/slippage are not measured broker fills; the engine uses its configured friction buffer.',
                           'Historical calendar forecast revisions and original 2025 model outputs are not archived.']}
    (args.root/'BACKTEST_2025_RESULTS.json').write_text(json.dumps(report,indent=2))
    text=['# 2025 sistem oynatma sonuçları','',
          f'**İstenen {len(selected)} aylık çalışma tamamlandı.**' if complete else f'**İstenen {len(selected)} aylık çalışma henüz tamamlanmadı. Eksik ayların performansı gösterilmez.**','',
          '| Ay | Dolan ve kapanan işlem | Kazanma | Net R | Risk ağırlıklı net R | Kapanan işlem DD (R) | Ay sonu açık |',
          '|---|---:|---:|---:|---:|---:|---:|']
    for month,row in months.items():
        v=row['metrics']
        if v is None:text.append(f'| {month} | Eksik | — | — | — | — | — |');continue
        win='—' if v['win_rate_pct'] is None else str(v['win_rate_pct'])+'%'
        text.append(f"| {month} | {v['filled_closed_trades']} | {win} | {v['net_r']:+.3f} | {v['risk_weighted_net_r']:+.3f} | {v['closed_equity_max_drawdown_weighted_r']:.3f} | {v['open_at_month_end']} |")
    text+=['','R, işlem stop mesafesine göre sonuçtur. Risk ağırlıklı R mevcut makro risk çarpanını içerir; hesap getirisi yüzdesi değildir.',
           'DD yalnız kapanmış işlem eğrisidir; açık pozisyon ve işlem içi dalgalanmayı içermez. Ay sonu açık işlemler zorla kapatılmadı.',
           '', 'Orijinal entry/işlem takibi kullanıldı. Makro kararları gerçek model yanıtlarıyla yeniden üretildi; özgün 2025 karar arşivi bulunmuyor.',
           'Forex fiyatları gerçek broker bid verisidir; özgün canlı TwelveData akışının aynısı değildir. Modelin güncel sürümü ve veri erişim varsayımları yöntemde açıklanır.',
           '', 'Ayrıntı: BACKTEST_2025_RESULTS.json. Yöntem: docs/FULL_SYSTEM_2025_REPLAY_METHOD.md.',
           'Bu baseline tamamlanmadan TP/stop iyileşmesi iddiası üretilmez.']
    (args.root/'BACKTEST_2025_RESULTS.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    print(json.dumps({'requested_study_completed':complete,'requested_months':selected,'months':months}))


if __name__=='__main__':main()

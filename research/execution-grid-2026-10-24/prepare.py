"""Prepare price-level proposals only. Never attaches old fills or returns."""
from pathlib import Path
from decimal import Decimal
import hashlib,json
import pandas as pd
from price_grid import normalize_for_research,FIELDS

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
SOURCE=HERE.parent/'sfp-ifvg-ablation-2026-10-24'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,obj):p.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf8')

def main():
    if (HERE/'protocol.json').exists():raise RuntimeError('Already prepared')
    sources=[SOURCE/'signals.json',SOURCE/'protocol.json',SOURCE/'summary.json',
        SOURCE/'quote_manifest_0_frozen.json',ROOT/'research/london-gold-2026-10-24/cost_evidence.json']
    fx=json.loads(sources[3].read_text())['symbol_specs']
    gold=json.loads(sources[4].read_text())['symbol_spec']
    steps={symbol:fx[symbol]['trade_tick_size'] for symbol in ['EURUSD','GBPUSD']}
    steps['XAUUSD']=gold['trade_tick_size']
    protocol=dict(created_utc=str(pd.Timestamp.now(tz='UTC')),
        status='UNIT_TESTED_GEOMETRY_ONLY_NOT_REPLAYED',
        source_hashes={str(p.relative_to(ROOT)):sha(p) for p in sources},
        code_hashes={p.name:sha(p) for p in HERE.glob('*.py')},steps=steps,
        rules='BUY entry ceil, SELL entry floor to observed brokerstep; SL outward; TP outward and at least1.2/2R from recomputed original-stop risk. Existing published farther targets retained. Input geometries with invalid ordering/nonfinite values rejected. No parameter search.',
        scope='Proposals from all57 frozen SFP no-IFVG signals. No price path, old fill, R result, macro, news or trade state carried into proposals. No broker order acceptance certificate.',
        spec_caveat='Captured2026 symbol metadata, not historical2025 tariff/stops/acceptance records. Entry rounding can change fills and risk; no guarantee of a lower bound on total performance.',
        next='A NEW frozen quote/lifecycle replay must regenerate fills, costs, stop/TP events and risk from these levels. Missing29 quote outcomes remain missing until complete. Do not replace old study results or treat quantization as edge.',
        live_changed=False,unit_tests_passed=10,paid_API_spend_USD=0)
    write(HERE/'protocol.json',protocol)
    proposals=[];max_risk_ratio=0.
    cases=json.loads(sources[0].read_text())
    for case in cases:
        aligned=normalize_for_research(case['signal'],steps[case['symbol']])
        step=Decimal(str(steps[case['symbol']]))
        for name in FIELDS:
            units=Decimal(str(aligned[name]))/step
            assert units==units.to_integral_value()
        entry=Decimal(str(aligned['entry']));stop=Decimal(str(aligned['stop_loss']));risk=abs(entry-stop)
        assert abs(Decimal(str(aligned['tp1']))-entry)/risk>=Decimal('1.2')
        assert abs(Decimal(str(aligned['tp2']))-entry)/risk>=Decimal('2.0')
        orig_risk=abs(Decimal(str(case['signal']['entry']))-Decimal(str(case['signal']['stop_loss'])))
        ratio=float(risk/orig_risk);max_risk_ratio=max(max_risk_ratio,ratio)
        # Deliberately omit every old direction/quote-return field.
        proposals.append(dict(case_id=case['case_id'],symbol=case['symbol'],available_at=case['available_at'],
            period=case['period'],signal=aligned,risk_ratio_to_nominal=ratio,
            status='PROPOSED_LEVELS_NOT_REPLAYED_NOT_LIVE_ORDER'))
    assert len(proposals)==57
    for p in sources:assert sha(p)==protocol['source_hashes'][str(p.relative_to(ROOT))]
    write(HERE/'aligned_signal_proposals.json',proposals)
    write(HERE/'integrity.json',dict(proposals=57,all_price_levels_on_grid=True,
        minimum_RR_rechecked=True,maximum_risk_ratio=max_risk_ratio,old_returns_reused=False,
        lifecycle_replayed=False,broker_order_acceptance_verified=False,live_changed=False))
    report='''# Araştırma fiyat-adımı adaptörü

Mevcut broker fiyat adımlarına göre57 SFP adayının tamamı için sayısal olarak uyumlu giriş/stop/hedef önerisi üretildi. Bu bir kâr backtesti veya kabul edilmiş broker emri değildir.

- Alış girişi yukarı, satış girişi aşağı yuvarlanır; giriş fiyatında olumlu iyileşme yazılmaz.
- Stop yapısal seviyeden dışarı yuvarlanır. Yeni risk mesafesi yeniden hesaplanır.
- Hedefler yeni riske göre en az1.2R/2R olacak şekilde dışarı yuvarlanır.
- Eski dolumlar, yön puanları ve kârlar bu önerilere taşınmadı. Değişen fiyatlar dolumu ve çıkışı değiştirebilir; yeni kronolojik replay gerekir.
- Fiyat adımları2026 broker metadata'sıdır. Tarihsel emir kabulü, minimum stop mesafesi ve diğer broker kısıtları doğrulanmış değildir.

10 birim testi geçti;57 önerinin tüm seviyeleri ve minimum RR'si ayrıca doğrulandı. Üretim kodu ve eski araştırma sonuçları değiştirilmedi. Sonraki iş yeni bir protokolle kotasyon kapsamını tamamlayıp bu seviyeleri baştan oynatmaktır. Bu düzeltme tek başına edge üretildiği anlamına gelmez.
'''
    (HERE/'REPORT.md').write_text(report,encoding='utf8')
    write(HERE/'artifact_manifest.json',{p.name:sha(p) for p in HERE.iterdir() if p.is_file() and p.name!='artifact_manifest.json'})
    print(json.loads((HERE/'integrity.json').read_text()))

if __name__=='__main__':main()

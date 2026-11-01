"""Coverage-label correction only: inherit independently established closures."""
from pathlib import Path
from datetime import datetime,timezone
import sys,json
import pandas as pd
import numpy as np

HERE=Path(__file__).resolve().parent;BASE=HERE.parent
sys.path.insert(0,str(BASE))
import study as s
g=s.g

def main():
    old= g.read(BASE/'outcomes.json')
    feats=g.read(HERE/'features.json');rows=g.read(HERE/'outcomes.json')
    groups={}
    for r in old:groups.setdefault(r['date'],[]).append(r['outcome']['status'])
    dates=sorted(d for d,st in groups.items() if len(st)==3 and set(st)=={'CONFIRMED_HOLIDAY_CLOSED'})
    assert dates==['2025-01-01','2025-04-18','2025-12-25','2026-01-01']
    protocol=g.read(HERE/'protocol_frozen.json')
    for path,digest in protocol['declaration']['frozen_source_hashes'].items():assert g.sha(Path(path))==digest
    rule=dict(classification_rule='If all three original frozen baseline scenarios independently say CONFIRMED_HOLIDAY_CLOSED, carry that status through unchanged; do not require nonexistent Asia bars on a day with no session. Do not change any other date or trade outcome.',verified_dates=dates,source='immutable baseline outcomes.json; all three cost scenarios agree.')
    g.save(HERE/'closure_classification_v2.json',dict(created_utc=datetime.now(timezone.utc).isoformat(),rule=rule))
    fmap={f['date']:f for f in feats}
    for d in dates:
        assert fmap[d]['status']=='BLOCKED_ASIA_FEATURE'
        fmap[d]['status']='CONFIRMED_HOLIDAY_CLOSED';fmap[d]['closed_source']='all three original scenarios'
    rmap={(x['date'],x['scenario']):x for x in rows}
    for d in dates:
        for name,m in g.SCENARIOS:
            x=rmap[(d,name)]
            assert x['outcome']['status']=='BLOCKED_ASIA_FEATURE'
            x['outcome']=dict(status='CONFIRMED_HOLIDAY_CLOSED');x['asia']='CONFIRMED_HOLIDAY_CLOSED'
    monthsets={'2025_full':s.MONTHS[:12],'2025_new_SepDec':s.MONTHS[8:12],'2026_JanSep_partial':s.MONTHS[12:],'all21months':s.MONTHS}
    results={}
    for period,months in monthsets.items():
        cal=g.dates(months);results[period]={}
        for name,m in g.SCENARIOS:
            classic=[x for x in old if x['scenario']==name and x['date'][:7] in months]
            asia=[x for x in rows if x['scenario']==name and x['date'][:7] in months]
            unknown=sorted({x['date'] for x in asia if x['outcome']['status'] in g.UNKNOWN|{'BLOCKED_ASIA_FEATURE'}})
            if unknown:
                use=[d for d in cal if d not in unknown]
                a=[x for x in classic if x['date'] in use];b=[x for x in asia if x['date'] in use]
                bs=s.v.stats(a,use);fs=s.v.stats(b,use);delta=pd.Series(0.,index=use)
                for x in a:delta.loc[x['date']]-=x['outcome'].get('net_r',0)
                for x in b:delta.loc[x['date']]+=x['outcome'].get('net_r',0)
                results[period][name]=dict(complete=False,unknown_dates=unknown,known_common_days=len(use),classic=bs,asia=fs,paired_delta_r=float(delta.sum()),paired_delta_ci95=g.block_ci(delta))
            else:
                a=s.v.stats(classic,cal);b=s.v.stats(asia,cal);delta=pd.Series(0.,index=cal)
                for x in classic:delta.loc[x['date']]-=x['outcome'].get('net_r',0)
                for x in asia:delta.loc[x['date']]+=x['outcome'].get('net_r',0)
                results[period][name]=dict(complete=True,classic=a,asia=b,paired_delta_r=float(delta.sum()),paired_delta_ci95=g.block_ci(delta))
    out=dict(results=results,classification=rule,live_approved=False,orders_sent=False)
    g.save(HERE/'results_v2.json',out);g.save(HERE/'features_v2.json',feats);g.save(HERE/'outcomes_v2.json',rows)
    # Full 2025 and new Sep-Dec are complete. The two 2026 winter gaps remain unknown.
    lines=['# London XAUUSD ORB: Asya araligi baglami','',
      '**Hipotez:** London 08:00–08:15 M15 kapanisi, ayni yonde 00:00–08:00 Asya araligini terk etmisse ORB islemine izin ver.',
      '','Tam32 ardışık Asya M15 barı istenir. Kapanış long için aralık tepesinin üstünde, short için dibinin altında olmalıdır. Eşitlik ve aralık içinde kapanış reddedilir. Giriş, stop, 2R, 16:00 EOD, komisyon, spread ve slippage aynı dondurulmuş motorla ölçüldü. Yaz ve maliyet filtreleri eklenmedi.',
      '','Sonuçlar tarihsel keşif ölçümüdür. Bu kural eski geniş araştırmalarda geçmiş tarihlere uygulanmamış olabilir; bu nedenle tüm veri kümesiyle mutlak OOS/ileri test iddiası yok.','',
      '| Dönem | Maliyet | Klasik işlem / netR | Asya işlem / netR / PF | Asya filtresinin farkı [95% CI] | Kapsama |',
      '|---|---:|---:|---:|---:|---|']
    for period,months in monthsets.items():
        for name,m in g.SCENARIOS:
            z=results[period][name];a=z['classic'];b=z['asia'];ci=z['paired_delta_ci95']
            if z['complete']:coverage='tam'
            else:coverage='ortak gun '+str(z['known_common_days'])+'/'+str(len(g.dates(months)))+'; bilinmeyen '+', '.join(z['unknown_dates'])
            lines.append(f"| {period} | {m:g}x | {a['fills']} / {a['net_r']:+.2f}R | {b['fills']} / {b['net_r']:+.2f}R / {b['pf']:.2f} | {z['paired_delta_r']:+.2f}R [{ci[0]:+.2f},{ci[1]:+.2f}] | {coverage} |")
    lines+=['','### Ne gösteriyor?','',
      '2025 tam yılda Asya filtresi 22 işlemde 1.5x net +8.51R verdi; klasik ORB aynı yıl 229 işlemde -4.34R idi. Ancak eşleştirilmiş farkın %95 aralığı sıfırı kapsıyor ve 22 işlem edge kanıtı için az.',
      '2025 Eylül–Aralık ayrı dönemi 5 işlemde sadece +0.88R verdi.2026 Ocak–Eylül filtresi bilinmeyen iki kış günü çıkarılmış 193 takvim gününde 12 işlem/+8.74R; işlem bazlı blok CI -2.11R ile +20.68R. Eşleştirilmiş fark +45.90R, CI +12.36R ile +77.79R; bu adayın filtresiz ORB günlerinde kayıpları önlediğini düşündüren olumlu fakat küçük örneklemli işarettir.',
      '2025 ve 2026 birlikte 34 işlem ve +17.25R gösteriyor. 2025’in en iyi beş işlemi çıkarılınca +8.51R, -1.38R’ye; 2026’da +8.74R, -1.18R’ye düşüyor. Birleştirilmiş eşleştirilmiş farkın aralığı sıfırın hemen üstünden başlıyor; sonuç az sayıda işleme, birden çok denenmiş fikre ve daha önce görülmüş tarihsel veriye duyarlı. Bu yüzden “edge doğrulandı” demiyorum. Asya aralığı geniş günleri seçiyor; iyileşmenin hangi piyasa mekanizmasından geldiği ayrı kanıtlanmadı.',
      '', '### Veri ve karar','',
      'Dört tam piyasa kapanışı (2025-01-01, 2025-04-18, 2025-12-25, 2026-01-01) için orijinal üç senaryonun hepsi zaten CONFIRMED_HOLIDAY_CLOSED diyordu. Bunları Asya barı yok diye bilinmeyen saymak yerine aynı kapanış etiketiyle taşıdım; hiçbir PnL eklenmedi/değişmedi.2026-04-03te yalnız8Asya barı var ve 2026-03-16da native açılış/quote denetimi başarısız; bu iki günü sıfırlamadım. 2026 ve 21ay toplam/PF/CI iddiası yok.',
      '','**Karar: Asya bağlamı şu ana kadarki en güçlü test adayıdır, doğrulanmış edge değildir.** Öncelik bunu yeni ve el değmemiş bir dönemde aynen test etmek. M1 kapanış/retest/tepe-dip hipotezini sonradan ekleyip bu sonucu kurtarmaya çalışmamak. En az100 işlem ve yeni dönemde pozitif sonuç görmeden terfi yok. Canlı emir gönderilmedi.','']
    (HERE/'SONUC_v2.md').write_text('\n'.join(lines),encoding='utf8')
    hashes={n:g.sha(HERE/n) for n in ['closure_classification_v2.json','features_v2.json','outcomes_v2.json','results_v2.json','SONUC_v2.md','study.py','protocol_frozen.json']}
    g.save(HERE/'completion_v2.json',dict(status='COMPLETE_RESEARCH_WITH_KNOWN_COVERAGE_LIMITS',orders_sent=False,live_approved=False,hashes=hashes))
    print('CORRECTED_CLOSURE_CLASSIFICATION',dates,'2025_complete',results['2025_full']['STRESS_1.5x']['complete'],flush=True)

if __name__=='__main__':main()

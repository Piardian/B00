"""Versioned measurement audit. Preserve the original strict5s study."""
import argparse,ast,inspect,json,textwrap
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo
import complete as s

OFFICIAL='https://the5ers.com/faqs/market-trading-hours/'

def event_function():
    m=s.measure();tree=ast.parse(textwrap.dedent(inspect.getsource(m.quote_score)));changed=0
    for node in ast.walk(tree):
        if isinstance(node,ast.If) and 'j >= len(times)' in ast.unparse(node.test):
            for inner in ast.walk(node.test):
                if isinstance(inner,ast.Constant) and inner.value==5:inner.value=60;changed+=1
    assert changed==1
    env=m.__dict__.copy();exec(compile(ast.fix_missing_locations(tree),'<event_markout_max60s>','exec'),env)
    return env['quote_score']

def freeze():
    m=s.measure();m.verify();path=s.HERE/'event_protocol.json';assert not path.exists()
    m.write(path,dict(created_utc=str(pd.Timestamp.now(tz='UTC')),
        reason='After full broker archive retrieval, four case/model markouts fail strict5s solely because the first real quote arrives5.078..7.46seconds after the fixed60min timer. No markout price inspection used to choose this rule. Separate measurement repair, not a strategy change or untouchedOOS.',
        event_rule='Exactly first real quote at/after fill+60min, accept only <=60s latency and original <=60s internal quote-gap guard. Both models/all57cases/allsame3cost scenarios rerun. No chosen later/better quote. Original5s outputs kept as strict primary sensitivity.',
        gold_closed_rule='Report separately as CLOSED_SESSION_EXPIRY_ASSUMPTION if no original order touch before TTL, complete requested archive through expiry, quotes continuous to within5s of broker23:50local close, and no nativeM15 begins during closed tail before expiry. Current official session01:05-23:50, winterUTC+2/summer+3, corroborates historical tick/native close.2025 historical schedule itself not archived; not a certified nofill. Never invent a price/fill. Original unresolved sensitivity retained.',
        official_source=OFFICIAL,official_last_update='2026-06-10',
        scope='Explanatory diagnostic extension of seen data. No original lifecyclePnL, no new entry or parameter optimization, no live change.',
        original_protocol_sha256=m.sha(s.HERE/'protocol.json'),original_outcomes_sha256=m.sha(s.HERE/'outcomes.json'),
        code_sha256=m.sha(s.HERE/'event_audit.py')))
    print('EVENT_AUDIT_FROZEN; strict5s report retained')

def closed_expiry(c,sig,f,meta,reference):
    if c['symbol']!='XAUUSD':return None
    at=pd.Timestamp(c['available_at']);expiry=at+pd.Timedelta(hours=4)
    offset=2+int(bool(at.to_pydatetime().astimezone(ZoneInfo('America/New_York')).dst()))
    close=pd.Timestamp(c['day']+' 23:50',tz='UTC')-pd.Timedelta(hours=offset)
    if expiry<=close or pd.Timestamp(meta['requested_end'])<expiry:return None
    subset=f[(f.time>=at)&(f.time<expiry)]
    if subset.empty or subset.iloc[0].time>at+pd.Timedelta(seconds=5):return None
    if not((subset.bid>0)&(subset.ask>=subset.bid)).all():return None
    # Rules based on the raw nominal quotes; caller additionally checks each
    # scenario's actual limit touch to prevent a spread-dependent false nofill.
    if (subset.time.diff().dt.total_seconds()>60).any():return None
    if abs((close-subset.time.iloc[-1]).total_seconds())>5:return None
    if ((reference.datetime>=close)&(reference.datetime<expiry)).any():return None
    return dict(status='CLOSED_SESSION_EXPIRY_ASSUMPTION',net_markout_r=None,
        official_close_utc=str(close),last_quote=str(subset.time.iloc[-1]),expiry=str(expiry),
        no_native_bars_in_closed_tail=True,archived2025_schedule_verified=False,
        explanation='Unfilled timer expires after corroborated broker session close; no quote or return invented.')

def run():
    m=s.measure();m.verify();p=m.read(s.HERE/'event_protocol.json')
    assert m.sha(s.HERE/'event_audit.py')==p['code_sha256']
    assert m.sha(s.HERE/'outcomes.json')==p['original_outcomes_sha256']
    cases=m.read(s.HERE/'cases_frozen.json');aligned={r['case_id']:r for r in m.read(s.HERE/'aligned_frozen.json')}
    manifest=m.read(s.HERE/'quote_manifest_frozen.json');fn=event_function()
    gold=m.load_prices('XAUUSD')[0];results=[]
    for c in cases:
        meta=manifest['files'][c['symbol']+'_'+c['day']]
        assert meta['clock_qa']['passed'];path=s.Path(meta['path']);assert m.sha(path)==meta['sha256']
        f=pd.read_parquet(path);f.time=pd.to_datetime(f.time,utc=True)
        for model,sig in [('NOMINAL',c['signal']),('ALIGNED',aligned[c['case_id']]['signal'])]:
            for label,mult,floor in [('OBSERVED',1.,False),('STRESS_1_5X',1.5,False),('STRESS_FLOOR',1.5,True)]:
                r=fn(sig,c['available_at'],f,stress=mult,floor=floor)
                if r['status']=='FILLED_MARKOUT':
                    r['markout_latency_seconds']=(pd.Timestamp(r['marked_at'])-pd.Timestamp(r['filled_at'])-pd.Timedelta(hours=1)).total_seconds()
                if r['status']=='UNRESOLVED_COVERAGE':
                    closed=closed_expiry(c,sig,f,meta,gold)
                    if closed:
                        at=pd.Timestamp(c['available_at']);sub=f[(f.time>=at)&(f.time<at+pd.Timedelta(hours=4))]
                        point=.01;entry=sig['entry'];long=sig['direction']=='LONG'
                        spread=(sub.ask-sub.bid)*mult
                        if floor:spread=spread.clip(lower=.30)
                        touches=(sub.bid+spread<=entry-point+point*1e-7) if long else (sub.bid>=entry+point-point*1e-7)
                        if not touches.any():r=closed
                results.append({k:c[k] for k in ['case_id','symbol','day','month','period']}|dict(model=model,scenario=label,**r))
    m.write(s.HERE/'event_outcomes.json',results)
    summary={}
    for period in ['DEVELOPMENT','VALIDATION']:
        summary[period]={}
        for model in ['NOMINAL','ALIGNED']:
            summary[period][model]={}
            for scenario in ['OBSERVED','STRESS_1_5X','STRESS_FLOOR']:
                rows=[r for r in results if r['period']==period and r['model']==model and r['scenario']==scenario]
                ss=s.stats(rows);ss['closed_session_expiry_assumptions']=sum(r['status']=='CLOSED_SESSION_EXPIRY_ASSUMPTION' for r in rows)
                ss['quote_measured_records']=ss['fills']+ss['no_fill']
                ss['unclassified']=len(rows)-ss['fills']-ss['no_fill']-ss['closed_session_expiry_assumptions']
                summary[period][model][scenario]=ss
    assert len(results)==342
    for r in results:
        if r['status']=='FILLED_MARKOUT':
            assert 0<=r['markout_latency_seconds']<=60
            assert np.isclose(r['net_markout_r'],r['price_markout_r']-r['commission_r']-r['slip_r'])
        else:assert r['net_markout_r'] is None
    m.write(s.HERE/'event_summary.json',summary)
    lines=['# Gerçek sonraki kotasyonla zamanlayıcı denetimi','',
        'Ayrı duyarlılık çalışması: ilk katı5s sınırı ve sonuçları değişmedi.60dk markout emri zamanlayıcıdan sonraki İLK gerçek kotasyonda ölçüldü; azami60s ve tüm iç kotasyon boşlukları<=60s koşulu korundu. Bu örneklemde ek gecikmeler yalnızca5.078–7.46s; daha iyi fiyat aranmadı.','',
        '| Dönem | Model | Senaryo | Dolum | Kanıtlı dolmama | Kapalı seans varsayımı | Belirsiz | Ortalama maliyetli markout R |','|---|---|---|---:|---:|---:|---:|---:|']
    for period,models in summary.items():
        for model,scenarios in models.items():
            for scenario,ss in scenarios.items():
                mean='—' if ss['mean_conditional_markout_r'] is None else f"{ss['mean_conditional_markout_r']:.6f}"
                lines.append(f"| {period} | {model} | {scenario} | {ss['fills']} | {ss['no_fill']} | {ss['closed_session_expiry_assumptions']} | {ss['unclassified']} | {mean} |")
    lines+=['', 'Altındaki iki dolmamış emrin süre sonu kapanış aralığına denk geliyor. Mevcut resmi saatler01:05–23:50broker saati; tarihsel tick sonu23:49:57/23:49:59 ve nativeM15 boşluğu bunu destekliyor.2025 seans takvimi arşivlenmiş değildir; bu yüzden bu iki kayıt ayrı varsayım kategorisinde kaldı ve gerçek broker emri kabulü/iptali iddia edilmedi.',
      '', '[The5ers resmi saatleri,10Haziran2026 güncellemesi]('+OFFICIAL+').2026 belgesi2025 için bağımsız tarihsel sertifika değildir.',
      '', 'Markout işlem kârı değildir: stop/TP/erken çıkış uygulanmadı. Kapalı-seans varsayımına ve zaman toleransına rağmen edge kanıtlanmış sayılmaz; ilk strict rapor ve tüm eski dosyalar korunur.']
    (s.HERE/'EVENT_TIME.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    m.write(s.HERE/'event_integrity.json',dict(passed=True,records=342,strict_original_unchanged=True,
        archived2025_session_calendar_verified=False,live_changed=False,
        all_records_classified=all(ss['unclassified']==0 for models in summary.values() for scenarios in models.values() for ss in scenarios.values())))
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    pa=argparse.ArgumentParser();pa.add_argument('action',choices=['freeze','run']);args=pa.parse_args();globals()[args.action]()

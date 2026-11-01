"""Frozen original-SFP diagnostic. Not a portfolio or lifecycle backtest."""
from pathlib import Path
import argparse, hashlib, importlib, json, os, sys
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
SYMBOLS = ['EURUSD', 'GBPUSD', 'XAUUSD']
MONTHS = list(pd.period_range('2025-01', '2025-11', freq='M').astype(str))
MODULES = ['config.py', 'sfp_detector.py', 'entry_mechanics.py',
           'strict_setup.py', 'volume_anomaly.py', 'execution_policy.py']
MANIFESTS = [
 'research/london-quote-validation-2026-10-23/quote_manifest_frozen.json',
 'research/london-extension-2026-10-24/quote_manifest_frozen.json',
 'research/london-gold-seasonal-extension-2026-10-24/quote_manifest.json',
 'research/london-gold-2026-10-24/quote_manifest_frozen.json',
 'research/london-gold-validation-2026-10-24/quote_manifest.json']

def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p, obj):
    Path(p).write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False, default=str), encoding='utf-8')
def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()

def freeze():
    if (HERE/'protocol.json').exists(): raise RuntimeError('Already frozen')
    from sfp_orb_engine import config
    package = HERE/'frozen_engine'; package.mkdir(exist_ok=True)
    (package/'__init__.py').write_text('', encoding='utf-8')
    for name in MODULES: (package/name).write_bytes((ROOT/'sfp_orb_engine'/name).read_bytes())
    (HERE/'normalize_clock.py').write_bytes((ROOT/'scripts/normalize_broker_history.py').read_bytes())
    sources = []
    for s in SYMBOLS:
        for tf in ['15m', '1h']:
            sources.append(ROOT/f'data/full_2025_study/prices_utc/{s}_{tf}.csv.gz')
            if s != 'XAUUSD': sources.append(ROOT/f'research/fill-delay-2026-10-24/followup_prices/{s}_{tf}.parquet')
    sources.append(ROOT/'research/london-gold-seasonal-extension-2026-10-24/gold_m15.parquet')
    for i, name in enumerate(MANIFESTS):
        p = HERE/f'quote_manifest_{i}_frozen.json'; p.write_bytes((ROOT/name).read_bytes()); sources.append(p)
    cfg = {k:getattr(config,k) for k in ['ENTRY_MODEL','LIMIT_EXPIRY_BARS','REQUIRE_PRO_TREND_AAA',
       'REQUIRE_STRUCTURAL_BREAKER','USE_IFVG_ENTRY','SFP_RR_TARGET_1','SFP_RR_TARGET_2','ACTIVE_SYMBOLS']}
    write(HERE/'protocol.json', dict(created_utc=str(pd.Timestamp.now(tz='UTC')), symbols=SYMBOLS,
      months=MONTHS, development=MONTHS[:6], validation=MONTHS[6:], effective_config=cfg,
      scope='Original frozen SFP detector and signal validation ONLY. ORB branch stopped. No macro/news/risk/occupancy/cooldown or original exit replay. Every distinct validated signal is measured, possibly overlapping. Not an actual strategy backtest, not dollar account return.',
      history='Only completed bid M15, last300; original session and market-open predicates at availability. Original higher_timeframe_trend on completed last1000 H1. Gold H1 reconstructed from existing native M15 for missing native hours; parity with overlapping native H1 must be reported. Strict availability timestamps; never use future pivot bars.',
      primary='Signed BID close change from signal close to exactly60min later, divided by ORIGINAL entry-stop distance. Four contiguous futureM15 required. Diagnostic of direction at signal; not executable entry, ignores SL/TP, not tradePnL. No horizon optimization.',
      quote_secondary='Where existing quote tapes cover exact signal availability through four-hour expiry plus60min: first original limit penetration one brokerpoint, nominal entry, exit at first quote>=fill+60min within5s, actual bid forlong/ask forshort. Ignore stop/TP only to isolate conditional postfill direction. This can cross stops; MUST NOT call this strategy PnL. Missing coverage is unresolved, never a nofill or zero result.',
      quote_costs='FX: assumed commission4USD/100k roundtrip and0.2pip exit slip. Gold: RT USD/ounce=max(.08,2*entry*.001/100), .05USD/ounce exit slip; inherited conservative fee envelope, not historical receipts. Stress1.5x observed spread/fees/slip; no favorable fill improvement. Additional spread floor .5pipFX/.30USDgold. Entry/exits rerun under stress. No paid API or new price downloads.',
      assessment='Both fixed temporal periods reported without tuning; all prices previously inspected elsewhere, NOT pristine OOS. Day-cluster bootstrap10000 seed20261024. Entry follow-up requires >=30resolved quote fills across>=15days IN EACH PERIOD, no unresolved candidates, positive stressed mean and95CI lower>0 eachperiod. Diagnostic gate only, never live approval. Incomplete quote coverage or thin sample -> INCONCLUSIVE, not failed system or proven edge.',
      improvements='Only stage-by-stage rejection counts, costs/originalrisk, fill delay and signed paths may motivate a NEW predeclared experiment. Never silently relax IFVG/breaker/trend or replace entry in this run.',
      source_hashes={str(p.relative_to(ROOT)):sha(p) for p in sources},
      frozen_source_hashes={str(p.relative_to(HERE)):sha(p) for p in package.glob('*.py')},
      code_hashes={p.name:sha(p) for p in HERE.glob('*.py')},
      previous_ORB_decision_sha256=sha(ROOT/'research/full-tick-lifecycle-2026-10-24/decision.json')))
    print('FROZEN', cfg, flush=True)

def verify():
    p=read(HERE/'protocol.json')
    for bucket,base in [('source_hashes',ROOT),('frozen_source_hashes',HERE),('code_hashes',HERE)]:
        for n,h in p[bucket].items():
            if sha(base/n)!=h: raise RuntimeError('Frozen input changed: '+n)
    return p

def engine():
    p=read(HERE/'protocol.json')
    os.environ['ENTRY_MODEL']=p['effective_config']['ENTRY_MODEL']
    os.environ['LIMIT_EXPIRY_BARS']=str(p['effective_config']['LIMIT_EXPIRY_BARS'])
    c=importlib.import_module('frozen_engine.config')
    d=importlib.import_module('frozen_engine.sfp_detector')
    e=importlib.import_module('frozen_engine.execution_policy')
    return c,d,e

def frame(path):
    f=pd.read_parquet(path) if path.suffix=='.parquet' else pd.read_csv(path)
    f['datetime']=pd.to_datetime(f.datetime,utc=True)
    return f.sort_values('datetime').reset_index(drop=True)

def merge(parts):
    both=pd.concat(parts,ignore_index=True)
    conflicts=0
    for col in ['open','high','low','close','volume']:
        lo=both.groupby('datetime')[col].min();hi=both.groupby('datetime')[col].max()
        conflicts+=int((abs(hi-lo)>1e-8).sum())
    return both.drop_duplicates('datetime',keep='last').sort_values('datetime').reset_index(drop=True), conflicts

def load_prices(s):
    old=ROOT/'data/full_2025_study/prices_utc'
    m=frame(old/f'{s}_15m.csv.gz'); h=frame(old/f'{s}_1h.csv.gz')
    audit={}
    if s!='XAUUSD':
        new=ROOT/'research/fill-delay-2026-10-24/followup_prices'
        m,n=merge([m,frame(new/f'{s}_15m.parquet')]);audit['m15_conflicting_fields']=n
        h,n=merge([h,frame(new/f'{s}_1h.parquet')]);audit['h1_conflicting_fields']=n
    else:
        from normalize_clock import broker_to_utc
        g=pd.read_parquet(ROOT/'research/london-gold-seasonal-extension-2026-10-24/gold_m15.parquet')
        g['datetime']=broker_to_utc(pd.to_datetime(g.time,unit='s',utc=True));g['volume']=g.tick_volume
        m,n=merge([m,g[['datetime','open','high','low','close','volume']]])
        audit['m15_conflicting_fields']=n
        agg=m.set_index('datetime').resample('1h').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna().reset_index()
        overlap=h.merge(agg,on='datetime',suffixes=('_native','_derived'))
        audit['h1_overlap_rows']=len(overlap)
        audit['h1_ohlc_mismatches']=sum(int((abs(overlap[k+'_native']-overlap[k+'_derived'])>1e-8).sum()) for k in ['open','high','low','close'])
        audit['h1_derived_missing_native_rows']=int((~agg.datetime.isin(h.datetime)).sum())
        h,n=merge([agg,h]);audit['h1_conflicting_fields']=n
    audit.update(m15_rows=len(m),h1_rows=len(h),first=str(m.datetime.min()),last=str(m.datetime.max()))
    return m,h,audit

def direction(signal,available,bars):
    """Fixed diagnostic, never infer fills from bid OHLC."""
    at=pd.Timestamp(available); idx=pd.DatetimeIndex(bars.datetime)
    times=pd.date_range(at,periods=4,freq='15min')
    positions=idx.get_indexer(times)
    if (positions<0).any():return dict(status='MISSING_FORWARD_M15',signed_r=None)
    sign=1 if signal['direction']=='LONG' else -1
    risk=abs(signal['entry']-signal['stop_loss'])
    future=float(bars.iloc[positions[-1]].close)
    return dict(status='MEASURED',signed_r=sign*(future-signal['market_close_entry'])/risk,
       origin_bid=signal['market_close_entry'],future_bid=future,through=str(at+pd.Timedelta(hours=1)))

def scan():
    p=verify();c,d,e=engine();signals=[];coverage=[];audits={};rejects=[]
    detector=d.SFPDetector()
    structure=importlib.import_module('frozen_engine.strict_setup')
    original_confirm=structure.confirm_structure
    stages={}
    def observed_confirm(direction,j,i,highs,lows,opens,closes,atr,require_breaker=True,use_ifvg=True):
        r=original_confirm(direction,j,i,highs,lows,opens,closes,atr,require_breaker,use_ifvg)
        stages['structure_calls']+=1
        breaker=(structure.detect_structural_breaker_long if direction=='LONG' else structure.detect_structural_breaker_short)(j,i,highs,lows,opens,closes)
        zone=(structure.detect_ifvg_long if direction=='LONG' else structure.detect_ifvg_short)(i,highs,lows,closes,atr)
        stages['breaker_pass']+=int(bool(breaker));stages['ifvg_pass']+=int(zone is not None)
        stages['both_pass']+=int(bool(breaker) and zone is not None)
        stages['original_confirmation_pass']+=int(r is not None)
        return r
    structure.confirm_structure=observed_confirm
    for s in SYMBOLS:
        m,h,audit=load_prices(s);audits[s]=audit
        # Price conflicts invalidate comparable inputs instead of favoring an outcome.
        if audit['m15_conflicting_fields'] or (s!='XAUUSD' and audit['h1_conflicting_fields']):
            raise RuntimeError('Conflicting price inputs '+s+' '+str(audit))
        symbol=s[:3]+'/'+s[3:]; mi=pd.DatetimeIndex(m.datetime); hi=pd.DatetimeIndex(h.datetime)
        cache={};count=0
        for month in MONTHS:
            stages.clear();stages.update({k:0 for k in ['structure_calls','breaker_pass','ifvg_pass','both_pass','original_confirmation_pass']})
            start=pd.Timestamp(month+'-01',tz='UTC');end=start+pd.offsets.MonthBegin(1)
            cov=dict(symbol=s,month=month,expected_windows=0,missing_decision_bar=0,htf_unknown=0,scanned=0,raw_signals=0,validated=0)
            for at in pd.date_range(start,end,freq='15min',inclusive='left'):
                now=at.to_pydatetime()
                if not(c.is_market_open(symbol,now) and c.is_session_active_for_scan(symbol,now)):continue
                cov['expected_windows']+=1
                pos=mi.searchsorted(at-pd.Timedelta(minutes=15),side='right')
                if not pos or mi[pos-1]!=at-pd.Timedelta(minutes=15):cov['missing_decision_bar']+=1;continue
                hist=m.iloc[max(0,pos-300):pos].reset_index(drop=True)
                if len(hist)<30:cov['missing_decision_bar']+=1;continue
                key=at.floor('h')
                if key not in cache:
                    hp=hi.searchsorted(at-pd.Timedelta(hours=1),side='right')
                    cache[key]=e.higher_timeframe_trend(h.iloc[max(0,hp-1000):hp],at)
                trend=cache[key]
                if c.REQUIRE_PRO_TREND_AAA and trend not in ['BULLISH','BEARISH']:cov['htf_unknown']+=1;continue
                cov['scanned']+=1
                signal=detector.detect_sfp(hist,symbol,htf_trend=trend)
                if signal is None:continue
                cov['raw_signals']+=1
                reason=e.validate_signal(signal)
                risk=abs(float(signal['entry'])-float(signal['stop_loss']))
                if not reason and risk/float(signal['entry'])<.00002:reason='INSUFFICIENT_RISK_DISTANCE'
                if reason:rejects.append(dict(symbol=s,at=str(at),reason=reason));continue
                cov['validated']+=1
                signals.append(dict(case_id=f'{s}_{at.isoformat()}',symbol=s,available_at=str(at),
                    day=str(at.date()),month=month,period='DEVELOPMENT' if month in p['development'] else 'VALIDATION',
                    signal=signal,direction=direction(signal,at,m)))
            cov['confirmation_diagnostics']=dict(stages)
            coverage.append(cov);count+=cov['validated']
            write(HERE/'status.json',dict(stage='SCANNING',symbol=s,month=month,signals_so_far=len(signals)))
            print('SCAN',s,month,cov,flush=True)
        write(HERE/(s+'_signals.json'),[x for x in signals if x['symbol']==s])
    write(HERE/'signals.json',signals);write(HERE/'coverage.json',coverage)
    write(HERE/'price_audit.json',audits);write(HERE/'rejections.json',rejects)
    write(HERE/'status.json',dict(stage='SCAN_COMPLETE',signals=len(signals)))

def bootstrap(rows,key):
    valid=[r for r in rows if r.get(key) is not None]
    if not valid:return None
    days=sorted({r['day'] for r in valid})
    if len(days)<5:return None
    sums=np.array([sum(r[key] for r in valid if r['day']==d) for d in days])
    counts=np.array([sum(r['day']==d for r in valid) for d in days])
    picks=np.random.default_rng(20261024).integers(0,len(days),(10000,len(days)))
    return [float(v) for v in np.quantile(sums[picks].sum(1)/counts[picks].sum(1),[.025,.975])]

def tape_index():
    result={}
    for i in range(len(MANIFESTS)):
        for key,v in read(HERE/f'quote_manifest_{i}_frozen.json')['files'].items():
            if not v.get('path'):continue
            s=v.get('symbol','XAUUSD' if key[:4]=='2025' or key[:4]=='2026' else key.split('_')[0])
            day=v.get('date',key if key[:4] in ['2025','2026'] else key.split('_')[-1])
            result.setdefault((s,day),[]).append(v)
    return result

def quote_score(signal,available,tape, *, stress=1.,floor=False,expiry_minutes=240):
    """Coverage is required through the terminal event, never beyond it."""
    at=pd.Timestamp(available);end=at+pd.Timedelta(minutes=expiry_minutes+60)
    risk=abs(signal['entry']-signal['stop_loss']);long=signal['direction']=='LONG';sgn=1 if long else -1
    gold=signal['symbol'].replace('/','')=='XAUUSD'; point=.01 if gold else .00001
    f=tape[(tape.time>=at)&(tape.time<=end+pd.Timedelta(seconds=5))].copy()
    if f.empty or (f.time.iloc[0]-at).total_seconds()>5:
        return dict(status='UNRESOLVED_COVERAGE',net_markout_r=None)
    if not ((f.bid>0)&(f.ask>=f.bid)&np.isfinite(f.bid)&np.isfinite(f.ask)).all():
        return dict(status='INVALID_QUOTES',net_markout_r=None)
    spread=(f.ask-f.bid).to_numpy()*stress
    if floor:spread=np.maximum(spread,.30 if gold else .00005)
    bid=f.bid.to_numpy();ask=bid+spread
    times=pd.DatetimeIndex(f.time);entry=signal['entry']
    resting=times<at+pd.Timedelta(minutes=expiry_minutes)
    touch=(ask<=entry-point+point*1e-7) if long else (bid>=entry+point-point*1e-7)
    hits=np.flatnonzero(resting&touch)
    if not len(hits):
        expiry=at+pd.Timedelta(minutes=expiry_minutes)
        if times[-1]<expiry:return dict(status='UNRESOLVED_COVERAGE',net_markout_r=None)
        terminal=int(times.searchsorted(expiry))
        if (times[terminal]-expiry).total_seconds()>5:return dict(status='UNRESOLVED_COVERAGE',net_markout_r=None)
        if (f.time.iloc[:terminal+1].diff().dt.total_seconds()>60).any():return dict(status='UNRESOLVED_QUOTE_GAP',net_markout_r=None)
        return dict(status='NO_FILL',net_markout_r=None)
    i=int(hits[0]);target=times[i]+pd.Timedelta(hours=1);j=int(times.searchsorted(target))
    if j>=len(times) or (times[j]-target).total_seconds()>5:return dict(status='UNRESOLVED_MARKOUT',net_markout_r=None)
    if (f.time.iloc[:j+1].diff().dt.total_seconds()>60).any():return dict(status='UNRESOLVED_QUOTE_GAP',net_markout_r=None)
    slip=(.05 if gold else .00002)*stress
    fee=(max(.08,2*entry*.001/100) if gold else 4/100000)*stress
    exit_quote=float(bid[j] if long else ask[j]);price_markout=sgn*(exit_quote-entry)/risk
    path=bid[i:j+1] if long else ask[i:j+1]
    signed=sgn*(path-entry)/risk
    return dict(status='FILLED_MARKOUT',filled_at=str(times[i]),marked_at=str(times[j]),
        wait_minutes=(times[i]-at).total_seconds()/60,marketable_at_first=bool(i==0 and (ask[0]<=entry if long else bid[0]>=entry)),
        price_markout_r=price_markout,commission_r=fee/risk,slip_r=slip/risk,
        net_markout_r=price_markout-(fee+slip)/risk,
        mfe_r=float(max(0,signed.max())),mae_r=float(max(0,-signed.min())),
        original_stop_crossed=bool((path<=signal['stop_loss']).any() if long else (path>=signal['stop_loss']).any()))

def quotes():
    verify();cases=read(HERE/'signals.json');index=tape_index();out=[];used={}
    for number,c in enumerate(cases):
        paths=index.get((c['symbol'],c['day']),[]);frames=[]
        for meta in paths:
            p=Path(meta['path'])
            if not p.exists():continue
            if sha(p)!=meta['sha256']:raise RuntimeError('Quote tape changed '+str(p))
            f=pd.read_parquet(p);f.time=pd.to_datetime(f.time,utc=True)
            # Do not stitch overlapping tapes: preserve one complete original sequence.
            frames.append((f,meta))
        expiry_minutes=15*read(HERE/'protocol.json')['effective_config']['LIMIT_EXPIRY_BARS']
        at=pd.Timestamp(c['available_at']);end=at+pd.Timedelta(minutes=expiry_minutes+60)
        usable=[(f,meta) for f,meta in frames if not f.empty and f.time.min()<=at+pd.Timedelta(seconds=5) and f.time.max()>=at]
        chosen=max(usable,key=lambda x:(x[0].time.max(),len(x[0]))) if usable else (None,None)
        for label,stress,floor in [('OBSERVED',1.,False),('STRESS_1_5X',1.5,False),('STRESS_FLOOR',1.5,True)]:
            r=quote_score(c['signal'],at,chosen[0],stress=stress,floor=floor,expiry_minutes=expiry_minutes) if chosen[0] is not None else dict(status='UNRESOLVED_COVERAGE',net_markout_r=None)
            out.append({k:c[k] for k in ['case_id','symbol','day','month','period']}|dict(scenario=label,**r))
        if chosen[1]:used[str(Path(chosen[1]['path']))]=chosen[1]['sha256']
        print('QUOTE',number+1,len(cases),c['case_id'],out[-3]['status'],flush=True)
    write(HERE/'quote_markouts.json',out);write(HERE/'used_tape_hashes.json',used)

def report():
    p=verify();cases=read(HERE/'signals.json');q=read(HERE/'quote_markouts.json');cov=read(HERE/'coverage.json')
    groups={}
    for period in ['DEVELOPMENT','VALIDATION']:
        cs=[c for c in cases if c['period']==period]
        ds=[dict(day=c['day'],signed_r=c['direction']['signed_r']) for c in cs]
        values=[d['signed_r'] for d in ds if d['signed_r'] is not None]
        g=dict(signals=len(cs),direction_measured=len(values),direction_mean_r=float(np.mean(values)) if values else None,
           direction_positive=sum(v>0 for v in values),direction_day95=bootstrap(ds,'signed_r'),quotes={})
        for label in ['OBSERVED','STRESS_1_5X','STRESS_FLOOR']:
            rows=[r for r in q if r['period']==period and r['scenario']==label]
            fills=[r for r in rows if r['status']=='FILLED_MARKOUT'];v=[r['net_markout_r'] for r in fills]
            g['quotes'][label]=dict(setups=len(rows),fills=len(fills),days=len({r['day'] for r in fills}),
                status_counts={s:sum(r['status']==s for r in rows) for s in sorted({r['status'] for r in rows})},
                mean_conditional_markout_r=float(np.mean(v)) if v else None,day95=bootstrap(fills,'net_markout_r'),
                stop_crossed=sum(r['original_stop_crossed'] for r in fills))
        groups[period]=g
    monthly={}
    for mo in MONTHS:
        cs=[c for c in cases if c['month']==mo]
        vals=[c['direction']['signed_r'] for c in cs if c['direction']['signed_r'] is not None]
        monthly[mo]=dict(signals=len(cs),direction_mean_r=float(np.mean(vals)) if vals else None,
            by_symbol={s:sum(c['symbol']==s for c in cs) for s in SYMBOLS})
    passed=True
    for g in groups.values():
        for label in ['STRESS_1_5X','STRESS_FLOOR']:
            r=g['quotes'][label]
            passed &= (r['fills']>=30 and r['days']>=15 and not any(k.startswith(('UNRESOLVED','INVALID')) for k in r['status_counts'])
                and r['mean_conditional_markout_r'] is not None and r['mean_conditional_markout_r']>0 and r['day95'] is not None and r['day95'][0]>0)
    write(HERE/'summary.json',dict(groups=groups,monthly=monthly,by_symbol={s:sum(c['symbol']==s for c in cases) for s in SYMBOLS},
        coverage_totals={k:sum(r[k] for r in cov) for k in ['expected_windows','missing_decision_bar','htf_unknown','scanned','raw_signals','validated']},
        direction_not_pnl=True,conditional_markout_not_strategy_pnl=True))
    write(HERE/'decision.json',dict(status='ENTRY_FOLLOWUP_SUPPORTED' if passed else 'ENTRY_EDGE_NOT_ESTABLISHED',
       live_approved=False,demo_started=False,ORB='FROZEN_STOP_NO_TUNING',
       caveat='Missing quotes or thin samples cannot disprove SFP. Direction and conditional markouts do not include original stop/TP or macro/news/occupancy. No strategy profitability claim.',
       next='Only if coverage and fixed-period evidence support it, replay original lifecycle. No TP/SL optimization on unproven entry. Audit rejection stages before proposing one isolated new rule.'))
    text=['# Begonya00 — mevcut SFP giriş mekanizması',
      '', 'Bu çalışma tam sistem backtesti değildir. Gerçek SFP tespit ve giriş seviyeleri korunur; makro/haber/portföy ve çıkış yönetimi uygulanmaz. 60 dakikalık yön puanı ve koşullu dolum sonrası markout, işlem kârı değildir.',
      '', 'Ocak–Haziran geliştirme; Temmuz–Kasım ayrı tarihsel kontrol. Veriler başka çalışmalarda görülmüştür; temiz OOS veya ileri test değildir.',
      '', '| Dönem | Geçerli sinyal | 60dk yön ortalaması (R) | Pozitif yön | Gözlenen kotasyonla ölçülebilen dolum |',
      '|---|---:|---:|---:|---:|']
    for name,g in groups.items():
        text.append(f"| {name} | {g['signals']} | {g['direction_mean_r']} | {g['direction_positive']}/{g['direction_measured']} | {g['quotes']['OBSERVED']['fills']} |")
    text+=['', 'Fiyat yön puanı sinyal kapanışından başlar; limitin dolduğunu varsaymaz. Kotasyon markoutu, limit dolumundan 60dk sonrasını ölçer ve stop aşılmasına izin verir; bu nedenle kazanç gibi kullanılamaz.',
      '', 'Eksik kotasyonlar sıfır getiri veya dolmayan emir sayılmaz. Kapsam, dolanlarda dolum+60dk; dolmayanlarda 4 saatlik limit süresinin sonuna kadar gerekir. Bu kapsam düzeltmesi kotasyon sonuçlarına bakılmadan protocol_initial.json üzerine kaydedilmiştir. Tarihsel spread gözlenir; komisyon ve kayma varsayımdır. Altın ve FX maliyetleri ayrıdır.',
      '', 'Sinyal zamanı girdileri yalnızca tamamlanmış barlardır. Üst zaman dilimi mevcut kodun son1000 H1, 4H EMA50/200 yöntemidir. Altında ek dönem H1 barları mevcut M15 arşivinden türetilmiştir; örtüşme kontrolü price_audit.json içindedir.',
      '', 'Karar: '+('Giriş mekanizması için yaşam döngüsü incelemesine geçiş eşiği sağlandı.' if passed else 'Giriş edge’i kanıtlanmadı. Eksik kapsam/az örnek ve negatif bulgular summary.json içinde ayrı gösterilir; bu karar tüm SFP olasılıklarının reddi değildir.'),
      '', 'ORB kolunda yeni süre/TP/SL taraması yapılmadı. Üretim koduna, çalışan sürece ve emirlere müdahale edilmedi.',
      '', 'Ayrıntı: summary.json, signals.json, rejections.json, coverage.json, price_audit.json, quote_markouts.json ve protocol.json.']
    (HERE/'REPORT.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    write(HERE/'status.json',dict(stage='COMPLETE',cases=len(cases)))
    write(HERE/'artifact_manifest.json',{p.name:sha(p) for p in HERE.glob('*') if p.is_file() and p.name not in ['artifact_manifest.json','run.log','run_errors.log']})
    print(json.dumps(groups,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','scan','quotes','report']);args=parser.parse_args()
    globals()[args.action]()

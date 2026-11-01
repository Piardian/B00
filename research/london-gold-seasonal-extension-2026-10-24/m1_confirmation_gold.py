"""M1 confirmation candidate on frozen gold tapes."""
from pathlib import Path
import sys,json,os
import numpy as np,pandas as pd
BASE=Path(__file__).resolve().parent;ORB_MIN=int(os.environ.get('ORB_MIN','15'));MIN_RANGE=float(os.environ.get('MIN_RANGE','0'));CONFIRM=int(os.environ.get('CONFIRM','1'));GRADE=os.environ.get('GRADE','ALL');REGIME=os.environ.get('REGIME','ALL');HTF=pd.read_csv(BASE/'htf_bias_causal.csv').set_index('date')['htf_bias'] if (BASE/'htf_bias_causal.csv').exists() else None;OUT=BASE/f'm1_candidate_{GRADE}_{REGIME}';OUT.mkdir(exist_ok=True)
D1=pd.read_parquet(BASE/'gold_d1.parquet');D1['date']=pd.to_datetime(D1.time,unit='s',utc=True).dt.tz_convert('Europe/London').dt.strftime('%Y-%m-%d');D1['r']=D1.high-D1.low;D1['pr']=D1.r.shift(1);D1['q33']=D1.pr.rolling(60,min_periods=20).quantile(.33);D1['q67']=D1.pr.rolling(60,min_periods=20).quantile(.67);RANGE_MAP=D1.set_index('date')[['pr','q33','q67']].to_dict('index')
sys.path.insert(0,str(BASE));import study as s;g=s.g
def save(n,x):g.save(OUT/n,x)
def freeze():
 files=[Path(__file__),BASE/'study.py',BASE/'protocol_frozen.json',BASE/'quote_manifest.json',BASE/'outcomes.json']
 save('protocol_frozen.json',dict(hypothesis='M1 close outside ORB, retest broken band, next completed M1 closes beyond previous M1 extreme and outside ORB; next quote entry before noon.',unchanged='Gold quote sides, virtual BID stop, 2R, EOD16 and costs; no Asia/summer/cost filters.',classification='Posthoc development candidate; no OOS/live claim.',hashes={str(p):g.sha(p) for p in files},live_approved=False))
def plan(f,date):
 t=pd.DatetimeIndex(f.time);b=f.bid.to_numpy(float);st=pd.Timestamp(date+' 08:00',tz='Europe/London').tz_convert('UTC');dl=st+pd.Timedelta(hours=4);nat=f[(f['flags'].astype('int64')&2)!=0].set_index('time').bid;op=nat[(nat.index>=st)&(nat.index<st+pd.Timedelta(minutes=ORB_MIN))]
 if op.empty or t[0]>st+pd.Timedelta(seconds=5) or t[-1]<st+pd.Timedelta(hours=8) or f.time.diff().max()>pd.Timedelta(seconds=60):return {'status':'BLOCKED'}
 hi,lo=float(op.max()),float(op.min());
 rr=RANGE_MAP.get(date,{}); regime='MID' if rr and pd.notna(rr.get('q33')) and rr['q33']<=rr['pr']<=rr['q67'] else ('HIGH' if rr and pd.notna(rr.get('q67')) and rr['pr']>rr['q67'] else 'LOW')
 if REGIME!='ALL' and regime!=REGIME:return {'status':'REGIME_FILTER'}
 if hi-lo<MIN_RANGE:return {'status':'RANGE_FILTER'}
 d=int(np.sign(op.iloc[-1]-op.iloc[0]));
 if GRADE in ('A+','A++') and HTF is not None:
  bias=HTF.get(date,'NEUTRAL'); expected='LONG' if d==1 else 'SHORT'
  if bias!=expected:return {'status':'HTF_FILTER'}
 bars=nat.resample('1min').ohlc();br=None
 for m in pd.date_range(st+pd.Timedelta(minutes=ORB_MIN),dl-pd.Timedelta(minutes=2),freq='min'):
  if m in bars.index and not bars.loc[m].isna().any() and ((bars.loc[m,'close']>hi) if d==1 else (bars.loc[m,'close']<lo)):br=m+pd.Timedelta(minutes=1);break
 if br is None:return {'status':'NO_BREAK'}
 touch=np.flatnonzero((t>=br)&(t<dl)&((b<=hi) if d==1 else (b>=lo)))
 if not len(touch):return {'status':'NO_RETEST'}
 ti=int(touch[0]);stop=lo if d==1 else hi
 confirm = 2 if GRADE=='A++' else CONFIRM
 if confirm==0:
  av=t[ti];ix=np.flatnonzero((t>=av)&(t<dl))
  if len(ix) and t[ix[0]]<=av+pd.Timedelta(seconds=5):return {'status':'ENTRY','i':int(ix[0]),'d':d,'stop':stop}
 for m in pd.date_range(t[ti].floor('min')+pd.Timedelta(minutes=1),dl-pd.Timedelta(minutes=2),freq='min'):
  prev=m-pd.Timedelta(minutes=1)
  if m not in bars.index or prev not in bars.index or bars.loc[[prev,m]].isna().any().any():continue
  c=float(bars.loc[m,'close']);ok=(c>bars.loc[prev,'high'] and c>hi) if d==1 else (c<bars.loc[prev,'low'] and c<lo)
  if ok and (confirm==1 or ((m+pd.Timedelta(minutes=1)) in bars.index and ((bars.loc[m+pd.Timedelta(minutes=1),'close']>hi) if d==1 else (bars.loc[m+pd.Timedelta(minutes=1),'close']<lo)))):
   av=m+pd.Timedelta(minutes=1);ix=np.flatnonzero((t>=av)&(t<dl))
   if len(ix) and t[ix[0]]<=av+pd.Timedelta(seconds=5):return {'status':'ENTRY','i':int(ix[0]),'d':d,'stop':stop}
 return {'status':'NO_CONFIRMATION'}
def execute(f,date,p,m):
 if p['status']!='ENTRY':return p
 t=pd.DatetimeIndex(f.time);b=f.bid.to_numpy(float);a=b+(f.ask.to_numpy(float)-b)*m;sl=.05*m;i=p['i'];d=p['d'];e=a[i]+sl if d==1 else b[i]-sl;stop=p['stop'];risk=e-stop if d==1 else stop+(a[i]-b[i])-e
 if risk<=0:return {'status':'INVALID'}
 tar=e+d*2*risk;end=pd.Timestamp(date+' 16:00',tz='Europe/London').tz_convert('UTC');stp=b<=stop if d==1 else b>=stop;tp=b>=tar if d==1 else a<=tar;h=(t>=end)|stp|tp;h[:i+1]=False;ix=np.flatnonzero(h)
 if not len(ix):return {'status':'UNKNOWN'}
 j=int(ix[0]);reason='EOD' if t[j]>=end else 'SL' if stp[j] else 'TP2';x=tar-sl*d if reason=='TP2' else b[j]-sl if d==1 else a[j]+sl;comm=max(8.,2*e*100*.001/100)/100*m;pn=d*(x-e)/risk
 return {'status':'CLOSED','net_r':float(pn-comm/risk),'reason':reason}
def summary(rows,cal):
 v=np.array([x['outcome']['net_r'] for x in rows if x['outcome']['status']=='CLOSED']);loss=-v[v<0].sum();d=pd.Series(0.,index=cal)
 for x in rows:
  if x['outcome']['status']=='CLOSED':d.loc[x['date']]+=x['outcome']['net_r']
 rng=np.random.default_rng(173);tot=[]
 for _ in range(10000):
  ix=((rng.integers(0,len(d),size=(len(d)+4)//5)[:,None]+np.arange(5)).ravel())[:len(d)]%len(d);tot.append(d.to_numpy()[ix].sum())
 return dict(fills=len(v),net_r=float(v.sum()),pf=float(v[v>0].sum()/loss) if loss else None,ci95=np.quantile(tot,[.025,.975]).tolist(),without_best5=float(np.sort(v)[:-5].sum()) if len(v)>=5 else None)
def run():
 freeze();mf=s.read('quote_manifest.json');rows=[]
 for date in g.dates(s.MONTHS):
  meta=mf['files'][date]
  for name,m in g.SCENARIOS:
   o={'status':meta['status']} if meta['status']!='AVAILABLE' else execute((f:=pd.read_parquet(meta['path'])),date,plan(f,date),m);rows.append({'date':date,'scenario':name,'outcome':o})
 save('outcomes.json',rows);res={}
 for period,months in [('2025_full',s.MONTHS[:12]),('2025_new_SepDec',s.MONTHS[8:12]),('2026_partial',s.MONTHS[12:]),('all',s.MONTHS)]:
  cal=g.dates(months);res[period]={name:summary([x for x in rows if x['scenario']==name and x['date'][:7] in months],cal) for name,m in g.SCENARIOS}
 save('results.json',dict(results=res,orders_sent=False,live_approved=False));save('completion.json',dict(status='COMPLETE_RESEARCH',hashes={n:g.sha(OUT/n) for n in ['protocol_frozen.json','outcomes.json','results.json']}));print('M1_COMPLETE',res['2025_full']['STRESS_1.5x'],flush=True)
if __name__=='__main__':run()

"""Observe original gate passage without changing a decision condition."""
import ast,copy,json,types
from collections import Counter
import pandas as pd
import complete as s

STAGES=['CALL','WICK_PASS','POOL_AVAILABLE','POOL_SESSION_PASS','SWEEP_RECLAIM',
 'EXTREME_HELD','NO_EARLIER_TRIGGER_BREAK','CURRENT_TRIGGER_BREAK','BODY_DISPLACEMENT',
 'STRUCTURAL_CONFIRM','CE_SOURCE_ACCEPTED']

def tag(test):
    t=ast.unparse(test)
    if t=='wick / rng < self.min_wick_ratio':return 'WICK_PASS'
    if t.startswith('not pool or pool['):return 'POOL_AVAILABLE'
    if t.startswith("name.startswith('asian')"):return 'POOL_SESSION_PASS'
    if t=='not swept':return 'SWEEP_RECLAIM'
    if t.startswith('any((') and 'extreme' in t:return 'EXTREME_HELD'
    if t.startswith('any((') and 'trigger' in t:return 'NO_EARLIER_TRIGGER_BREAK'
    if t.startswith('not (closes[i] > trigger'):return 'CURRENT_TRIGGER_BREAK'
    if t.startswith('abs(closes[i] - opens[i]) /'):return 'BODY_DISPLACEMENT'
    if t=='confirmation is None':return 'STRUCTURAL_CONFIRM'
    if t.startswith('config.USE_IFVG_ENTRY and ce['):return 'CE_SOURCE_ACCEPTED'
    return None

def event(stage):return ast.Expr(value=ast.Call(func=ast.Name(id='_audit_stage',ctx=ast.Load()),args=[ast.Constant(stage)],keywords=[]))

class Insert(ast.NodeTransformer):
    def __init__(self):self.tags=[]
    def visit_If(self,node):
        node=self.generic_visit(node);stage=tag(node.test)
        if stage:self.tags.append(stage);return [node,event(stage)]
        return node

def instrument(module,callback):
    text=(s.HERE/'frozen_engine/sfp_detector.py').read_text(encoding='utf8')
    tree=ast.parse(text)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='SFPDetector')
    fn=copy.deepcopy(next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_detect_confirmed_sfp'))
    insert=Insert();fn=insert.visit(fn);fn.body.insert(0,event('CALL'))
    assert set(insert.tags)==set(STAGES)-{'CALL'},insert.tags
    code=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]))
    env=module.__dict__.copy();env['_audit_stage']=callback
    exec(compile(code,'<original_sfp_counter_instrumentation>','exec'),env)
    return env['_detect_confirmed_sfp'],insert.tags

def main():
    m=s.measure();m.verify();c,d,e=m.engine()
    expected={r['case_id']:r for r in m.read(s.HERE/'cases_frozen.json')}
    seen=set();fn,tags=instrument(d,seen.add);detector=d.SFPDetector()
    detector._detect_confirmed_sfp=types.MethodType(fn,detector)
    rows=[];matched=0;scanned=0
    for symbol in m.SYMBOLS:
        bars,hourly,qa=m.load_prices(symbol);mi=pd.DatetimeIndex(bars.datetime);hi=pd.DatetimeIndex(hourly.datetime)
        cache={};sym=symbol[:3]+'/'+symbol[3:]
        for month in m.MONTHS:
            counts=Counter();calendar=Counter()
            start=pd.Timestamp(month+'-01',tz='UTC');end=start+pd.offsets.MonthBegin(1)
            for at in pd.date_range(start,end,freq='15min',inclusive='left'):
                now=at.to_pydatetime()
                if not(c.is_market_open(sym,now) and c.is_session_active_for_scan(sym,now)):continue
                calendar['planned']+=1;pos=mi.searchsorted(at-pd.Timedelta(minutes=15),side='right')
                if not pos or mi[pos-1]!=at-pd.Timedelta(minutes=15):calendar['missing_bar']+=1;continue
                hist=bars.iloc[max(0,pos-300):pos].reset_index(drop=True)
                key=at.floor('h')
                if key not in cache:
                    hp=hi.searchsorted(at-pd.Timedelta(hours=1),side='right')
                    cache[key]=e.higher_timeframe_trend(hourly.iloc[max(0,hp-1000):hp],at)
                trend=cache[key]
                if trend not in ['BULLISH','BEARISH']:calendar['htf_neutral_or_not_ready']+=1;continue
                seen.clear();got=detector.detect_sfp(hist,sym,htf_trend=trend)
                case_id=symbol+'_'+at.isoformat();want=expected.get(case_id)
                assert json.dumps(got,default=str,sort_keys=True)==json.dumps(want['signal'] if want else None,default=str,sort_keys=True),case_id
                if got:matched+=1
                for stage in seen:counts[stage]+=1
                scanned+=1
            values=[counts[stage] for stage in STAGES]
            assert values==sorted(values,reverse=True),(symbol,month,counts)
            rows.append(dict(symbol=symbol,month=month,calendar=dict(calendar),stage_counts={k:counts[k] for k in STAGES}))
            m.write(s.HERE/'funnel_status.json',dict(symbol=symbol,month=month,scanned=scanned,signals_matched=matched))
            print('FUNNEL',symbol,month,'SCANNED',counts['CALL'],'SIGNALS',counts['CE_SOURCE_ACCEPTED'],flush=True)
    assert matched==57 and scanned==18860
    total={stage:sum(r['stage_counts'][stage] for r in rows) for stage in STAGES}
    result=dict(unique_window_stage_counts=total,rows=rows,stage_order=STAGES,
       instrumented_windows=scanned,signals_matched=matched,decision_equivalence_passed=True,
       caveat='Common upstream funnel measured in unchanged noIFVG branch. Counts are unique windows passing >=one pool/sweep path, not independent filters or unique executed trades. Original mandatoryIFVG reference has8accepted signals. No macro/news/cooldown/occupancy applied here.')
    m.write(s.HERE/'funnel.json',result)
    labels=['HTF uyumlu tarama','En azbir uygun fitil','İzinli likidite havuzu mevcut','Havuz seansı uygun',
       'Seviye süpürülüp içinde kapanış','Sweep ucu bozulmamış','Kırılım daha önce gerçekleşmemiş','Güncel kapanışla kırılım',
       'Kırılım mumunda gövde en az%35','Breaker yapı teyidi','Mevcut CE giriş kaynağı kabul']
    lines=['# Neden az sinyal üretiyor?','',
      'Üç varlık,15dakikalık karar anları, hafta içi07–11:59 ve13–17:59UTC. 28.560planlı varlık-zaman penceresinin160ında karar mumu yok (1Ocak ve altın18Nisan kapanışları);9.540ında4H trendi nötr/hazır değil. Kalan18.860pencereye gerçek dedektör uygulanıyor.','',
      '| Koşuldan geçen eşsiz karar penceresi | Sayı |','|---|---:|']
    for stage,label in zip(STAGES,labels):lines.append(f'| {label} | {total[stage]} |')
    lines+=['| Orijinal zorunlu iFVG modeliyle son kabul | 8 |','',
      'Bu tablo işlem sayısı değildir. Aynı pencerede farklı havuz/sweep yolları denenebilir; her aşamada pencere en fazla bir kez sayılır. Koşulların bağımsız etkisi veya elenenlerin kârlılığı bu sayılardan çıkarılamaz.','',
      '15dakikalık mum kapanışı gerekir; süpürme önceki1–3mumda olmalı; fitil en az%45, eskiuç bozulmamış, ilk yapı kırılımı ve en az%35gövde gerekir. Üst trend uyumu ve breaker eklenir. Orijinal model ayrıca iFVG ve uygun CE kaynağı ister. Ardından limitin gerçekten dolması gerekir. Az işlem, bu koşulların birlikte nadir oluşmasının sonucudur; filtreleri azaltmak kârı garanti etmez.','',
      'AST yalnızca sayaç çağrıları ekledi; hiçbir koşul değiştirilmedi.18.860kararın tamamında çıktı orijinal kayıtla karşılaştırıldı;57sinyal birebir eşleşti. Canlı makro/haber/aktifpozisyon engelleri eklenirse sayı daha da azalabilir; bu engeller bu tabloda uygulanmadı.']
    (s.HERE/'FUNNEL.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(total)

if __name__=='__main__':main()

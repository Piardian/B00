"""Do not impute two unknown winter dates; separately report fully covered summers."""
import study as s
import cost_gate as c
import pandas as pd
g=s.g

def main():
    s.verify();rows=s.read('outcomes.json');cost=g.read(s.BASE/'cost_gate/outcomes.json')
    old=g.read(s.v.OLD/'outcomes.json')+g.read(s.VALID/'outcomes.json')
    current={(r['date'],r['scenario']):r['outcome'] for r in rows}
    for r in old:assert current[(r['date'],r['scenario'])]==r['outcome']
    sums={}
    for year in ['2025','2026']:
        months=[year+'-'+m for m in ['06','07','08']];cal=g.dates(months);sums[year]={}
        for name,m in g.SCENARIOS:
            selected=[r for r in rows if r['scenario']==name and r['date'][:7] in months]
            assert not any(r['outcome']['status'] in g.UNKNOWN for r in selected)
            stats=s.v.stats(selected,cal)
            sums[year][name]=dict(complete=True,summer=stats,shutdown_avoided_net_r=-stats['net_r'])
    common={}
    for group,months in {'2026JanSep_partial':s.MONTHS[12:],'all21months':s.MONTHS}.items():
        common[group]={}
        for name,m in g.SCENARIOS:
            a=[r for r in rows if r['scenario']==name and r['date'][:7] in months]
            b=[r for r in cost if r['scenario']==name and r['date'][:7] in months]
            bad={r['date'] for r in a+b if r['outcome']['status'] in g.UNKNOWN}
            cal=[d for d in g.dates(months) if d not in bad]
            aa=s.v.stats([r for r in a if r['date'] not in bad],cal);bb=s.v.stats([r for r in b if r['date'] not in bad],cal)
            common[group][name]=dict(classification='Resolved common dates only, excludes same two winter dates from both; NOT full period.',excluded_dates=sorted(bad),common_dates=len(cal),baseline=aa,costgate=bb,paired_delta_net_r=bb['net_r']-aa['net_r'])
    f=pd.read_parquet(s.read('quote_manifest.json')['files']['2026-03-16']['path']);gap=f.time.diff().dt.total_seconds();i=gap.idxmax()
    g.save(s.BASE/'coverage_diagnostics.json',dict(summers=sums,cost_common_known=common,prior_parity_all_173_days_passed=True,
        unresolved={'2026-03-16':dict(max_quote_gap_seconds=float(gap.max()),gap_from=str(f.time.iloc[i-1]),gap_to=str(f.time.iloc[i]),native_price_mismatch=True),
                    '2026-04-03':dict(no_london_ticks=True,overnight_native_quotes_present=True,reason='Cannot classify as full-day closed under frozen noD1-and-noLondonM15 holiday rule; unknown retained.')},
        note='Summer-only paired shutdown effect identified because all JuneAug dates covered; unknown dates lie outside summer where policies identical. Full2026 and combined net returns remain unidentified. Cost common subset is descriptive, not full result.'))
    print('COVERAGE_DIAGNOSTICS_COMPLETE',flush=True)

if __name__=='__main__':main()

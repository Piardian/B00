"""The5ers read-only symbol, existing fee and native-bar evidence. No orders."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,shutil
import pandas as pd
import MetaTrader5 as mt5

BASE=Path(__file__).resolve().parent
TERMINAL='C:/Program Files/Five Percent Online MetaTrader 5/terminal64.exe'
def main():
    if not mt5.initialize(TERMINAL,timeout=10000):raise RuntimeError(str(mt5.last_error()))
    try:
        assert mt5.account_info().server=='FivePercentOnline-Real'
        s=mt5.symbol_info('XAUUSD');keys=['name','description','digits','point','trade_tick_size','trade_tick_value','trade_contract_size','currency_profit','volume_min','volume_max','volume_step','trade_calc_mode','trade_stops_level']
        spec={k:getattr(s,k) for k in keys}
        deals=mt5.history_deals_get(datetime(2024,1,1,tzinfo=timezone.utc),datetime.now(timezone.utc),group='*XAU*')
        fee_rows=[]
        for d in deals or []:
            if d.symbol!='XAUUSD' or d.volume<=0 or d.commission>=0:continue
            notional=d.price*s.trade_contract_size*d.volume;c=-d.commission
            fee_rows.append(dict(month=datetime.fromtimestamp(d.time,timezone.utc).strftime('%Y-%m'),entry=int(d.entry),
                commission_usd_per_lot=c/d.volume,other_fee=d.fee,
                per_side_0_001_percent_matches_cent_rounding=round(notional*.001/100,2)==round(c,2),
                rate_percent_rounding_low=max(0,(c-.005)/notional*100),rate_percent_rounding_high=(c+.005)/notional*100))
        evidence=dict(captured_utc=datetime.now(timezone.utc).isoformat(),server='FivePercentOnline-Real',symbol_spec=spec,
            numeric_commission_exposed_in_symbol_info=False,existing_fill_fee_records=fee_rows,
            fee_limitations='Only2026Octoberobservations;numericpercentageunidentified;flat4USD/lot/sideand0.001percent/sidebothfitcents;not2025tariffproof',
            official_sources=['https://the5ers.com/faqs/what-are-the-spreads-and-commissions/','https://lp.the5ers.com/hub-assets-specifications/'],
            official_claim='Goldcontract100ounces;percentagebasedcommission;publicnumericratenotgiven',
            script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),read_only=True)
        (BASE/'cost_evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf8')
        for symbol,tf,label in [('XAUUSD',mt5.TIMEFRAME_M15,'gold_m15'),('XAUUSD',mt5.TIMEFRAME_D1,'gold_d1'),('EURUSD',mt5.TIMEFRAME_M15,'clock_eurusd_m15')]:
            raw=mt5.copy_rates_range(symbol,tf,datetime(2025,1,1,tzinfo=timezone.utc),datetime(2025,7,2,tzinfo=timezone.utc))
            if raw is None or not len(raw):raise RuntimeError('Missing native'+label+str(mt5.last_error()))
            pd.DataFrame(raw).to_parquet(BASE/f'{label}.parquet',compression='zstd')
            print('NATIVE',label,len(raw),flush=True)
        print('SPEC',json.dumps(spec),'COST_RECORDS',len(fee_rows),'FREE_GIB',round(shutil.disk_usage(BASE).free/1024**3,2))
    finally:mt5.shutdown()

if __name__=='__main__':main()

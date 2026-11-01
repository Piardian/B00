from pathlib import Path
import pandas as pd

BASE=Path(__file__).resolve().parent
d=pd.read_parquet(BASE/'gold_d1.parquet').copy()
d['dt']=pd.to_datetime(d['time'],unit='s',utc=True).dt.tz_convert('Europe/London').dt.strftime('%Y-%m-%d')
d['prior_day_close']=d['close'].shift(1)
d['prior_20d_sma']=d['prior_day_close'].rolling(20,min_periods=20).mean()
d['htf_bias']=d.apply(lambda r:'LONG' if pd.notna(r.prior_20d_sma) and r.prior_day_close>r.prior_20d_sma else ('SHORT' if pd.notna(r.prior_20d_sma) and r.prior_day_close<r.prior_20d_sma else 'NEUTRAL'),axis=1)
out=d[['dt','htf_bias','prior_day_close','prior_20d_sma']].rename(columns={'dt':'date'})
out.to_csv(BASE/'htf_bias_causal.csv',index=False)
print('HTF_READY',len(out),out.htf_bias.value_counts().to_dict())

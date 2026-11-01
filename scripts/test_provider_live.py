import pandas as pd
from sfp_orb_engine.data_provider import MarketDataProvider

provider = MarketDataProvider()

symbols = ["EUR/USD", "GBP/USD", "XAU/USD", "BTC/USD"]

for s in symbols:
    print(f"\n================ Testing {s} ================")
    for interval, count in [("1m", 1000), ("15m", 300), ("1h", 1000)]:
        df = provider.fetch_candles(s, interval=interval, outputsize=count)
        if df is None or df.empty:
            print(f"  {interval} (req {count}): FAILED (None or empty)")
        else:
            last_time = df.iloc[-1].get("datetime", df.iloc[-1].get("time"))
            first_time = df.iloc[0].get("datetime", df.iloc[0].get("time"))
            print(f"  {interval} (req {count}): SUCCESS (len={len(df)}), range={first_time} -> {last_time}")
            if interval == "1m":
                now_utc = pd.Timestamp.now(tz="UTC")
                diff_sec = (now_utc - pd.to_datetime(last_time, utc=True)).total_seconds()
                print(f"     1m age diff vs now_utc: {diff_sec:.1f} seconds (limit was 180s!)")

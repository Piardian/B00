"""Real 2025 prices: broker bid ticks, TwelveData ETF quotes, Binance archives."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import time
import zipfile

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sfp_orb_engine.config import ACTIVE_SYMBOLS, EXCLUDED_SFP_SYMBOLS, is_crypto, TWELVE_DATA_KEYS

MONTHS = ["2025-01", "2025-06", "2025-11"]
COLS = ["datetime", "open", "high", "low", "close", "volume"]


def window(month):
    start = pd.Timestamp(month+"-01", tz="UTC")
    return start, start + pd.offsets.MonthBegin(1)


def save_frame(path, frames):
    if not frames:
        return 0
    df = pd.concat(frames).sort_values("datetime").drop_duplicates("datetime")
    disk_check(path.parent)
    temporary = path.with_name(path.name + ".partial")
    df[COLS].to_csv(temporary, index=False, compression="gzip")
    temporary.replace(path)
    return len(df)


def disk_check(root):
    if shutil.disk_usage(root).free < 1024**3:
        raise RuntimeError("Less than 1GiB free; collection stopped without deleting user files")


def collect_crypto(root):
    cache = root / "binance_zips"
    cache.mkdir(exist_ok=True)
    months = set()
    for month in MONTHS:
        start, end = window(month)
        months.update(pd.period_range((start-pd.Timedelta(days=65)).tz_localize(None), end.tz_localize(None)-pd.Timedelta(days=1), freq="M").astype(str))
    jobs = []
    for symbol in ACTIVE_SYMBOLS:
        if not is_crypto(symbol):
            continue
        ticker = symbol.replace("/", "")[:-3] + "USDT"
        for tf in ("1m", "15m", "1h"):
            for month in (MONTHS if tf == "1m" else sorted(months)):
                jobs.append((symbol, ticker, tf, month))
    manifest = []
    frames = {}
    def download(job):
        symbol, ticker, tf, month = job
        name = f"{ticker}-{tf}-{month}.zip"
        path = cache / name
        url = f"https://data.binance.vision/data/spot/monthly/klines/{ticker}/{tf}/{name}"
        if not path.exists():
            disk_check(root)
            for attempt in range(3):
                try:
                    response = requests.get(url, timeout=30)
                    if response.status_code == 404:
                        return job, None, {"url": url, "status": "ARCHIVE_404"}
                    response.raise_for_status()
                    path.write_bytes(response.content)
                    break
                except requests.RequestException:
                    if attempt == 2:
                        return job, None, {"url": url, "status": "DOWNLOAD_FAILED"}
                    time.sleep(attempt+1)
        raw = path.read_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            df = pd.read_csv(z.open(z.namelist()[0]), header=None)
        stamps = pd.to_numeric(df[0], errors="coerce")
        df = df[stamps.notna()].copy()
        stamps = stamps[stamps.notna()]
        unit = "us" if stamps.max() > 1e14 else "ms"
        result = pd.DataFrame({"datetime": pd.to_datetime(stamps, unit=unit, utc=True),
                               **{col: pd.to_numeric(df[i]) for col, i in [("open",1),("high",2),("low",3),("close",4),("volume",5)]}})
        start, end = window(month)
        result = result[(result.datetime >= start) & (result.datetime < end)]
        return job, result, {"url": url, "status": "OK", "rows": len(result), "sha256": hashlib.sha256(raw).hexdigest()}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(download, j) for j in jobs]
        for index, future in enumerate(as_completed(futures), 1):
            job, frame, record = future.result()
            symbol, ticker, tf, month = job
            manifest.append({"symbol": symbol, "timeframe": tf, "month": month, **record})
            if frame is not None:
                frames.setdefault((symbol, tf), []).append(frame)
            if index % 40 == 0:
                print("crypto", index, "/", len(jobs), flush=True)
                (root / "crypto_manifest.json").write_text(json.dumps(manifest, indent=2))
    for (symbol, tf), group in frames.items():
        save_frame(root / f"{symbol.replace('/', '')}_{tf}.csv.gz", group)
    (root / "crypto_manifest.json").write_text(json.dumps(manifest, indent=2))


def collect_broker(root):
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError("MT5 unavailable")
    manifest_path = root / "broker_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    tick_base = Path(mt5.terminal_info().data_path) / "bases" / mt5.account_info().server / "ticks"
    cleanup = []
    parts = root / "broker_parts"
    parts.mkdir(exist_ok=True)
    study_start = datetime.fromisoformat("2026-10-22T19:00:00").timestamp()
    def release_intermediate(symbol_cache, clean):
        for cached in symbol_cache.glob("*.tkc"):
            if cached.stat().st_ctime < study_start or not cached.stem.isdigit() or cached.stem >= datetime.now().strftime('%Y%m'):
                continue
            target_months = {'202501':'2025-01','202506':'2025-06','202511':'2025-11'}
            month = target_months.get(cached.stem)
            if month and not all((parts/f'{clean}_{tf}_{month}.csv.gz').exists() for tf in ('1m','15m','1h')):
                continue
            resolved=cached.resolve()
            if resolved.parent != symbol_cache or not resolved.is_relative_to(tick_base.resolve()):
                raise RuntimeError('Historical cache path escaped verified terminal symbol directory')
            record={'path':str(resolved),'bytes':cached.stat().st_size,'reason':'Task-generated intermediate cache or fully exported monthly part'}
            try:cached.unlink();record['status']='REMOVED'
            except PermissionError:record['status']='PRESERVED_TERMINAL_LOCK'
            cleanup.append(record)
        (root/'collector_tick_cache_cleanup.json').write_text(json.dumps(cleanup,indent=2))
    for symbol in ACTIVE_SYMBOLS:
        if is_crypto(symbol) or symbol in EXCLUDED_SFP_SYMBOLS or symbol in {"NAS100", "QQQ", "SPY"}:
            continue
        clean = symbol.replace("/", "")
        mt5.symbol_select(clean, True)
        if all((root / f"{clean}_{tf}.csv.gz").exists() for tf in ("1m", "15m", "1h")):
            print("broker already exported", symbol, flush=True)
            continue
        symbol_cache = (tick_base / clean).resolve()
        if not symbol_cache.is_relative_to(tick_base.resolve()):
            raise RuntimeError("Tick cache path escaped the named terminal directory")
        existing_cache = set(symbol_cache.glob("*.tkc"))
        group = {tf: [] for tf in ("1m", "15m", "1h")}
        for month in MONTHS:
            if all((parts/f'{clean}_{tf}_{month}.csv.gz').exists() for tf in group):
                for tf in group:
                    saved=pd.read_csv(parts/f'{clean}_{tf}_{month}.csv.gz')
                    saved.datetime=pd.to_datetime(saved.datetime,utc=True)
                    group[tf].append(saved)
                continue
            release_intermediate(symbol_cache,clean)
            start, end = window(month)
            month_frames={tf:[] for tf in group}
            for tf, native in [("15m", mt5.TIMEFRAME_M15), ("1h", mt5.TIMEFRAME_H1)]:
                rates = mt5.copy_rates_range(clean, native, (start-pd.Timedelta(days=65)).to_pydatetime(), end.to_pydatetime())
                if rates is None or not len(rates):
                    raise RuntimeError(f"No broker {symbol} {tf} {month}")
                df = pd.DataFrame(rates)
                df["datetime"] = pd.to_datetime(df.time, unit="s", utc=True)
                df = df[(df.datetime >= start-pd.Timedelta(days=65)) & (df.datetime < end)]
                df["volume"] = df.tick_volume
                group[tf].append(df[COLS])
                month_frames[tf].append(df[COLS])
            for day in pd.date_range(start, end, freq="D", inclusive="left"):
                release_intermediate(symbol_cache,clean)
                disk_check(root)
                stop = day + pd.Timedelta(days=1)
                ticks = mt5.copy_ticks_range(clean, day.to_pydatetime(), stop.to_pydatetime(), mt5.COPY_TICKS_ALL)
                if ticks is None:
                    time.sleep(2)
                    ticks = mt5.copy_ticks_range(clean, day.to_pydatetime(), stop.to_pydatetime(), mt5.COPY_TICKS_ALL)
                if ticks is None:
                    raise RuntimeError(f"Tick history unavailable: {symbol} {day}")
                raw_hash = hashlib.sha256(ticks.tobytes()).hexdigest()
                if not len(ticks):
                    manifest.append({"symbol": symbol, "day": day.isoformat(), "status": "NO_TICKS", "raw_sha256": raw_hash})
                    continue
                df = pd.DataFrame(ticks)
                df["datetime"] = pd.to_datetime(df.time_msc, unit="ms", utc=True)
                df = df[(df.datetime >= day) & (df.datetime < stop) & (df.bid > 0)]
                if df.empty:
                    raise RuntimeError(f"Only out-of-range ticks: {symbol} {day}")
                quotes = df.set_index("datetime").bid
                bars = quotes.resample("1min").ohlc()
                bars["volume"] = quotes.resample("1min").count()
                bars = bars.dropna().reset_index()
                group["1m"].append(bars)
                month_frames['1m'].append(bars)
                manifest.append({"symbol": symbol, "day": day.isoformat(), "ticks": len(df), "minutes": len(bars),
                                 "raw_sha256": raw_hash, "source": "MT5 real bid ticks; native tick count; no interpolation"})
            print("broker", symbol, month, "minute_rows",sum(len(f) for f in group['1m']),flush=True)
            for tf in group:
                save_frame(parts/f'{clean}_{tf}_{month}.csv.gz',month_frames[tf])
            (root / "broker_manifest.json").write_text(json.dumps(manifest, indent=2))
        for tf, frames in group.items():
            save_frame(root / f"{clean}_{tf}.csv.gz", frames)
        (root / "broker_manifest.json").write_text(json.dumps(manifest, indent=2))
        # Only remove files created by this collector after their quotes have
        # been exported. Preserve all preexisting files and the live month.
        for cached in symbol_cache.glob("*.tkc"):
            resolved = cached.resolve()
            if cached in existing_cache or not cached.stem.isdigit() or len(cached.stem) != 6:
                continue
            if cached.stem >= datetime.now().strftime("%Y%m"):
                continue
            if resolved.parent != symbol_cache or not resolved.is_relative_to(tick_base.resolve()):
                raise RuntimeError("Refusing tick cache cleanup outside verified symbol directory")
            if not all((root / f"{clean}_{tf}.csv.gz").stat().st_size > 0 for tf in group):
                raise RuntimeError("Missing price exports; preserving raw tick cache")
            record = {"path": str(resolved), "bytes": cached.stat().st_size, "symbol": symbol}
            try:
                cached.unlink()
                record["status"] = "REMOVED"
            except PermissionError:
                record["status"] = "PRESERVED_TERMINAL_LOCK"
            cleanup.append(record)
        (root / "collector_tick_cache_cleanup.json").write_text(json.dumps(cleanup, indent=2))
        print("broker exported and released new historical cache", symbol, flush=True)


def collect_etfs(root, forex=False):
    manifest = []
    request_count = 0
    last_request = {}
    exhausted_keys = set()
    universe = [(s.replace('/', ''),s) for s in ACTIVE_SYMBOLS if not is_crypto(s) and s not in EXCLUDED_SFP_SYMBOLS and s not in {"NAS100","QQQ","SPY"}] if forex else [("QQQ", "QQQ"), ("NAS100", "QQQ"), ("SPY", "SPY")]
    for symbol, ticker in universe:
        if symbol == "NAS100":
            continue
        for tf, interval in [("1m","1min"), ("15m","15min"), ("1h","1h")]:
            if forex and (root / f"{symbol}_{tf}.csv.gz").exists():
                print("TwelveData already exported",symbol,tf,flush=True)
                continue
            frames = []
            for month in MONTHS:
                start, end = window(month)
                left = start if tf == "1m" else start-pd.Timedelta(days=65)
                step = pd.Timedelta(days=(3 if forex else 7) if tf == "1m" else 30)
                while left < end:
                    right = min(end, left+step)
                    key_index = request_count % len(TWELVE_DATA_KEYS)
                    request_count += 1
                    wait = max(0., 8.0-(time.monotonic()-last_request.get(key_index, 0.)))
                    if wait: time.sleep(wait)
                    params = dict(symbol=ticker, interval=interval, start_date=left.strftime("%Y-%m-%d %H:%M:%S"),
                                  end_date=right.strftime("%Y-%m-%d %H:%M:%S"), timezone="UTC", outputsize=5000,
                                  apikey=TWELVE_DATA_KEYS[key_index])
                    cache_dir = root / "twelve_raw"
                    cache_dir.mkdir(exist_ok=True)
                    request_id = hashlib.sha256(json.dumps({k:v for k,v in params.items() if k!='apikey'},sort_keys=True).encode()).hexdigest()
                    cached = cache_dir / f"{request_id}.json.gz"
                    if cached.exists():
                        body = json.loads(gzip.decompress(cached.read_bytes()))
                    else:body={}
                    if body.get("status") != "ok" and not (body.get("code")==400 and "no data" in str(body.get("message","")).lower()):
                        for attempt in range(len(TWELVE_DATA_KEYS)):
                            usable=[i for i in range(len(TWELVE_DATA_KEYS)) if i not in exhausted_keys]
                            if not usable:raise RuntimeError("All configured TwelveData keys exhausted their existing daily allowance; no purchase made")
                            key_index=min(usable,key=lambda i:last_request.get(i,0))
                            delay=max(0.,12.0-(time.monotonic()-last_request.get(key_index,0)))
                            if delay:time.sleep(delay)
                            params['apikey']=TWELVE_DATA_KEYS[key_index]
                            body = requests.get("https://api.twelvedata.com/time_series", params=params, timeout=30).json()
                            last_request[key_index] = time.monotonic()
                            if body.get('code')==429:
                                exhausted_keys.add(key_index)
                                print('Existing TwelveData key daily quota exhausted',key_index+1,flush=True)
                                continue
                            cached.write_bytes(gzip.compress(json.dumps(body).encode()))
                            break
                    if body.get("status") != "ok":
                        if body.get("code")==400 and "no data" in str(body.get("message","")).lower():
                            manifest.append({"symbol":symbol,"timeframe":tf,"start":left.isoformat(),"end":right.isoformat(),"status":"NO_SOURCE_BARS"})
                            left=right
                            continue
                        raise RuntimeError(f"TwelveData unavailable {ticker} {tf} {left}: {body.get('code')}")
                    df = pd.DataFrame(body["values"])
                    df.datetime = pd.to_datetime(df.datetime, utc=True)
                    if "volume" not in df:
                        # Identical to the actual live shared-cache adapter for
                        # TwelveData forex, which has no exchange volume.
                        df["volume"] = ((pd.to_numeric(df.high)-pd.to_numeric(df.low))*100000).clip(lower=100.0).round(1)
                    for col in COLS[1:]:
                        df[col] = pd.to_numeric(df[col])
                    df = df[(df.datetime >= left) & (df.datetime < right)]
                    frames.append(df[COLS])
                    manifest.append({"symbol": symbol,"ticker":ticker,"timeframe":tf,"start":left.isoformat(),"end":right.isoformat(),"rows":len(df)})
                    left = right
            count = save_frame(root / f"{symbol}_{tf}.csv.gz", frames)
            if symbol == "QQQ":
                shutil.copyfile(root/f'QQQ_{tf}.csv.gz',root/f'NAS100_{tf}.csv.gz')
            print("ETF",symbol,tf,count,flush=True)
    (root/("forex_manifest.json" if forex else "etf_manifest.json")).write_text(json.dumps(manifest,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind",choices=["crypto","broker","etf","forex"],required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    {"crypto":collect_crypto,"broker":collect_broker,"etf":collect_etfs,"forex":lambda root:collect_etfs(root,forex=True)}[args.kind](args.output)


if __name__=="__main__":main()

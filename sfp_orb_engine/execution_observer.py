"""Passive research archive. Never participates in signal or exit decisions."""
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3

import pandas as pd

from .config import DATA_DIR
from .execution_policy import completed_bars, utc_time


class ExecutionObserver:
    def __init__(self, path=None):
        self.path = Path(path or DATA_DIR / "execution_observations.sqlite3")
        self.follow_until = {}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS bars (
                    symbol TEXT, timeframe TEXT, bar_time TEXT, first_seen_at TEXT,
                    open REAL, high REAL, low REAL, close REAL, volume REAL,
                    fingerprint TEXT, source TEXT,
                    PRIMARY KEY (symbol, timeframe, bar_time, first_seen_at, fingerprint)
                );
                CREATE INDEX IF NOT EXISTS bars_lookup ON bars(symbol, timeframe, bar_time);
                CREATE TABLE IF NOT EXISTS macro_snapshots (
                    fingerprint TEXT, available_at TEXT, source TEXT, payload TEXT,
                    PRIMARY KEY(fingerprint, available_at)
                );
                CREATE TABLE IF NOT EXISTS trade_snapshots (
                    trade_id TEXT, fingerprint TEXT, observed_at TEXT, payload TEXT,
                    PRIMARY KEY(trade_id, fingerprint)
                );
            """)
            last = db.execute("SELECT fingerprint FROM macro_snapshots ORDER BY available_at DESC, rowid DESC LIMIT 1").fetchone()
            self.last_macro_hash = last[0] if last else None

    def needs_capture(self, symbol):
        return self.follow_until.get(symbol, datetime.min.replace(tzinfo=timezone.utc)) > datetime.now(timezone.utc)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=0.2)
        db.execute("PRAGMA journal_mode=WAL")
        return db

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def archive_bars(self, symbol, timeframe, frame, observed_at=None, source=None):
        now = observed_at or self._now()
        minutes = {"1m": 1, "15m": 15, "1h": 60}[timeframe]
        df = completed_bars(frame, minutes, now)
        if df.empty:
            return
        rows = []
        for b in df.to_dict(orient="records"):
            values = tuple(float(b[k]) for k in ("open", "high", "low", "close", "volume"))
            if not all(pd.notna(v) and abs(v) != float("inf") for v in values):
                continue
            digest = hashlib.sha256(json.dumps(values).encode()).hexdigest()
            rows.append((symbol, timeframe, b["datetime"].isoformat(), now, *values, digest,
                         source or "actual_live_provider_return; upstream feed unspecified"))
        with self._connect() as db:
            db.executemany("""INSERT OR IGNORE INTO bars
                SELECT ?,?,?,?,?,?,?,?,?,?,? WHERE ? != COALESCE((SELECT fingerprint FROM bars
                WHERE symbol=? AND timeframe=? AND bar_time=? ORDER BY first_seen_at DESC, rowid DESC LIMIT 1),'')""",
                [row + (row[9], row[0], row[1], row[2]) for row in rows])

    def archive_macro(self, path, observed_at=None):
        path = Path(path)
        if not path.exists():
            return
        raw = path.read_text(encoding="utf-8")
        payload = json.dumps(json.loads(raw), sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        if digest == self.last_macro_hash:
            return
        with self._connect() as db:
            db.execute("INSERT OR IGNORE INTO macro_snapshots VALUES (?,?,?,?)",
                       (digest, observed_at or self._now(), str(path), payload))
        self.last_macro_hash = digest

    def archive_trades(self, trades, observed_at=None):
        now = observed_at or self._now()
        rows = []
        for trade in trades:
            if trade.get("close_reason") in {"STOP_LOSS", "TRAILING_STOP"} and trade.get("closed_at"):
                until = utc_time(trade["closed_at"], legacy_local=True) + timedelta(hours=4)
                if until > datetime.now(timezone.utc):
                    self.follow_until[trade["symbol"]] = max(until, self.follow_until.get(trade["symbol"], until))
            # Ignore polling-only fields to avoid storing identical states each minute.
            payload = json.dumps({k: v for k, v in trade.items() if k != "last_checked_at"},
                                 sort_keys=True, ensure_ascii=False, default=str)
            digest = hashlib.sha256(payload.encode()).hexdigest()
            rows.append((trade["id"], digest, now, payload))
        with self._connect() as db:
            db.executemany("INSERT OR IGNORE INTO trade_snapshots VALUES (?,?,?,?)", rows)

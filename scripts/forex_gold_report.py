"""Ledger-derived diagnostics for the legacy candidate, never a live-edge certificate."""
from pathlib import Path
import hashlib
import json
import sys

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]


def ledger_metrics(frame):
    if len(frame) < 2 or not np.isfinite(frame[['net_r', 'gross_r', 'cost_r']].to_numpy(float)).all():
        raise ValueError('At least two finite trade results required')
    if not np.allclose(frame.gross_r - frame.cost_r, frame.net_r, atol=0.00011):
        raise ValueError('Ledger gross minus cost does not reconcile with net')
    values = frame.net_r.to_numpy(float)
    n = len(values)
    se = values.std(ddof=1) / np.sqrt(n)
    if se == 0:
        raise ValueError('Nonzero sample variance required for t inference')
    t = values.mean() / se
    closed = frame.assign(_closed=pd.to_datetime(frame.closed_at)).sort_values('_closed', kind='stable')
    equity = np.r_[0., closed.net_r.to_numpy(float).cumsum()]
    losses = -values[values < 0].sum()
    return dict(n=n, wins=int((values > 0).sum()), losses=int((values < 0).sum()),
                gross_r=float(frame.gross_r.sum()), cost_r=float(frame.cost_r.sum()),
                net_r=float(values.sum()), win_rate_pct=float(100 * (values > 0).mean()),
                profit_factor=float(values[values > 0].sum() / losses) if losses else None,
                mean_r=float(values.mean()), t=float(t), p_two_sided_iid=float(2 * stats.t.sf(abs(t), n-1)),
                ci95_mean_iid_r=list(map(float, stats.t.interval(.95, n-1, loc=values.mean(), scale=se))),
                closed_equity_max_drawdown_r=float((np.maximum.accumulate(equity) - equity).max()))


def write_report(ledger, report):
    # Read the saved ledger, so report numbers cannot silently differ from CSV.
    frame = pd.read_csv(ledger)
    m = ledger_metrics(frame)
    from scripts.audit_forex_gold_hardened import block_bootstrap
    low, high, nonpositive, _ = block_bootstrap(frame)
    m['bootstrap_total_ci95_r'] = [float(low), float(high)]
    m['bootstrap_nonpositive_fraction'] = float(nonpositive)
    m['ledger_sha256'] = hashlib.sha256(ledger.read_bytes()).hexdigest()
    m['scope'] = 'LEGACY_CANDIDATE_DIAGNOSTICS_NOT_FULL_LIVE_SYSTEM_BACKTEST'
    ci = m['ci95_mean_iid_r']
    lines = [
        '# Forex ve Altın: eski aday simülatörünün işlem defteri özeti', '',
        '**Bu rapor canlı sistemin tam backtesti değildir; doğrulanmış edge veya canlıya geçiş onayı vermez.**', '',
        'Ayrı M15 simülatörü canlı iFVG/Breaker dedektörünü, makro/haber kapılarını ve ortak risk takibini çalıştırmıyor. '
        'Dolumdan önceki hedefin kâr yazılması bağımsız M1 kontrolünde gösterildi. '
        'Aşağıdaki rakamlar bu kusurlu modelin kaydedilmiş defterini özetler; gerçekleşebilir getiri sayılmaz.', '',
        f'İşlem defteri: `{ledger.name}`; SHA256: `{m["ledger_sha256"]}`.', '',
        'Maliyet etiketi: adayın varsayılan 1.0x modeli; 1.5x maliyet sonucu değildir. '
        'Spread sütunu ve varsayılan komisyon/kayma, gerçek broker dolumlarının kanıtı değildir.', '',
        '| Ölçüm | Defterden hesaplanan |', '|---|---:|',
        f'| İşlem | {m["n"]} |',
        f'| Kazanç / kayıp | {m["wins"]} / {m["losses"]} |',
        f'| Kazanma oranı | %{m["win_rate_pct"]:.2f} |',
        f'| Brüt / maliyet / net | {m["gross_r"]:+.4f} / {m["cost_r"]:.4f} / {m["net_r"]:+.4f} R |',
        f'| PF | {m["profit_factor"]} |',
        f'| Ortalama | {m["mean_r"]:+.6f} R |',
        f'| t / iki taraflı p (IID varsayımı) | {m["t"]:.6f} / {m["p_two_sided_iid"]:.6f} |',
        f'| Ortalama için %95 Student t aralığı | [{ci[0]:+.6f}, {ci[1]:+.6f}] R |',
        f'| Kapanış sırasıyla maksimum düşüş | {m["closed_equity_max_drawdown_r"]:.4f} R |',
        f'| Beş işlem günü blok bootstrap toplam %95 aralığı | [{low:+.4f}, {high:+.4f}] R |',
        f'| Bootstrap örneklerinde sıfır veya negatif toplam oranı | %{100*nonpositive:.2f} |', '',
        'IID testi korelasyonu ve seçim yanlılığını çözmez. Bootstrap oranı edge yokluğu olasılığı veya p-değeri değildir. '
        'Düşüş hesabı açık pozisyon zararını içermez. Bloklar beş aktif işlem günüdür; takvim haftası değildir.', '',
        '| Sembol | İşlem | Net R |', '|---|---:|---:|',
    ]
    for symbol, group in frame.groupby('symbol'):
        lines.append(f'| {symbol} | {len(group)} | {group.net_r.sum():+.4f} |')
    lines += ['', '| Açılış yılı | İşlem | Net R |', '|---|---:|---:|']
    for year, group in frame.groupby(pd.to_datetime(frame.opened_at).dt.year):
        lines.append(f'| {year} | {len(group)} | {group.net_r.sum():+.4f} |')
    lines += ['', '2024 yalnızca Aralık verisi; 2026 veri sonuna kadardır. '
              'Hiçbiri bağımsız ve dokunulmamış örneklem dışı doğrulama değildir.', '',
              '[Bağımsız inceleme ve dolum sırası kanıtları](FOREX_GOLD_INDEPENDENT_REVIEW_2026-10-23.md)', '']
    report.write_text('\n'.join(lines), encoding='utf-8')
    report.with_suffix('.json').write_text(json.dumps(m, indent=2, allow_nan=False), encoding='utf-8')
    return m


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    print(json.dumps(write_report(ROOT/'data/forex_gold_verified_trades.csv',
                                 ROOT/'docs/FOREX_GOLD_AUDIT_REPORT.md'), indent=2))

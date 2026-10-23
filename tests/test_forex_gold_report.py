import numpy as np
import pandas as pd
import pytest

from scripts.forex_gold_report import ledger_metrics, write_report


def test_statistics_follow_ledger_and_closed_equity_starts_at_zero():
    frame = pd.DataFrame(dict(net_r=[-1., 2., -1.], gross_r=[-.9, 2.1, -.9],
                              cost_r=[.1]*3, closed_at=['2025-01-01', '2025-01-03', '2025-01-02']))
    m = ledger_metrics(frame)
    assert m['n'] == 3 and m['net_r'] == 0 and m['wins'] == 1
    assert m['closed_equity_max_drawdown_r'] == 2  # both losses close first
    assert m['t'] == 0 and m['p_two_sided_iid'] == 1
    changed = frame.copy()
    changed.loc[1, ['net_r', 'gross_r']] += 1
    assert ledger_metrics(changed)['net_r'] == 1


def test_report_rejects_inconsistent_or_nonfinite_ledger():
    frame = pd.DataFrame(dict(net_r=[-1., 2.], gross_r=[-1., 2.], cost_r=[.1, .1],
                              closed_at=['2025-01-01', '2025-01-02']))
    with pytest.raises(ValueError, match='reconcile'):
        ledger_metrics(frame)
    frame.loc[0, 'net_r'] = np.nan
    with pytest.raises(ValueError, match='finite'):
        ledger_metrics(frame)


def test_saved_report_changes_with_saved_ledger(tmp_path):
    frame = pd.DataFrame(dict(symbol=['EURUSD']*3, net_r=[-1., 2., -1.],
                              gross_r=[-.9, 2.1, -.9], cost_r=[.1]*3,
                              opened_at=['2025-01-01', '2025-01-02', '2025-01-03'],
                              closed_at=['2025-01-01', '2025-01-02', '2025-01-03']))
    ledger, report = tmp_path/'trades.csv', tmp_path/'report.md'
    frame.to_csv(ledger, index=False)
    first = write_report(ledger, report)
    assert '| İşlem | 3 |' in report.read_text(encoding='utf-8')
    assert '| Brüt / maliyet / net | +0.3000 / 0.3000 / +0.0000 R |' in report.read_text(encoding='utf-8')
    frame.loc[1, ['net_r', 'gross_r']] += 1
    frame.to_csv(ledger, index=False)
    second = write_report(ledger, report)
    assert first['ledger_sha256'] != second['ledger_sha256']
    assert second['net_r'] == 1
    assert '+1.0000 R |' in report.read_text(encoding='utf-8')

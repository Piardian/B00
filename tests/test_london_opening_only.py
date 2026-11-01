from types import SimpleNamespace
from unittest.mock import Mock
import pandas as pd
from sfp_orb_engine import config,engine
from sfp_orb_engine.orb_detector import ORBDetector
from sfp_orb_engine.orb_session_context import london_context
from sfp_orb_engine.execution_policy import orb_daily_key,orb_daily_attempt_used
from scripts.replay_live_system import Clock
from test_london_orb_context import bars,history

def test_only_london_enabled_and_ny_tokyo_cannot_fall_through():
    assert config.ORB_ACTIVE_SESSIONS==('LONDON',)
    d=ORBDetector()
    for start in ['2025-06-16 00:00Z','2025-06-16 13:30Z']:
        f=bars();f.datetime=pd.date_range(start,periods=len(f),freq='15min')
        assert d.detect_orb(f,'EUR/USD',hourly_history=history(),as_of=f.iloc[-1].datetime+pd.Timedelta(minutes=15)) is None

def test_local_noon_cutoff_uses_decision_time_not_candle_open():
    for date,utc_hour in [('2025-01-15',12),('2025-06-16',11)]:
        f=bars(date);cut=pd.Timestamp(f'{date} 12:00',tz='Europe/London').tz_convert('UTC')
        assert cut.hour==utc_hour
        # Same data cannot authorize a late replay/delivery after the deadline.
        assert london_context(f,history(date),config.ORB_SESSIONS['LONDON'],15,cut) is None
        d=ORBDetector(volume_detector=SimpleNamespace(analyze=lambda *a,**k:{'spike_ratio':3.}))
        at=f.iloc[-1].datetime+pd.Timedelta(minutes=15)
        s=d.detect_orb(f,'EUR/USD',hourly_history=history(date),as_of=at)
        assert pd.Timestamp(s['entry_deadline_utc'])==cut

def test_daily_cap_includes_no_fill_and_other_direction_but_not_other_pair_or_next_day():
    at=pd.Timestamp('2025-06-16 07:30Z')
    trade=dict(symbol='EUR/USD',strategy='ORB_SESSION_BREAKOUT',direction='LONG',opened_at=str(at),close_reason='EXPIRED_NO_FILL')
    assert orb_daily_attempt_used('EURUSD',at+pd.Timedelta(hours=1),{},[trade])
    assert not orb_daily_attempt_used('GBP/USD',at,{},[trade])
    assert not orb_daily_attempt_used('EUR/USD',at+pd.Timedelta(days=1),{},[trade])
    sfp={**trade,'strategy':'SFP_IFVG_BREAKER'}
    assert not orb_daily_attempt_used('EUR/USD',at,{},[sfp])

def test_persisted_marker_survives_restart_and_future_history_cannot_block_past():
    at=pd.Timestamp('2025-06-16 07:30Z');key=orb_daily_key('EUR/USD',at)
    h={key:{'timestamp':at.timestamp()}}
    assert orb_daily_attempt_used('EUR/USD',at,h,[])
    assert not orb_daily_attempt_used('EUR/USD',at-pd.Timedelta(minutes=1),h,[])

def test_engine_daily_cap_rejects_before_macro_or_notifications(monkeypatch):
    at=pd.Timestamp('2025-06-16 08:00Z');e=engine.BegonyaEngine.__new__(engine.BegonyaEngine)
    e.signal_history={orb_daily_key('EUR/USD',at):{'timestamp':at.timestamp()}}
    e.outcome_tracker=SimpleNamespace(active_trades=[],closed_trades=[])
    e._log_telemetry=Mock();e.macro_client=Mock();e.notifier=Mock()
    monkeypatch.setattr(engine,'datetime',Clock(at).datetime_type())
    s=dict(symbol='EUR/USD',strategy='ORB_SESSION_BREAKOUT',direction='SHORT',grade='AAA',htf_trend='BEARISH',entry=1.,stop_loss=1.01,tp1=.988,tp2=.98,entry_deadline_utc='2025-06-16 11:00Z')
    e._process_candidate(None,s)
    assert e._log_telemetry.call_args.args[0]=='ORB_DAILY_ATTEMPT_LIMIT'
    e.macro_client.evaluate_gate.assert_not_called()
    e.notifier.send_notification.assert_not_called()

def test_pending_limit_expires_at_cutoff_but_filled_position_still_tracks(monkeypatch):
    from sfp_orb_engine import outcome_tracker as tracker
    clock=Clock('2025-01-15 11:58Z')
    monkeypatch.setattr(tracker,'datetime',clock.datetime_type())
    monkeypatch.setattr(tracker.OutcomeTracker,'_load_json',lambda *a:[])
    monkeypatch.setattr(tracker.OutcomeTracker,'_save_json',lambda *a:None)
    monkeypatch.setattr(tracker.OutcomeTracker,'_notify_lifecycle',lambda *a:None)
    t=tracker.OutcomeTracker(notifier=Mock())
    s=dict(symbol='EUR/USD',strategy='ORB_SESSION_BREAKOUT',direction='LONG',entry=1.,stop_loss=.99,tp1=1.012,tp2=1.02,entry_deadline_utc='2025-01-15 12:00Z')
    t.register_trade(s)
    t.active_trades[0]['last_processed_bar']='2025-01-15 11:58Z'
    clock.current=pd.Timestamp('2025-01-15 12:00Z').to_pydatetime()
    t.check_trade_progress('EUR/USD',dict(datetime='2025-01-15 11:59Z',open=1.,high=1.001,low=.999,close=1.))
    assert t.closed_trades[0]['timeout_reason']=='SESSION_ENTRY_CUTOFF'
    assert t.closed_trades[0]['net_r']==0 and not t.closed_trades[0].get('filled_at')
    t.register_trade(s)
    t.active_trades[0].update(status='OPEN',last_processed_bar='2025-01-15 11:59Z')
    clock.current=pd.Timestamp('2025-01-15 12:01Z').to_pydatetime()
    t.check_trade_progress('EUR/USD',dict(datetime='2025-01-15 12:00Z',open=1.005,high=1.03,low=1.001,close=1.02))
    assert t.closed_trades[-1]['close_reason']=='TP2_HIT'

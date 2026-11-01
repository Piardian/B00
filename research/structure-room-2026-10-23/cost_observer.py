"""Read-only quote/cost diagnostic. Never places orders or changes a gate.

Cost budget is a diagnostic estimate, NOT an additional replay debit: bid/ask
replay already includes spread in executable prices. R is initial quote-price risk.
"""
import math
import pandas as pd


def observe(signal, bid, ask, quote_at, observed_at, commission_usd=4., exit_slip_pips=.2):
    symbol=signal['symbol'].replace('/','')
    if not (symbol.endswith('USD') or symbol.startswith('USD')):raise ValueError('USD crosses only')
    if any(not math.isfinite(v) or v<=0 for v in (bid,ask)):raise ValueError('Invalid quotes')
    if ask<bid:raise ValueError('Crossed quotes')
    if any(not math.isfinite(v) or v<0 for v in (commission_usd,exit_slip_pips)):raise ValueError('Invalid costs')
    age=(pd.Timestamp(observed_at)-pd.Timestamp(quote_at)).total_seconds()
    if age<0 or age>5:return dict(status='UNPRICED',reason='FUTURE_OR_STALE_QUOTE',quote_age_seconds=age)
    entry=float(signal['entry']);stop=float(signal['stop_loss']);risk=abs(entry-stop)
    if risk<=0:raise ValueError('Positive structural stop distance required')
    sign=1 if signal['direction']=='LONG' else -1
    if signal['direction'] not in {'LONG','SHORT'} or sign*(entry-stop)<=0:raise ValueError('Invalid stop direction')
    pip=.01 if symbol.endswith('JPY') else .0001
    commission=commission_usd*(entry if symbol.startswith('USD') else 1)/100000/risk
    budget=(ask-bid+exit_slip_pips*pip)/risk+commission
    gross_target=.5*sign*(signal['tp1']-entry)/risk+.5*sign*(signal['tp2']-entry)/risk
    return dict(status='OBSERVED_ONLY',quote_age_seconds=age,spread_pips=(ask-bid)/pip,
      stop_pips=risk/pip,spread_r=(ask-bid)/risk,commission_budget_r=commission,
      total_cost_budget_r=budget,weighted_full_target_gross_r=gross_target,
      full_target_less_cost_budget_r=gross_target-budget,
      binary_full_win_full_loss_breakeven_winrate=(1+budget)/(1+gross_target),
      caution='Binary benchmark only; partial exits, reaction exits, gaps and trailing alter required win rate. Not an entry approval.')

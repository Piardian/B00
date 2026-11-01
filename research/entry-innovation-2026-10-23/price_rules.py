"""Research-only target arithmetic; does not create entries or place orders."""
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR


def normalize_targets(signal, price_step, min_tp1='1.2', min_tp2='2.0'):
    step = Decimal(str(price_step))
    entry = Decimal(str(signal['entry']))
    stop = Decimal(str(signal['stop_loss']))
    risk = abs(entry-stop)
    if step <= 0 or risk <= 0:
        raise ValueError('Positive verified price step and risk required')
    if signal['direction'] not in {'LONG', 'SHORT'}:
        raise ValueError('Invalid direction')
    long = signal['direction'] == 'LONG'
    if not (stop < entry if long else stop > entry):
        raise ValueError('Stop must lie beyond entry in the loss direction')
    revised = dict(signal)
    for name, minimum in [('tp1', min_tp1), ('tp2', min_tp2)]:
        required = entry + (1 if long else -1)*risk*Decimal(minimum)
        prior = Decimal(str(signal[name]))
        desired = max(prior, required) if long else min(prior, required)
        rounding = ROUND_CEILING if long else ROUND_FLOOR
        revised[name] = float((desired/step).to_integral_value(rounding=rounding)*step)
    if not (revised['tp1'] < revised['tp2'] if long else revised['tp2'] < revised['tp1']):
        revised['tp2'] = float(Decimal(str(revised['tp1'])) + (step if long else -step))
    return revised

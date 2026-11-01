"""Causal sweep -> structure break -> iFVG setup confirmation."""
from .entry_mechanics import (
    detect_structural_breaker_long, detect_structural_breaker_short,
    detect_ifvg_long, detect_ifvg_short,
)


def confirm_structure(direction, j, i, highs, lows, opens, closes, atr,
                      require_breaker=True, use_ifvg=True):
    breaker = (detect_structural_breaker_long if direction == "LONG" else detect_structural_breaker_short)(
        j, i, highs, lows, opens, closes)
    if require_breaker and not breaker:
        return None
    zone = (detect_ifvg_long if direction == "LONG" else detect_ifvg_short)(i, highs, lows, closes, atr) if use_ifvg else None
    if use_ifvg and zone is None:
        return None
    return {"breaker_confirmed": breaker, "ifvg_confirmed": zone is not None, "zone": zone}

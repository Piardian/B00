"""
🌺 Begonya 00 - Kurumsal SMC & SFP İcraat ve Entry Mekaniği Modülü
Model A: %50 Consequent Encroachment (Equilibrium / Midpoint Entry)
Dinamik Stop Tamponu, Slice-Through & Momentum İptal Kalkanı ve Limit Durum Makinesi
"""

import math
from typing import Dict, Any, Optional, Tuple


def calculate_ce_entry(
    direction: str,
    peak_or_valley: Optional[float] = None,
    trigger_price: Optional[float] = None,
    close_price: Optional[float] = None,
    fvg_range: Optional[Tuple[float, float]] = None,
    atr: float = 0.0,
    sl_buffer_atr: float = 0.15,
    entry_model: str = "midpoint",
    orb_level: Optional[float] = None,
    tp1_r: float = 1.0,
    tp2_r: float = 3.0,
    **kwargs
) -> Dict[str, Any]:
    """
    SFP, FVG veya ORB kurulumları için matematiksel giriş, stop ve hedef seviyelerini belirler.
    """
    direction = direction.upper()
    model = (entry_model or "midpoint").lower()

    # Parametre takma adları (alias) çözümleme
    if close_price is None:
        close_price = float(kwargs.get("curr_close", 0.0))
    if peak_or_valley is None:
        peak_or_valley = float(kwargs.get("sweep_extreme", 0.0))
    if trigger_price is None:
        trigger_price = float(kwargs.get("mss_trigger", 0.0))
    if fvg_range is None and kwargs.get("has_fvg"):
        f_top = kwargs.get("fvg_top")
        f_bot = kwargs.get("fvg_bottom")
        if f_top is not None and f_bot is not None:
            fvg_range = (float(f_top), float(f_bot))

    if model == "midpoint":
        if direction == "SHORT":
            # 1. FVG Kontrolü: Yalnızca güncel bar kapanışına makul mesafedeyse kullanılır!
            # Fiyat FVG'yi delip saatler önce geçmişse asla eski FVG giriş seviyesi olarak kullanılamaz!
            is_fvg_valid_and_near = False
            if fvg_range is not None and len(fvg_range) == 2 and fvg_range[0] > fvg_range[1]:
                fvg_top, fvg_bottom = fvg_range
                cand_entry = (fvg_top + fvg_bottom) / 2.0
                max_dev = (atr * 0.8) if atr > 0 else (close_price * 0.0025)
                # FVG orta noktası güncel fiyata yakınsa ve güncel fiyat FVG'nin çok altında değilse
                if abs(cand_entry - close_price) <= max_dev and close_price <= fvg_top:
                    is_fvg_valid_and_near = True
                    entry_price = cand_entry
                    zone_high = max(fvg_top, peak_or_valley)
                    zone_low = min(fvg_bottom, close_price)
                    entry_source = "FVG_50_CE"

            if not is_fvg_valid_and_near:
                if orb_level is not None:
                    entry_price = (orb_level + close_price) / 2.0
                    zone_high = max(orb_level, close_price)
                    zone_low = min(orb_level, close_price)
                    entry_source = "ORB_RETEST_MIDPOINT"
                else:
                    # SFP Süpürme fitili orta noktası: (Tepe + Kırılan Seviye veya Kapanış) / 2
                    ref_low = min(trigger_price, close_price)
                    entry_price = (peak_or_valley + ref_low) / 2.0
                    zone_high = peak_or_valley
                    zone_low = ref_low
                    entry_source = "SWEEP_WICK_50_CE"

            # Dinamik Stop Tamponu: Pariteye özel kalibre edilmiş ATR tamponu
            zone_width = abs(zone_high - entry_price)
            dyn_buffer = (atr * sl_buffer_atr) if atr > 0 else (entry_price * 0.0015)
            dyn_buffer = max(dyn_buffer, zone_width * 0.15, (atr * 0.10) if atr > 0 else (entry_price * 0.0005))

            stop_loss = max(peak_or_valley, entry_price) + dyn_buffer
            risk_dist = max(stop_loss - entry_price, (atr * 0.20) if atr > 0 else (entry_price * 0.0010))
            tp1 = entry_price - (risk_dist * tp1_r)
            tp2 = entry_price - (risk_dist * tp2_r)

            # Hedef & Giriş Mantık Kalkanı (Sanity Guard):
            # SHORT pozisyonda hedefler (TP1/TP2) kesinlikle güncel fiyatın ALTINDA olmalıdır!
            if tp1 >= close_price or tp2 >= close_price or entry_price < close_price:
                ref_low = min(trigger_price, close_price)
                entry_price = (peak_or_valley + ref_low) / 2.0
                stop_loss = max(peak_or_valley, entry_price) + dyn_buffer
                risk_dist = max(stop_loss - entry_price, (atr * 0.20) if atr > 0 else (entry_price * 0.0010))
                tp1 = entry_price - (risk_dist * tp1_r)
                tp2 = entry_price - (risk_dist * tp2_r)
                entry_source = "SWEEP_WICK_50_CE_FALLBACK"

        else:  # LONG
            is_fvg_valid_and_near = False
            if fvg_range is not None and len(fvg_range) == 2 and fvg_range[1] > fvg_range[0]:
                fvg_bottom, fvg_top = fvg_range
                cand_entry = (fvg_top + fvg_bottom) / 2.0
                max_dev = (atr * 0.8) if atr > 0 else (close_price * 0.0025)
                if abs(cand_entry - close_price) <= max_dev and close_price >= fvg_bottom:
                    is_fvg_valid_and_near = True
                    entry_price = cand_entry
                    zone_high = max(fvg_top, close_price)
                    zone_low = min(fvg_bottom, peak_or_valley)
                    entry_source = "FVG_50_CE"

            if not is_fvg_valid_and_near:
                if orb_level is not None:
                    entry_price = (orb_level + close_price) / 2.0
                    zone_high = max(orb_level, close_price)
                    zone_low = min(orb_level, close_price)
                    entry_source = "ORB_RETEST_MIDPOINT"
                else:
                    # SFP Süpürme fitili orta noktası: (Dip + Kırılan Seviye veya Kapanış) / 2
                    ref_high = max(trigger_price, close_price)
                    entry_price = (peak_or_valley + ref_high) / 2.0
                    zone_high = ref_high
                    zone_low = peak_or_valley
                    entry_source = "SWEEP_WICK_50_CE"

            zone_width = abs(entry_price - zone_low)
            dyn_buffer = (atr * sl_buffer_atr) if atr > 0 else (entry_price * 0.0015)
            dyn_buffer = max(dyn_buffer, zone_width * 0.15, (atr * 0.10) if atr > 0 else (entry_price * 0.0005))

            stop_loss = min(peak_or_valley, entry_price) - dyn_buffer
            risk_dist = max(entry_price - stop_loss, (atr * 0.20) if atr > 0 else (entry_price * 0.0010))
            tp1 = entry_price + (risk_dist * tp1_r)
            tp2 = entry_price + (risk_dist * tp2_r)

            # Hedef & Giriş Mantık Kalkanı (Sanity Guard):
            # LONG pozisyonda hedefler (TP1/TP2) kesinlikle güncel fiyatın ÜSTÜNDE olmalıdır!
            if tp1 <= close_price or tp2 <= close_price or entry_price > close_price:
                ref_high = max(trigger_price, close_price)
                entry_price = (peak_or_valley + ref_high) / 2.0
                stop_loss = min(peak_or_valley, entry_price) - dyn_buffer
                risk_dist = max(entry_price - stop_loss, (atr * 0.20) if atr > 0 else (entry_price * 0.0010))
                tp1 = entry_price + (risk_dist * tp1_r)
                tp2 = entry_price + (risk_dist * tp2_r)
                entry_source = "SWEEP_WICK_50_CE_FALLBACK"

        return {
            "entry_price": round(entry_price, 6),
            "stop_loss": round(stop_loss, 6),
            "risk_distance": round(risk_dist, 6),
            "risk_dist": round(risk_dist, 6),
            "tp1": round(tp1, 6),
            "tp2": round(tp2, 6),
            "zone_low": round(zone_low, 6),
            "zone_high": round(zone_high, 6),
            "is_limit": True,
            "entry_model": "MIDPOINT",
            "entry_source": entry_source,
            "dynamic_buffer": round(dyn_buffer, 6),
        }

    else:
        # Klasik Kapanış Girişi (Model 'close')
        entry_price = close_price
        if direction == "SHORT":
            stop_loss = peak_or_valley + ((atr * sl_buffer_atr) if atr > 0 else (entry_price * 0.0015))
            risk_dist = max(stop_loss - entry_price, (atr * 0.20) if atr > 0 else (entry_price * 0.0008))
            tp1 = entry_price - (risk_dist * tp1_r)
            tp2 = entry_price - (risk_dist * tp2_r)
            zone_high = peak_or_valley
            zone_low = close_price
        else:
            stop_loss = peak_or_valley - ((atr * sl_buffer_atr) if atr > 0 else (entry_price * 0.0015))
            risk_dist = max(entry_price - stop_loss, (atr * 0.20) if atr > 0 else (entry_price * 0.0008))
            tp1 = entry_price + (risk_dist * tp1_r)
            tp2 = entry_price + (risk_dist * tp2_r)
            zone_high = close_price
            zone_low = peak_or_valley

        return {
            "entry_price": round(entry_price, 6),
            "stop_loss": round(stop_loss, 6),
            "risk_distance": round(risk_dist, 6),
            "risk_dist": round(risk_dist, 6),
            "tp1": round(tp1, 6),
            "tp2": round(tp2, 6),
            "zone_low": round(zone_low, 6),
            "zone_high": round(zone_high, 6),
            "is_limit": False,
            "entry_model": "CLOSE",
            "entry_source": "MARKET_CLOSE",
            "dynamic_buffer": round(abs(stop_loss - peak_or_valley), 6),
        }


def is_slice_through_candle(
    direction: str,
    open_p: float,
    high_p: float,
    low_p: float,
    close_p: float,
    zone_low: float,
    zone_high: float,
) -> bool:
    """
    Bölgeye yaklaşan retest mumunun yüksek momentumla bölgeyi tepkisiz delip geçip geçmediğini denetler.
    Eğer mum devasa gövdeyle bölgeyi kırıp geçerse ve tepki fitili bırakmazsa emri korumak için True döner.
    """
    candle_range = max(high_p - low_p, 1e-8)
    body = abs(close_p - open_p)
    body_ratio = body / candle_range

    if direction.upper() == "LONG":
        # Long için gelen mum düşüş mumu (Bearish) olmalı
        if close_p < open_p and body_ratio >= 0.60 and close_p < zone_low:
            lower_wick = max(close_p - low_p, 0.0) / candle_range
            # Alt fitil zayıfsa (alıcı tepkisi / absorpsiyon yoksa)
            if lower_wick <= 0.22:
                return True

    elif direction.upper() == "SHORT":
        # Short için gelen mum yükseliş mumu (Bullish) olmalı
        if close_p > open_p and body_ratio >= 0.60 and close_p > zone_high:
            upper_wick = max(high_p - close_p, 0.0) / candle_range
            # Üst fitil zayıfsa (satıcı tepkisi yoksa)
            if upper_wick <= 0.22:
                return True

    return False


def evaluate_entry_candle_reaction(
    direction: str,
    open_p: float,
    high_p: float,
    low_p: float,
    close_p: float,
    zone_low: float,
    zone_high: float,
) -> bool:
    """
    Giriş mumunun bölge içinde absorpsiyon / tepki fitili üretip üretmediğini doğrular.
    """
    candle_range = max(high_p - low_p, 1e-8)

    if direction.upper() == "LONG":
        lower_wick = (min(open_p, close_p) - low_p) / candle_range
        # Güçlü alt fitil veya yeşil kapanış
        return lower_wick >= 0.30 or close_p > open_p
    else:
        upper_wick = (high_p - max(open_p, close_p)) / candle_range
        # Güçlü üst fitil veya kırmızı kapanış
        return upper_wick >= 0.30 or close_p < open_p


def detect_ifvg_short(
    i: int,
    highs,
    lows,
    closes,
    c_atr: float,
    lookback: int = 6,
    min_atr_mult: float = 0.08,
) -> Optional[Tuple[float, float]]:
    """
    Bearish Inversion FVG (iFVG) Tespiti:
    Son `lookback` (en fazla 6 bar) içinde oluşmuş yükseliş yönlü (Bullish) bir FVG'nin
    bar `i` kapanışı ile aşağı yönlü kırılıp (invert edilip) dirence dönüşmesini tespit eder.
    Dönüş: (fvg_top, fvg_bottom) -> SHORT için fvg_top > fvg_bottom
    """
    curr_c = float(closes[i])
    for k in range(i - 1, max(2, i - lookback), -1):
        if lows[k] > highs[k - 2]:
            gap_size = float(lows[k] - highs[k - 2])
            if gap_size >= c_atr * min_atr_mult:
                fvg_top = float(lows[k])
                fvg_bot = float(highs[k - 2])
                if closes[i] < fvg_bot and closes[k] >= fvg_bot:
                    # Yalnızca güncel muma yakınsa (fiyat kopup gitmemişse) geçerlidir!
                    if abs((fvg_top + fvg_bot) / 2.0 - curr_c) <= c_atr * 1.0:
                        return (fvg_top, fvg_bot)
    return None


def detect_ifvg_long(
    i: int,
    highs,
    lows,
    closes,
    c_atr: float,
    lookback: int = 6,
    min_atr_mult: float = 0.08,
) -> Optional[Tuple[float, float]]:
    """
    Bullish Inversion FVG (iFVG) Tespiti:
    Son `lookback` (en fazla 6 bar) içinde oluşmuş düşüş yönlü (Bearish) bir FVG'nin
    bar `i` kapanışı ile yukarı yönlü kırılıp (invert edilip) desteğe dönüşmesini tespit eder.
    Dönüş: (fvg_bottom, fvg_top) -> LONG için fvg_bottom < fvg_top
    """
    curr_c = float(closes[i])
    for k in range(i - 1, max(2, i - lookback), -1):
        if highs[k] < lows[k - 2]:
            gap_size = float(lows[k - 2] - highs[k])
            if gap_size >= c_atr * min_atr_mult:
                fvg_bot = float(highs[k])
                fvg_top = float(lows[k - 2])
                if closes[i] > fvg_top and closes[k] <= fvg_top:
                    if abs((fvg_top + fvg_bot) / 2.0 - curr_c) <= c_atr * 1.0:
                        return (fvg_bot, fvg_top)
    return None


def detect_structural_breaker_short(
    j: int,
    i: int,
    highs,
    lows,
    opens,
    closes,
) -> bool:
    """
    Gerçek Yapısal Breaker Kırılımı (Short MSS):
    Sweep mumu (j) öncesindeki son 5 mum içindeki en son yükseliş mumunun (Bullish Order Block / Bearish Breaker)
    tabanının bar `i` tarafından gövdeyle aşağı kırılması.
    """
    for k in range(j - 1, max(2, j - 6), -1):
        if closes[k] > opens[k]:
            return bool(closes[i] < lows[k])
    return bool(closes[i] < min(lows[j], lows[j - 1]))


def detect_structural_breaker_long(
    j: int,
    i: int,
    highs,
    lows,
    opens,
    closes,
) -> bool:
    """
    Gerçek Yapısal Breaker Kırılımı (Long MSS):
    Sweep mumu (j) öncesindeki son 5 mum içindeki en son düşüş mumunun (Bearish Order Block / Bullish Breaker)
    tavanının bar `i` tarafından gövdeyle yukarı kırılması.
    """
    for k in range(j - 1, max(2, j - 6), -1):
        if closes[k] < opens[k]:
            return bool(closes[i] > highs[k])
    return bool(closes[i] > max(highs[j], highs[j - 1]))


class LimitExecutionSimulator:
    """
    Model A (%50 CE Limit) emirlerinin bar-bar simülasyonunu yöneten yardımcı durum makinesi.
    """
    def __init__(
        self,
        order_id: str,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        tp1: float,
        tp2: float,
        zone_low: float,
        zone_high: float,
        is_limit: bool = True,
        expiry_bars: int = 32,
        require_reaction: bool = True,
    ):
        self.order_id = order_id
        self.symbol = symbol
        self.direction = direction.upper()
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.tp1 = tp1
        self.tp2 = tp2
        self.zone_low = zone_low
        self.zone_high = zone_high
        self.is_limit = is_limit
        self.expiry_bars = expiry_bars
        self.require_reaction = require_reaction

        self.risk_distance = abs(entry_price - stop_loss)
        self.status = "PENDING" if is_limit else "OPEN"
        self.bars_waiting = 0
        self.bars_held = 0
        self.current_sl = stop_loss
        self.be_armed = False
        self.mfe_r = 0.0
        self.mae_r = 0.0
        self.closed_reason = ""
        self.r_result = 0.0

    def process_bar(
        self,
        open_p: float,
        high_p: float,
        low_p: float,
        close_p: float,
        bar_time: str,
    ) -> str:
        """
        Her yeni bar kapandığında emir durumunu günceller.
        Dönen durum: 'PENDING', 'OPEN', 'TP1_HIT', 'CLOSED'
        """
        if self.status == "CLOSED":
            return self.status

        is_long = self.direction == "LONG"

        # 1. PENDING Durumundaki Limit Emrin Değerlendirilmesi
        if self.status == "PENDING":
            self.bars_waiting += 1
            if self.bars_waiting >= self.expiry_bars:
                self.status = "CLOSED"
                self.closed_reason = "EXPIRED"
                self.r_result = 0.0
                return self.status

            # Girişten önce Stop Loss delindi mi? (Geçersiz Kılınma)
            stop_hit_before = (low_p <= self.stop_loss) if is_long else (high_p >= self.stop_loss)
            reached_entry = (low_p <= self.entry_price and open_p >= self.stop_loss) if is_long else (high_p >= self.entry_price and open_p <= self.stop_loss)

            if stop_hit_before and not reached_entry:
                self.status = "CLOSED"
                self.closed_reason = "INVALIDATED_BEFORE_FILL"
                self.r_result = 0.0
                return self.status

            if reached_entry:
                # Slice-Through kontrolü (Reaksiyonsuz momentum delmesi)
                if self.require_reaction:
                    if is_slice_through_candle(self.direction, open_p, high_p, low_p, close_p, self.zone_low, self.zone_high):
                        self.status = "CLOSED"
                        self.closed_reason = "CANCELLED_SLICE_THROUGH"
                        self.r_result = 0.0
                        return self.status

                self.status = "OPEN"
                # Giriş mumunun kendisinde anında TP/SL kontrolü
                sl_on_entry = (low_p <= self.stop_loss) if is_long else (high_p >= self.stop_loss)
                tp_on_entry = (high_p >= self.tp2) if is_long else (low_p <= self.tp2)

                if sl_on_entry and tp_on_entry:
                    self.status = "CLOSED"
                    self.closed_reason = "STOP_LOSS"
                    self.r_result = -1.0
                    return self.status
                if tp_on_entry:
                    self.status = "CLOSED"
                    self.closed_reason = "TP2_HIT"
                    self.r_result = 2.0  # +2.0R Net
                    return self.status
                if sl_on_entry:
                    self.status = "CLOSED"
                    self.closed_reason = "STOP_LOSS"
                    self.r_result = -1.0
                    return self.status

                return self.status

        # 2. OPEN veya TP1_HIT Pozisyonunun Yönetimi
        if self.status in ["OPEN", "TP1_HIT"]:
            self.bars_held += 1

            fav = max(0.0, high_p - self.entry_price) if is_long else max(0.0, self.entry_price - low_p)
            adv = max(0.0, self.entry_price - low_p) if is_long else max(0.0, high_p - self.entry_price)

            curr_mfe = fav / max(self.risk_distance, 1e-8)
            curr_mae = adv / max(self.risk_distance, 1e-8)
            self.mfe_r = max(self.mfe_r, curr_mfe)
            self.mae_r = max(self.mae_r, curr_mae)

            # TP1 Kontrolü (1.0R): Vurulunca Stop BE'ye çekilir
            hits_tp1 = (high_p >= self.tp1) if is_long else (low_p <= self.tp1)
            if hits_tp1 and self.status == "OPEN":
                self.status = "TP1_HIT"
                self.current_sl = self.entry_price
                self.be_armed = True

            hits_tp2 = (high_p >= self.tp2) if is_long else (low_p <= self.tp2)
            hits_sl = (low_p <= self.current_sl) if is_long else (high_p >= self.current_sl)

            if hits_tp2 and hits_sl:
                # Muhafazakar: BE çekildiyse BE, değilse SL
                self.status = "CLOSED"
                if self.be_armed:
                    self.closed_reason = "BREAK_EVEN"
                    self.r_result = 0.5  # %50 TP1 (0.5R) + %50 BE (0.0R)
                else:
                    self.closed_reason = "STOP_LOSS"
                    self.r_result = -1.0
                return self.status

            if hits_tp2:
                self.status = "CLOSED"
                self.closed_reason = "TP2_HIT"
                self.r_result = 2.0  # %50 TP1 (0.5R) + %50 TP2 (1.5R) = 2.0R
                return self.status

            if hits_sl:
                self.status = "CLOSED"
                if self.status == "TP1_HIT" or self.be_armed:
                    self.closed_reason = "BREAK_EVEN"
                    self.r_result = 0.5
                else:
                    self.closed_reason = "STOP_LOSS"
                    self.r_result = -1.0
                return self.status

            if self.bars_held >= 192:  # 48 saat zaman aşımı
                self.status = "CLOSED"
                self.closed_reason = "TIME_EXIT"
                final_gain = (close_p - self.entry_price) if is_long else (self.entry_price - close_p)
                self.r_result = round(final_gain / max(self.risk_distance, 1e-8), 2)
                return self.status

        return self.status

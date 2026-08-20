"""
Range/mean-reversion-scoring.

Används ENDAST när market_structure() == "range" - annars är trend_engine
(technical/engine.py:s ordinarie viktade score) rätt modell.

Idé: i en trend vill man följa riktningen (trend_engine). I ett range vill
man göra motsatsen - köpa nära stöd, sälja nära motstånd - eftersom priset
historiskt studsat mellan samma nivåer istället för att bryta ut. Att
använda trend-scoret i ett range ger nästan alltid ~0 eftersom EMA/momentum-
komponenterna motverkar varandra (se förklaring i technical/engine.py).

VIKTIGT (samma princip som trend_engine): en enskild komponent (t.ex. bara
"nära stöd") får inte ensam trigga en trade - RSI-extremvärde och/eller en
avvisnings-wick krävs som bekräftelse innan scoret blir starkt.
"""
from __future__ import annotations
import pandas as pd

RANGE_WEIGHTS = {
    "position_in_range": 0.45,   # var i intervallet ligger priset - störst vikt
    "rsi_extreme": 0.30,         # bekräftar med faktisk över-/undersåld nivå
    "rejection_wick": 0.15,      # senaste candlen visar avvisning vid nivån
    "range_width": 0.10,         # bredare, mer "beprövat" range = mer pålitligt
}


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, x)))


def _position_score(close: float, support: float | None, resistance: float | None) -> float:
    if support is None or resistance is None or resistance <= support:
        return 0.0
    pos = (close - support) / (resistance - support)  # 0 = vid stöd, 1 = vid motstånd
    # Brantare lutning än i trend_engine.position_score, eftersom det här är
    # huvudsignalen i range-läge, inte bara en liten justering.
    return _clip((0.5 - pos) * 2.2)


def _rsi_extreme_score(rsi_val: float) -> float:
    # I range-läge bryr vi oss bara om faktiska extremvärden, inte 50-mittpunkten -
    # där finns ingen edge i ett sidledes intervall.
    if rsi_val <= 30:
        return _clip((30 - rsi_val) / 15 + 0.6)   # djupare översåld = starkare köpsignal
    if rsi_val >= 70:
        return _clip(-((rsi_val - 70) / 15 + 0.6))
    return 0.0


def _rejection_wick_score(last_candle: pd.Series, direction_hint: float) -> float:
    """Lång lower wick nära stöd = köp-avvisning. Lång upper wick nära motstånd = sälj-avvisning."""
    body = abs(last_candle["close"] - last_candle["open"])
    lower_wick = min(last_candle["close"], last_candle["open"]) - last_candle["low"]
    upper_wick = last_candle["high"] - max(last_candle["close"], last_candle["open"])
    # Om kroppen är ~0 (doji) räknas ändå wicken - använd ett litet golv för att undvika division/skala-problem
    min_body = max(body, 1e-9)
    if direction_hint > 0 and lower_wick > min_body * 1.5:
        return 0.6
    if direction_hint < 0 and upper_wick > min_body * 1.5:
        return -0.6
    return 0.0


def _range_width_score(support: float | None, resistance: float | None, atr: float) -> float:
    if support is None or resistance is None or not atr:
        return 0.0
    width_in_atr = (resistance - support) / atr
    # Ett för smalt range (< 2x ATR) är opålitligt/brus. För brett (> 6x utöver
    # golvet) är knappt ett range längre - då är det snarare två separata trender.
    if width_in_atr < 2:
        return 0.0
    return _clip(min((width_in_atr - 2) / 4, 1.0))


def range_score(df: pd.DataFrame, support: float | None, resistance: float | None,
                 rsi_val: float, atr: float) -> float:
    """
    Returnerar ett score -1..+1 för range-läge, med samma tolkning som
    trend_engine.technical_score: >0 = köpbias (nära stöd, bekräftat),
    <0 = säljbias (nära motstånd, bekräftat).
    """
    if df is None or df.empty:
        return 0.0

    last_candle = df.iloc[-1]
    close = float(last_candle["close"])

    pos_score = _position_score(close, support, resistance)
    rsi_score = _rsi_extreme_score(rsi_val)
    wick_score = _rejection_wick_score(last_candle, direction_hint=pos_score)
    width_score = _range_width_score(support, resistance, atr)

    return _clip(
        RANGE_WEIGHTS["position_in_range"] * pos_score
        + RANGE_WEIGHTS["rsi_extreme"] * rsi_score
        + RANGE_WEIGHTS["rejection_wick"] * wick_score
        + RANGE_WEIGHTS["range_width"] * width_score
    )

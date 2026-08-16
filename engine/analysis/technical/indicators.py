"""
Rena, deterministiska funktioner för tekniska indikatorer.
Ingen AI, ingen slump - allt är matematik på OHLCV-data.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))

    # avg_loss == 0 betyder oavbruten uppgång -> RSI ska vara 100 (inte NaN/neutral),
    # såvida inte avg_gain också är 0 (helt platt serie) -> då är RSI neutralt 50.
    result = result.where(avg_loss != 0, np.where(avg_gain > 0, 100.0, 50.0))
    return pd.Series(result, index=series.index).fillna(50)  # neutral bara vid otillräcklig data (NaN i starten)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def realized_volatility(series: pd.Series, period: int = 20) -> pd.Series:
    """Annualiserad volatilitet baserat på log returns (grov proxy, funkar oavsett timeframe)."""
    log_ret = np.log(series / series.shift(1))
    return log_ret.rolling(period).std()


def find_swing_points(df: pd.DataFrame, lookback: int = 5) -> tuple[pd.Series, pd.Series]:
    """
    Identifierar swing highs/lows: en punkt är en swing high om den är högst
    bland `lookback` candles på vardera sida (motsvarande för swing low).
    Returnerar boolean-serier.
    """
    highs = df["high"]
    lows = df["low"]
    is_swing_high = pd.Series(False, index=df.index)
    is_swing_low = pd.Series(False, index=df.index)

    for i in range(lookback, len(df) - lookback):
        window_high = highs.iloc[i - lookback: i + lookback + 1]
        window_low = lows.iloc[i - lookback: i + lookback + 1]
        if highs.iloc[i] == window_high.max():
            is_swing_high.iloc[i] = True
        if lows.iloc[i] == window_low.min():
            is_swing_low.iloc[i] = True

    return is_swing_high, is_swing_low


def nearest_support_resistance(df: pd.DataFrame, current_price: float, lookback: int = 5):
    """
    Hittar närmaste support (under nuvarande pris) och resistance (över).
    Baserat på senaste swing lows/highs.
    """
    is_high, is_low = find_swing_points(df, lookback=lookback)
    swing_highs = df.loc[is_high, "high"]
    swing_lows = df.loc[is_low, "low"]

    resistances_above = swing_highs[swing_highs > current_price]
    supports_below = swing_lows[swing_lows < current_price]

    resistance = resistances_above.min() if not resistances_above.empty else None
    support = supports_below.max() if not supports_below.empty else None
    return support, resistance


def market_structure(df: pd.DataFrame, lookback: int = 5) -> str:
    """
    Grov klassificering av marknadsstruktur baserat på de senaste swing-punkterna:
    - 'HH_HL' (bullish struktur: högre toppar, högre bottnar)
    - 'LH_LL' (bearish struktur: lägre toppar, lägre bottnar)
    - 'range' (osäker/sidledes struktur)
    """
    is_high, is_low = find_swing_points(df, lookback=lookback)
    highs = df.loc[is_high, "high"].tail(2)
    lows = df.loc[is_low, "low"].tail(2)

    if len(highs) < 2 or len(lows) < 2:
        return "range"

    higher_high = highs.iloc[-1] > highs.iloc[-2]
    higher_low = lows.iloc[-1] > lows.iloc[-2]
    lower_high = highs.iloc[-1] < highs.iloc[-2]
    lower_low = lows.iloc[-1] < lows.iloc[-2]

    if higher_high and higher_low:
        return "HH_HL"
    if lower_high and lower_low:
        return "LH_LL"
    return "range"


def detect_breakout(df: pd.DataFrame, lookback: int = 20) -> bool:
    """True om senaste close bryter över/under det senaste `lookback`-fönstrets high/low."""
    if len(df) < lookback + 1:
        return False
    recent = df.iloc[-(lookback + 1):-1]
    last_close = df["close"].iloc[-1]
    return bool(last_close > recent["high"].max() or last_close < recent["low"].min())

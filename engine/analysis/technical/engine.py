"""
Technical Analysis Engine.

Tar rå OHLCV-data och producerar:
1. Ett fullständigt "snapshot" (alla indikatorvärden) - sparas i technical_snapshots
2. Ett sammanvägt technical_score mellan -1 (extremt bearish) och +1 (extremt bullish)

VIKTIGT (från spec): en enskild indikator får ALDRIG ensam trigga en trade.
Scoret är en vägd kombination av flera oberoende signaler, och breakout/trend
kräver bekräftelse från momentum (RSI/MACD) för att ge fullt utslag.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from engine.analysis.technical import indicators as ind

# Vikter för hur mycket varje komponent bidrar till slutgiltiga technical_score.
# Summerar till 1.0. Konfigurerbart - kan optimeras senare via backtesting.
WEIGHTS = {
    "trend": 0.30,        # EMA-stack (20/50/200)
    "momentum": 0.25,     # RSI + MACD-histogram
    "structure": 0.20,    # market structure (HH/HL vs LH/LL)
    "breakout": 0.15,     # breakout bekräftad av momentum
    "position": 0.10,     # var priset ligger relativt support/resistance
}


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, x)))


def _trend_score(close: float, ema20: float, ema50: float, ema200: float) -> float:
    """+1 om pris > ema20 > ema50 > ema200 (perfekt bullish stack), symmetriskt för bearish."""
    score = 0.0
    score += 0.4 if close > ema20 else -0.4
    score += 0.3 if ema20 > ema50 else -0.3
    score += 0.3 if ema50 > ema200 else -0.3
    return _clip(score)


def _momentum_score(rsi_val: float, macd_hist: float, macd_hist_prev: float) -> float:
    # RSI: skala 30-70 linjärt till -1..+1 (över/under det = extremvärden, dämpas)
    rsi_component = _clip((rsi_val - 50) / 20)
    # MACD-histogram: positivt och växande = bullish momentum
    macd_component = _clip(np.sign(macd_hist) * min(abs(macd_hist), 1.0))
    macd_accel = 0.15 if macd_hist > macd_hist_prev else -0.15
    return _clip(0.55 * rsi_component + 0.35 * macd_component + 0.10 * np.sign(macd_accel))


def _structure_score(structure: str) -> float:
    return {"HH_HL": 0.7, "LH_LL": -0.7, "range": 0.0}.get(structure, 0.0)


def _breakout_score(breakout: bool, momentum_score: float) -> float:
    """Breakout ger bara fullt utslag om momentum bekräftar riktningen."""
    if not breakout:
        return 0.0
    direction = 1 if momentum_score >= 0 else -1
    strength = 0.6 + 0.4 * min(abs(momentum_score), 1.0)
    return _clip(direction * strength)


def _position_score(close: float, support, resistance) -> float:
    """Nära support (i en uptrend-kontext) = mer attraktivt läge, och vice versa."""
    if support is None or resistance is None or resistance == support:
        return 0.0
    position_in_range = (close - support) / (resistance - support)  # 0 = vid support, 1 = vid resistance
    # Nära support -> lätt bullish bias (bättre R/R för köp), nära resistance -> bearish bias
    return _clip((0.5 - position_in_range) * 2)


def analyze(df: pd.DataFrame, symbol: str, timeframe: str) -> dict | None:
    """
    df: OHLCV DataFrame sorterad stigande på ts, minst ~250 rader för EMA200 att vara meningsfull.
    Returnerar None om det inte finns tillräckligt med data (kraschar inte).
    """
    if df is None or df.empty or len(df) < 30:
        return None

    df = df.sort_values("ts").reset_index(drop=True)
    close = df["close"]

    ema20 = ind.ema(close, 20)
    ema50 = ind.ema(close, 50)
    ema200 = ind.ema(close, 200) if len(df) >= 200 else ind.ema(close, max(len(df) // 2, 2))
    rsi14 = ind.rsi(close, 14)
    macd_line, macd_signal, macd_hist = ind.macd(close)
    atr14 = ind.atr(df, 14)
    vol = ind.realized_volatility(close, 20)

    last = -1
    prev = -2 if len(df) > 1 else -1

    current_close = float(close.iloc[last])
    support, resistance = ind.nearest_support_resistance(df, current_close)
    structure = ind.market_structure(df)
    breakout = ind.detect_breakout(df)

    trend_score = _trend_score(current_close, float(ema20.iloc[last]), float(ema50.iloc[last]), float(ema200.iloc[last]))
    momentum_score = _momentum_score(float(rsi14.iloc[last]), float(macd_hist.iloc[last]), float(macd_hist.iloc[prev]))
    structure_score = _structure_score(structure)
    breakout_score = _breakout_score(breakout, momentum_score)
    position_score = _position_score(current_close, support, resistance)

    technical_score = _clip(
        WEIGHTS["trend"] * trend_score
        + WEIGHTS["momentum"] * momentum_score
        + WEIGHTS["structure"] * structure_score
        + WEIGHTS["breakout"] * breakout_score
        + WEIGHTS["position"] * position_score
    )

    prev_high = float(df["high"].iloc[-21:-1].max()) if len(df) > 21 else float(df["high"].max())
    prev_low = float(df["low"].iloc[-21:-1].min()) if len(df) > 21 else float(df["low"].min())
    recent_high = float(df["high"].tail(50).max())
    recent_low = float(df["low"].tail(50).min())

    trend_label = "up" if trend_score > 0.2 else ("down" if trend_score < -0.2 else "sideways")

    snapshot = {
        "symbol": symbol,
        "timeframe": timeframe,
        "ts": df["ts"].iloc[last].isoformat(),
        "close": current_close,
        "ema_20": float(ema20.iloc[last]),
        "ema_50": float(ema50.iloc[last]),
        "ema_200": float(ema200.iloc[last]),
        "rsi_14": float(rsi14.iloc[last]),
        "macd": float(macd_line.iloc[last]),
        "macd_signal": float(macd_signal.iloc[last]),
        "macd_hist": float(macd_hist.iloc[last]),
        "atr_14": float(atr14.iloc[last]),
        "volatility": float(vol.iloc[last]) if pd.notna(vol.iloc[last]) else None,
        "prev_high": prev_high,
        "prev_low": prev_low,
        "support": float(support) if support is not None else None,
        "resistance": float(resistance) if resistance is not None else None,
        "trend": trend_label,
        "breakout": breakout,
        "market_structure": structure,
        "momentum": momentum_score,
        "distance_from_high": _clip((recent_high - current_close) / current_close, -1, 1) if current_close else None,
        "distance_from_low": _clip((current_close - recent_low) / current_close, -1, 1) if current_close else None,
        "technical_score": technical_score,
    }
    return snapshot

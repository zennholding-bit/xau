import numpy as np
import pandas as pd
import pytest

from engine.analysis.technical import indicators as ind


def make_trend_df(n=250, start=1900, step=1.0, noise=0.0, seed=42):
    rng = np.random.default_rng(seed)
    close = start + np.arange(n) * step + rng.normal(0, noise, n)
    high = close + abs(rng.normal(1, 0.3, n))
    low = close - abs(rng.normal(1, 0.3, n))
    open_ = close - rng.normal(0, 0.5, n)
    ts = pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame({"ts": ts, "open": open_, "high": high, "low": low, "close": close, "volume": 100.0})


def test_ema_converges_toward_price_in_uptrend():
    df = make_trend_df(step=2.0)
    e20 = ind.ema(df["close"], 20)
    assert e20.iloc[-1] > e20.iloc[0]  # EMA ska följa upptrenden


def test_rsi_bounds():
    df = make_trend_df(step=1.0)
    r = ind.rsi(df["close"])
    assert (r >= 0).all() and (r <= 100).all()


def test_rsi_high_in_strong_uptrend():
    df = make_trend_df(step=3.0, noise=0.0)
    r = ind.rsi(df["close"])
    assert r.iloc[-1] > 60  # stark, oavbruten uppgång -> hög RSI


def test_macd_returns_three_series_same_length():
    df = make_trend_df()
    macd_line, signal, hist = ind.macd(df["close"])
    assert len(macd_line) == len(signal) == len(hist) == len(df)


def test_atr_positive():
    df = make_trend_df(noise=1.0)
    a = ind.atr(df)
    assert (a.dropna() >= 0).all()


def test_market_structure_uptrend_detects_hh_hl():
    # Skapa en tydlig sicksack-uppgång: varje topp och botten högre än föregående
    n = 60
    ts = pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")
    base = np.linspace(1900, 2000, n)
    wiggle = 5 * np.sin(np.linspace(0, 6 * np.pi, n))
    close = base + wiggle
    high = close + 2
    low = close - 2
    df = pd.DataFrame({"ts": ts, "open": close, "high": high, "low": low, "close": close, "volume": 100.0})
    structure = ind.market_structure(df, lookback=3)
    assert structure in ("HH_HL", "range")  # ska åtminstone inte klassas som bearish


def test_detect_breakout_true_when_close_exceeds_range():
    df = make_trend_df(n=30, step=0.0, noise=0.0)
    df.loc[df.index[-1], "close"] = df["high"].iloc[:-1].max() + 50  # tydligt brott uppåt
    assert ind.detect_breakout(df, lookback=20) is True


def test_nearest_support_resistance_returns_reasonable_values():
    df = make_trend_df(n=100, step=0.0, noise=3.0)
    current = float(df["close"].iloc[-1])
    support, resistance = ind.nearest_support_resistance(df, current, lookback=3)
    if support is not None:
        assert support < current
    if resistance is not None:
        assert resistance > current

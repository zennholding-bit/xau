"""
MarketDataProvider - gratis implementation via yfinance.

Designad som ett interface (duck-typed) så den senare kan bytas mot en
premiumleverantör (t.ex. Twelve Data, Polygon, OANDA) utan att signalmotorn
behöver ändras. Alla providers ska returnera samma DataFrame-format:

    columns: ts (UTC datetime), open, high, low, close, volume

yfinance historik-begränsningar (viktigt att känna till):
- 1m data: max ~7 dagar tillbaka
- 5m/15m data: max ~60 dagar tillbaka
- 1h data: max ~730 dagar tillbaka
- 1d data: obegränsat

Systemet hanterar detta genom att bara hämta det som är tillgängligt och
markera perioder med lägre quality_score om data saknas, istället för att krascha.
"""
from __future__ import annotations
import logging
import pandas as pd
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential

from engine.config.settings import YFINANCE_SYMBOLS

logger = logging.getLogger(__name__)

# yfinance-intervall + max lookback-period som funkar i praktiken
_INTERVAL_CONFIG = {
    "5m":  {"yf_interval": "5m",  "period": "60d"},
    "15m": {"yf_interval": "15m", "period": "60d"},
    "1h":  {"yf_interval": "60m", "period": "730d"},
    "1d":  {"yf_interval": "1d",  "period": "max"},
}


class MarketDataUnavailableError(Exception):
    pass


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _download(ticker: str, yf_interval: str, period: str) -> pd.DataFrame:
    df = yf.download(
        tickers=ticker,
        interval=yf_interval,
        period=period,
        progress=False,
        auto_adjust=False,
        multi_level_index=False,
    )
    if df is None or df.empty:
        raise MarketDataUnavailableError(f"Tom respons för {ticker} ({yf_interval}, {period})")
    return df


def fetch_ohlcv(symbol: str, timeframe: str) -> pd.DataFrame:
    """
    Hämtar OHLCV för en given symbol/timeframe.
    Returnerar tom DataFrame (inte exception) om data inte kan hämtas,
    så anroparen kan logga och fortsätta utan att krascha hela pipelinen.
    """
    ticker = YFINANCE_SYMBOLS.get(symbol)
    if ticker is None:
        logger.warning("Okänd symbol %s - hoppar över", symbol)
        return pd.DataFrame()

    # 4h finns inte nativt i yfinance -> hämta 1h och resampla
    base_tf = "1h" if timeframe == "4h" else timeframe
    cfg = _INTERVAL_CONFIG.get(base_tf)
    if cfg is None:
        logger.warning("Timeframe %s stöds inte av yfinance-providern - hoppar över", timeframe)
        return pd.DataFrame()

    try:
        df = _download(ticker, cfg["yf_interval"], cfg["period"])
    except Exception as e:
        logger.error("Kunde inte hämta %s (%s): %s", symbol, timeframe, e)
        return pd.DataFrame()

    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume",
    })
    df.index.name = "ts"
    df = df.reset_index()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df[["ts", "open", "high", "low", "close", "volume"]].dropna(subset=["open", "high", "low", "close"])

    if timeframe == "4h":
        df = _resample_to_4h(df)

    return df


def _resample_to_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    if df_1h.empty:
        return df_1h
    d = df_1h.set_index("ts")
    agg = d.resample("4h").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
    }).dropna(subset=["open", "high", "low", "close"])
    return agg.reset_index()


def fetch_all_symbols(timeframes: list[str]) -> dict[str, dict[str, pd.DataFrame]]:
    """Hämtar alla konfigurerade symboler för angivna timeframes. Kraschar aldrig helt."""
    result: dict[str, dict[str, pd.DataFrame]] = {}
    for symbol in YFINANCE_SYMBOLS:
        result[symbol] = {}
        for tf in timeframes:
            df = fetch_ohlcv(symbol, tf)
            result[symbol][tf] = df
            if df.empty:
                logger.warning("Ingen data för %s %s", symbol, tf)
    return result

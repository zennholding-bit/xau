"""
MarketDataProvider - primär implementation via Stooq (gratis, ingen nyckel).

BAKGRUND: yfinance (Yahoo Finance) blockerar ofta trafik från molnservrar
som GitHub Actions (bot-detektering/rate-limiting), vilket gjorde datainsamlingen
opålitlig i produktion. Stooq levererar enkla CSV-filer utan bot-skydd eller
komplicerade klientbibliotek, vilket gör den betydligt mer robust att köra
schemalagt i CI/CD-miljöer som GitHub Actions.

BEGRÄNSNING v1: Stooq gratis-CSV ger bara DAGSDATA (1d), inte intraday
(15m/1h/4h). Systemet körs därför på dagsdata tills en premiumleverantör
kopplas in (se README för uppgraderingsväg). Detta är en medveten avvägning:
ett system som fungerar pålitligt på dagsdata är mer värt än ett som ofta
misslyckas på timdata.

Designad som ett interface (duck-typed) så den senare kan bytas mot en
premiumleverantör (t.ex. Twelve Data, Polygon, OANDA) utan att signalmotorn
behöver ändras. Alla providers returnerar samma DataFrame-format:

    columns: ts (UTC datetime), open, high, low, close, volume
"""
from __future__ import annotations
import io
import logging
import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Stooq-symboler för respektive instrument. Stooq saknar tickers för vissa
# instrument (t.ex. vissa räntor) - de hanteras genom att helt enkelt
# returnera tom data, vilket resten av systemet redan är byggt för att tåla.
STOOQ_SYMBOLS = {
    "XAUUSD": "xauusd",
    "DXY": "usdx",
    "US10Y": "10usy.b",
    "US2Y": "2usy.b",
    "WTI": "cl.f",
    "BRENT": "bz.f",
    "SPX": "^spx",
    "NDX": "^ndq",
    "VIX": "^vix",
    "EURUSD": "eurusd",
    "USDJPY": "usdjpy",
}

# Endast dagsdata stöds i v1 (se modulens docstring för varför).
SUPPORTED_TIMEFRAMES = {"1d"}


class MarketDataUnavailableError(Exception):
    pass


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
def _download_stooq(ticker: str) -> pd.DataFrame:
    url = f"https://stooq.com/q/d/l/?s={ticker}&i=d"
    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()

    text = resp.text.strip()
    if not text or text.lower().startswith("no data") or "," not in text.splitlines()[0]:
        raise MarketDataUnavailableError(f"Stooq gav ingen giltig data för {ticker}")

    df = pd.read_csv(io.StringIO(text))
    if df.empty or "Date" not in df.columns:
        raise MarketDataUnavailableError(f"Tom/ogiltig CSV från Stooq för {ticker}")
    return df


def fetch_ohlcv(symbol: str, timeframe: str) -> pd.DataFrame:
    """
    Hämtar OHLCV för en given symbol/timeframe.
    Returnerar tom DataFrame (inte exception) om data inte kan hämtas,
    så anroparen kan logga och fortsätta utan att krascha hela pipelinen.
    """
    if timeframe not in SUPPORTED_TIMEFRAMES:
        logger.warning(
            "Timeframe %s stöds inte i v1 (endast 1d stöds via gratis Stooq-data) - hoppar över",
            timeframe,
        )
        return pd.DataFrame()

    ticker = STOOQ_SYMBOLS.get(symbol)
    if ticker is None:
        logger.warning("Okänd symbol %s - hoppar över", symbol)
        return pd.DataFrame()

    try:
        df = _download_stooq(ticker)
    except Exception as e:
        logger.error("Kunde inte hämta %s (%s) från Stooq: %s", symbol, timeframe, e)
        return pd.DataFrame()

    df = df.rename(columns={
        "Date": "ts", "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    if "volume" not in df.columns:
        df["volume"] = None

    df = df[["ts", "open", "high", "low", "close", "volume"]].dropna(
        subset=["open", "high", "low", "close"]
    )
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def fetch_all_symbols(timeframes: list[str]) -> dict[str, dict[str, pd.DataFrame]]:
    """Hämtar alla konfigurerade symboler för angivna timeframes. Kraschar aldrig helt."""
    result: dict[str, dict[str, pd.DataFrame]] = {}
    for symbol in STOOQ_SYMBOLS:
        result[symbol] = {}
        for tf in timeframes:
            df = fetch_ohlcv(symbol, tf)
            result[symbol][tf] = df
            if df.empty:
                logger.warning("Ingen data för %s %s", symbol, tf)
    return result

"""
MarketDataProvider - implementation via Twelve Data (gratis API-nivå, kräver nyckel).

BAKGRUND: Både Yahoo Finance (yfinance) och Stooq blockerar trafik från
molnservrar som GitHub Actions med bot-detektering (Cloudflare-liknande
JavaScript-utmaningar som en enkel HTTP-förfrågan inte kan lösa). Detta är
inte ett kod-problem utan en begränsning hos "gratis scraping"-källor.

Twelve Data är en riktig REST-API byggd för programmatisk åtkomst (inte en
webbsida som skrapas), vilket gör den pålitlig att köra schemalagt i CI/CD.
Gratis-nivån ger 800 anrop/dag och 8 anrop/minut - mer än tillräckligt för
en gång per dag-körning av detta system.

Skaffa gratis API-nyckel: https://twelvedata.com/pricing (Basic/Free-planen)
Lägg in som TWELVE_DATA_API_KEY i .env / GitHub Secrets.

BEGRÄNSNING v1: Twelve Data free tier stödjer intradagsdata (15min, 1h, 4h)
för huvudsymbolen XAU/USD - används av signal_cycle för täta uppdateringar.
Övriga cross-market-symboler hämtas bara som dagsdata (mindre kritiskt,
används bara som kontext). Vissa instrument (t.ex. amerikanska räntor)
stöds inte av Twelve Datas free tier och hoppas över med tydlig loggning.

Designad som ett interface (duck-typed) så den senare kan bytas mot en
premiumleverantör utan att signalmotorn behöver ändras. Alla providers
returnerar samma DataFrame-format: ts (UTC datetime), open, high, low, close, volume
"""
from __future__ import annotations
import logging
import time
import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from engine.config.settings import settings

logger = logging.getLogger(__name__)

# Twelve Data-symboler. Vissa instrument (särskilt amerikanska räntor) stöds
# inte tillförlitligt på free tier - de får gärna stå kvar här och hoppas
# över (loggas tydligt) tills en premiumkälla kopplas in.
TWELVEDATA_SYMBOLS = {
    "XAUUSD": "XAU/USD",
    "BTCUSD": "BTC/USD",
    "DXY": "DXY",
    "US10Y": None,   # inte tillgängligt på free tier
    "US2Y": None,    # inte tillgängligt på free tier
    "WTI": "WTI/USD",
    "BRENT": "BRENT/USD",
    "SPX": "SPX",
    "NDX": "NDX",
    "VIX": "VIX",
    "EURUSD": "EUR/USD",
    "USDJPY": "USD/JPY",
}

# Mappning till Twelve Datas eget intervallformat
TIMEFRAME_TO_TD_INTERVAL = {
    "5m": "5min",
    "15m": "15min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1day",
}
SUPPORTED_TIMEFRAMES = set(TIMEFRAME_TO_TD_INTERVAL.keys())

_MIN_SECONDS_BETWEEN_CALLS = 8.0  # håller oss under 8 anrop/minut (free tier-gräns)
_last_call_time = 0.0


class MarketDataUnavailableError(Exception):
    pass


def _throttle() -> None:
    global _last_call_time
    elapsed = time.time() - _last_call_time
    if elapsed < _MIN_SECONDS_BETWEEN_CALLS:
        time.sleep(_MIN_SECONDS_BETWEEN_CALLS - elapsed)
    _last_call_time = time.time()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=3, max=15), reraise=True)
def _download_twelvedata(td_symbol: str, td_interval: str) -> pd.DataFrame:
    if not settings.TWELVE_DATA_API_KEY:
        raise MarketDataUnavailableError(
            "TWELVE_DATA_API_KEY saknas - skaffa gratis nyckel på twelvedata.com och "
            "lägg in som GitHub Secret."
        )

    _throttle()
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": td_symbol,
        "interval": td_interval,
        "outputsize": 500,
        "apikey": settings.TWELVE_DATA_API_KEY,
        "timezone": "UTC",
    }
    resp = requests.get(url, params=params, timeout=20)

    if resp.status_code != 200:
        raise MarketDataUnavailableError(
            f"Twelve Data HTTP {resp.status_code} för {td_symbol}. Svar: {resp.text[:300]!r}"
        )

    data = resp.json()

    if isinstance(data, dict) and data.get("status") == "error":
        raise MarketDataUnavailableError(
            f"Twelve Data API-fel för {td_symbol}: {data.get('message', data)}"
        )

    values = data.get("values") if isinstance(data, dict) else None
    if not values:
        raise MarketDataUnavailableError(
            f"Twelve Data gav ingen 'values'-data för {td_symbol}. Svar: {str(data)[:300]}"
        )

    df = pd.DataFrame(values)
    return df


def fetch_ohlcv(symbol: str, timeframe: str) -> pd.DataFrame:
    """
    Hämtar OHLCV för en given symbol/timeframe.
    Returnerar tom DataFrame (inte exception) om data inte kan hämtas,
    så anroparen kan logga och fortsätta utan att krascha hela pipelinen.
    """
    td_interval = TIMEFRAME_TO_TD_INTERVAL.get(timeframe)
    if td_interval is None:
        logger.warning("Timeframe %s stöds inte - hoppar över", timeframe)
        return pd.DataFrame()

    td_symbol = TWELVEDATA_SYMBOLS.get(symbol)
    if td_symbol is None:
        logger.warning("%s stöds inte av Twelve Data free tier - hoppar över", symbol)
        return pd.DataFrame()

    try:
        df = _download_twelvedata(td_symbol, td_interval)
    except Exception as e:
        logger.error("Kunde inte hämta %s (%s) från Twelve Data: %s", symbol, timeframe, e)
        return pd.DataFrame()

    df = df.rename(columns={
        "datetime": "ts", "open": "open", "high": "high", "low": "low",
        "close": "close", "volume": "volume",
    })
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = None

    df = df[["ts", "open", "high", "low", "close", "volume"]].dropna(
        subset=["open", "high", "low", "close"]
    )
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def fetch_all_symbols(timeframes: list[str]) -> dict[str, dict[str, pd.DataFrame]]:
    """Hämtar alla konfigurerade symboler för angivna timeframes. Kraschar aldrig helt."""
    result: dict[str, dict[str, pd.DataFrame]] = {}
    for symbol in TWELVEDATA_SYMBOLS:
        result[symbol] = {}
        for tf in timeframes:
            df = fetch_ohlcv(symbol, tf)
            result[symbol][tf] = df
            if df.empty:
                logger.warning("Ingen data för %s %s", symbol, tf)
    return result

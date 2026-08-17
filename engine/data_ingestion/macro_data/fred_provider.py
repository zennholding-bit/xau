"""
FRED (Federal Reserve Economic Data) provider - gratis API för amerikansk makrodata.

Skaffa gratis nyckel: https://fred.stlouisfed.org/docs/api/api_key.html
Lägg in som FRED_API_KEY i .env / GitHub Secrets.

VIKTIG BEGRÄNSNING: FRED tillhandahåller endast FAKTISKA publicerade värden,
INTE analytikerkonsensus/forecast. Det betyder att vi inte kan räkna ut
"surprise = actual - forecast" som specen ursprungligen ville (det kräver en
betald ekonomisk kalender-tjänst, t.ex. Trading Economics eller Investing.com's
API). Istället beräknar vi en förändring vs föregående publicering
(actual - previous), vilket är en gratis, transparent proxy. `forecast` och
`surprise` lämnas som NULL i databasen - vi låtsas aldrig ha data vi inte har.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from engine.config.settings import settings

logger = logging.getLogger(__name__)

# FRED series ID -> (event_code, läsbart namn, enhet)
# Detta är de serier specen efterfrågade som faktiskt finns gratis på FRED.
FRED_SERIES = {
    "CPIAUCSL":  ("US_CPI", "US CPI (YoY, All Urban Consumers)", "%"),
    "CPILFESL":  ("US_CORE_CPI", "US Core CPI (ex food/energy)", "%"),
    "PCEPI":     ("US_PCE", "US PCE Price Index", "%"),
    "PCEPILFE":  ("US_CORE_PCE", "US Core PCE Price Index", "%"),
    "PAYEMS":    ("US_NFP", "US Non-Farm Payrolls", "thousands"),
    "UNRATE":    ("US_UNEMPLOYMENT_RATE", "US Unemployment Rate", "%"),
    "GDP":       ("US_GDP", "US GDP", "billions USD"),
    "RSAFS":     ("US_RETAIL_SALES", "US Retail Sales", "millions USD"),
    "FEDFUNDS":  ("FED_FUNDS_RATE", "Effective Federal Funds Rate", "%"),
    "DGS10":     ("US10Y_YIELD", "US 10-Year Treasury Yield", "%"),
    "DGS2":      ("US2Y_YIELD", "US 2-Year Treasury Yield", "%"),
    "DFII10":    ("US10Y_REAL_YIELD", "US 10-Year TIPS Real Yield", "%"),
    "T10YIE":    ("US_INFLATION_EXPECTATIONS", "US 10Y Breakeven Inflation Rate", "%"),
    "ICSA":      ("US_INITIAL_JOBLESS_CLAIMS", "US Initial Jobless Claims", "claims"),
}


class MacroDataUnavailableError(Exception):
    pass


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
def _fetch_series(series_id: str, limit: int = 6) -> list[dict]:
    if not settings.FRED_API_KEY:
        raise MacroDataUnavailableError(
            "FRED_API_KEY saknas - skaffa gratis nyckel på fred.stlouisfed.org och "
            "lägg in som GitHub Secret."
        )

    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": settings.FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }
    resp = requests.get(url, params=params, timeout=20)

    if resp.status_code != 200:
        raise MacroDataUnavailableError(
            f"FRED HTTP {resp.status_code} för {series_id}. Svar: {resp.text[:300]!r}"
        )

    data = resp.json()
    observations = data.get("observations")
    if not observations:
        raise MacroDataUnavailableError(f"FRED gav inga observationer för {series_id}")

    # Filtrera bort "." som FRED använder för saknade värden
    clean = [o for o in observations if o.get("value") not in (None, ".", "")]
    return clean


def fetch_latest_release(series_id: str) -> dict | None:
    """
    Hämtar de senaste två publiceringarna för en FRED-serie och returnerar
    ett dict redo att sparas i macro_events. Returnerar None om data saknas
    (kraschar aldrig hela pipelinen).
    """
    event_code, event_name, unit = FRED_SERIES[series_id]
    try:
        observations = _fetch_series(series_id, limit=6)
    except Exception as e:
        logger.error("Kunde inte hämta FRED-serie %s: %s", series_id, e)
        return None

    if len(observations) < 2:
        logger.warning("Otillräcklig historik för %s - hoppar över", series_id)
        return None

    latest = observations[0]
    previous = observations[1]

    try:
        actual = float(latest["value"])
        prev_value = float(previous["value"])
    except (ValueError, TypeError):
        logger.warning("Ogiltiga värden för %s - hoppar över", series_id)
        return None

    # release_time: FRED anger bara publiceringsDATUM, inte klockslag.
    # Vi sätter tiden till 12:30 UTC (typisk publiceringstid för amerikansk
    # makrodata, t.ex. BLS/BEA-releaser kl 08:30 ET) som en rimlig approximation.
    release_date = latest["date"]
    release_time = datetime.strptime(release_date, "%Y-%m-%d").replace(
        hour=12, minute=30, tzinfo=timezone.utc
    )

    return {
        "event_code": event_code,
        "event_name": event_name,
        "country": "US",
        "release_time": release_time.isoformat(),
        "actual": actual,
        "previous": prev_value,
        "forecast": None,   # inte tillgängligt gratis - se moduldocstring
        "surprise": None,   # kan inte beräknas utan forecast
        "surprise_pct": None,
        "unit": unit,
        "source": "FRED",
    }


def fetch_all_series() -> list[dict]:
    """Hämtar senaste publicering för alla konfigurerade serier. Kraschar aldrig helt."""
    results = []
    for series_id in FRED_SERIES:
        release = fetch_latest_release(series_id)
        if release:
            results.append(release)
        else:
            logger.warning("Ingen data för FRED-serie %s", series_id)
    return results

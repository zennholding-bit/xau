"""
Central konfiguration för hela systemet.
Allt läses från miljövariabler (.env lokalt, GitHub Secrets i produktion).
Inga nycklar hårdkodas någonsin.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Supabase ---
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # --- Makrodata ---
    FRED_API_KEY: str = ""

    # --- AI ---
    AI_PROVIDER: str = "none"  # none | openai | ollama
    OPENAI_API_KEY: str = ""

    # --- Trading / risk ---
    STARTING_BALANCE_SEK: float = 100_000.0
    MAX_RISK_PER_TRADE_PCT: float = 0.5  # % av kontot per trade

    # --- Signal thresholds ---
    BUY_THRESHOLD: float = 0.65
    SELL_THRESHOLD: float = -0.65

    # --- Symbols som ska hämtas ---
    PRIMARY_SYMBOL: str = "XAUUSD"

    def validate_critical(self) -> list[str]:
        """Returnerar en lista med varningar för saknad kritisk config."""
        warnings = []
        if not self.SUPABASE_URL or not self.SUPABASE_SERVICE_ROLE_KEY:
            warnings.append("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY saknas - databas kan inte nås.")
        if not self.FRED_API_KEY:
            warnings.append("FRED_API_KEY saknas - makrodata (CPI, NFP, etc) kan inte hämtas.")
        if self.AI_PROVIDER == "openai" and not self.OPENAI_API_KEY:
            warnings.append("AI_PROVIDER=openai men OPENAI_API_KEY saknas.")
        return warnings


settings = Settings()

# Symbols som hämtas via yfinance för marknadsdata + cross-market kontext
YFINANCE_SYMBOLS = {
    "XAUUSD": "GC=F",       # Gold futures (bra gratis proxy för spot)
    "DXY": "DX-Y.NYB",      # US Dollar Index
    "US10Y": "^TNX",        # 10Y Treasury yield (x10)
    "US2Y": "^IRX",         # kort ränta - approximation (13-week T-bill)
    "WTI": "CL=F",          # WTI Crude
    "BRENT": "BZ=F",        # Brent Crude
    "SPX": "^GSPC",         # S&P 500
    "NDX": "^NDX",          # Nasdaq 100
    "VIX": "^VIX",
    "EURUSD": "EURUSD=X",
    "USDJPY": "JPY=X",
}

TIMEFRAME_TO_INTERVAL = {
    "5m": "5m",
    "15m": "15m",
    "1h": "60m",
    "4h": "60m",   # yfinance saknar 4h nativt - vi resamplar från 1h
    "1d": "1d",
}

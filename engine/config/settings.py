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

    # --- Marknadsdata ---
    TWELVE_DATA_API_KEY: str = ""

    # --- AI ---
    AI_PROVIDER: str = "none"  # none | openai | ollama
    OPENAI_API_KEY: str = ""

    # --- Trading / risk ---
    STARTING_BALANCE_SEK: float = 100_000.0
    MAX_RISK_PER_TRADE_PCT: float = 0.5  # % av kontot per trade

    # --- Signal thresholds & risk, per symbol ---
    # XAUUSD: sänkt från 0.65 (2026-08-20): 143 körda signaler 16-20 aug visade
    # avg |score|=0.14, max=0.367, p90=0.266 - dvs 0.65 nåddes aldrig i
    # närheten. 0.28 ligger runt observerad 90:e percentil -> ~1 signal/dag
    # istället för noll, utan att slänga bort confluence-kravet i technical
    # engine.
    #
    # BTCUSD (2026-08-20): nytt instrument, ej kalibrerat mot skarp data ännu.
    # Startar högre än XAUUSD eftersom BTC:s ATR i % ofta är mycket större -
    # ett score som "känns lika starkt" som guldets kan motsvara en mindre
    # tillförlitlig rörelse på crypto. sl_atr_mult högre och max_risk_pct lägre
    # av samma skäl - sänk/justera efter att score-fördelningen observerats
    # i skarp drift (samma metod som gav XAUUSD:s 0.28).
    SYMBOLS: dict = {
        "XAUUSD": {
            "buy_threshold": 0.28,
            "sell_threshold": -0.28,
            "range_buy_threshold": 0.30,
            "range_sell_threshold": -0.30,
            "max_risk_pct": 0.5,
            "sl_atr_mult": 1.5,
            "rr_target": 2.0,
            "timeframe": "5m",
            "unit_label": "oz",
            "use_fundamental_context": True,
        },
        "BTCUSD": {
            "buy_threshold": 0.35,
            "sell_threshold": -0.35,
            "range_buy_threshold": 0.38,
            "range_sell_threshold": -0.38,
            "max_risk_pct": 0.3,
            "sl_atr_mult": 2.0,
            "rr_target": 2.0,
            "timeframe": "15m",
            "unit_label": "BTC",
            # False: makro/nyhets-tolkningen i context_builder.py är kalibrerad
            # för HUR DET PÅVERKAR GULD (t.ex. "sjunkande realränta -> stärker
            # guldets attraktivitet"). Samma logik gäller inte BTC. Tills en
            # egen BTC-kalibrerad modell finns körs BTC bara på technical_score.
            "use_fundamental_context": False,
        },
    }

    # --- Symbols som tradas aktivt (körs var för sig av signal_cycle) ---
    PRIMARY_SYMBOL: str = "XAUUSD"

    def validate_critical(self) -> list[str]:
        """Returnerar en lista med varningar för saknad kritisk config."""
        warnings = []
        if not self.SUPABASE_URL or not self.SUPABASE_SERVICE_ROLE_KEY:
            warnings.append("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY saknas - databas kan inte nås.")
        if not self.TWELVE_DATA_API_KEY:
            warnings.append("TWELVE_DATA_API_KEY saknas - marknadsdata kan inte hämtas.")
        if not self.FRED_API_KEY:
            warnings.append("FRED_API_KEY saknas - makrodata (CPI, NFP, etc) kan inte hämtas.")
        if self.AI_PROVIDER == "openai" and not self.OPENAI_API_KEY:
            warnings.append("AI_PROVIDER=openai men OPENAI_API_KEY saknas.")
        return warnings


settings = Settings()

# Symbols som hämtas via Stooq - se engine/data_ingestion/market_data/stooq_provider.py
# (filnamnet är historiskt, innehållet hämtar numera från Stooq)

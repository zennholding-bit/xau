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
    # SCALP-LÄGE (2026-08-20): byggt om från swing-stil (bred SL/TP, sällan
    # men "säkrare" trades) till scalping (tighta SL/TP, oftare men mindre
    # per trade + tidsbaserad tvångsstängning så inget ligger öppet länge).
    #
    # Vad som ändrats och varför:
    # - Trösklarna sänkta rejält (0.28->0.12 för XAUUSD) - scalping bygger på
    #   volym av små edge-trades, inte att vänta på stark övertygelse.
    # - rr_target sänkt till 1.0 (var 2.0) - scalping siktar på snabba,
    #   symmetriska in/ut, inte stora vinster per trade.
    # - sl_atr_mult sänkt kraftigt - tightare stop = trejden avgörs snabbare
    #   åt endera hållet istället för att flyta länge i limbo.
    # - max_hold_minutes: NYTT - om varken SL eller TP nås inom denna tid
    #   stängs traden ändå till marknadspris (se paper_trading.py). Det här
    #   är den faktiska lösningen på "en trade ska ej vara aktiv jätte länge".
    # - min_confidence_to_trade sänkt kraftigt (var globalt 60% - blockerade
    #   trades även när decision=BUY/SELL, se paper_trading.py).
    #
    # VIKTIGT att vara medveten om (inte kod, utan verklighet): fler och
    # snabbare trades betyder fler tillfällen där spread/avgifter äter upp
    # den lilla vinstmarginalen. Den här konfigurationen är okalibrerad mot
    # skarp data - se den som en startpunkt att observera och justera från,
    # precis som XAUUSD:s ursprungliga 0.28 togs fram genom att titta på
    # faktisk score-fördelning.
    SYMBOLS: dict = {
        "XAUUSD": {
            "buy_threshold": 0.12,
            "sell_threshold": -0.12,
            "range_buy_threshold": 0.12,
            "range_sell_threshold": -0.12,
            "max_risk_pct": 0.3,
            "sl_atr_mult": 0.6,
            "rr_target": 1.0,
            "timeframe": "5m",
            "unit_label": "oz",
            "use_fundamental_context": True,
            "max_hold_minutes": 30,
            "min_confidence_to_trade": 20.0,
        },
        "BTCUSD": {
            "buy_threshold": 0.18,
            "sell_threshold": -0.18,
            "range_buy_threshold": 0.18,
            "range_sell_threshold": -0.18,
            "max_risk_pct": 0.2,
            "sl_atr_mult": 0.8,
            "rr_target": 1.0,
            "timeframe": "15m",
            "unit_label": "BTC",
            # False: makro/nyhets-tolkningen i context_builder.py är kalibrerad
            # för HUR DET PÅVERKAR GULD (t.ex. "sjunkande realränta -> stärker
            # guldets attraktivitet"). Samma logik gäller inte BTC. Tills en
            # egen BTC-kalibrerad modell finns körs BTC bara på technical_score.
            "use_fundamental_context": False,
            "max_hold_minutes": 60,
            # Lägre än XAUUSD:s 20.0 med avsikt: BTC har use_fundamental_context=
            # False, vilket permanent ger bara 1/5 datakällor aktiva ->
            # coverage-delen av confidence-formeln blir bara 6 poäng (mot
            # XAUUSD:s 24). Vid BTC:s egen tröskel (0.18) blir confidence då
            # ~18.6% - en gräns på 20 hade tyst blockerat trades precis vid
            # tröskeln. 15 säkerställer att tröskel-nivå-signaler faktiskt
            # öppnar en trade.
            "min_confidence_to_trade": 15.0,
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

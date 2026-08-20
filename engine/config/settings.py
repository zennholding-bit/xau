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
    STARTING_BALANCE_SEK: float = 5_000.0
    MAX_RISK_PER_TRADE_PCT: float = 0.5  # % av kontot per trade

    # --- Signal thresholds & risk, per symbol ---
    # AGGRESSIV SCALP-PROFIL (2026-08-20, andra iterationen): trösklarna sänkta
    # ytterligare rejält (XAU 0.12->0.05, BTC 0.18->0.08) för att trades ska
    # ske i så gott som varje cykel snarare än sällan. VIKTIGT att förstå:
    # vid dessa nivåer är technical_score ofta lika mycket brus som riktig
    # signal (se observerad fördelning: avg |score| låg runt 0.13-0.14) - det
    # här prioriterar frekvens hårt över övertygelse per trade. Förvänta dig
    # en lägre andel vinnande trades än vid högre trösklar. Detta är ett
    # medvetet vägval, inte ett misstag - men bör observeras i paper_trades
    # över några dagar och justeras baserat på faktisk win-rate/pnl.
    #
    # max_hold_minutes kortades ytterligare (30->15 XAU, 60->30 BTC) och
    # sl_atr_mult tightades (0.6->0.4 XAU, 0.8->0.6 BTC) - snabbare
    # in/ut, mindre tid per trade, i linje med "snabba moves".
    SYMBOLS: dict = {
        "XAUUSD": {
            "buy_threshold": 0.05,
            "sell_threshold": -0.05,
            "range_buy_threshold": 0.05,
            "range_sell_threshold": -0.05,
            "max_risk_pct": 0.2,
            "sl_atr_mult": 0.4,
            "rr_target": 1.0,
            "timeframe": "5m",
            "unit_label": "oz",
            "use_fundamental_context": True,
            "max_hold_minutes": 15,
            "min_confidence_to_trade": 15.0,
            # Breakeven-stop (2026-08-20): när en trade gått breakeven_trigger_r
            # (0.5 = halvvägs till TP, i R-multiplar) i rätt riktning, flyttas
            # SL till entry + en liten buffert (breakeven_buffer_r) - traden
            # kan därefter aldrig vända till förlust, bara till en liten vinst
            # eller full TP. Skyddar INTE trades som går rakt till SL utan att
            # först röra sig i vinst.
            "breakeven_trigger_r": 0.5,
            "breakeven_buffer_r": 0.1,
            # Hävstång & marginal (2026-08-20): matchar IC Markets EU-reglerade
            # gräns för guld (CySEC/ESMA). Om ditt konto ligger under en
            # offshore-enhet kan verklig hävstång vara mycket högre - satt
            # konservativt/EU-standard tills motsatsen bekräftats.
            "leverage": 20,
            # En enskild trade får max använda denna andel av kontosaldot i
            # marginal - risk-baserad storlek skalas ner om den skulle kräva
            # mer, så systemet aldrig föreslår en position som vore omöjlig
            # att öppna på riktigt hos brokern.
            "max_margin_pct_per_trade": 0.5,
        },
        "BTCUSD": {
            "buy_threshold": 0.08,
            "sell_threshold": -0.08,
            "range_buy_threshold": 0.08,
            "range_sell_threshold": -0.08,
            "max_risk_pct": 0.15,
            "sl_atr_mult": 0.6,
            "rr_target": 1.0,
            "timeframe": "5m",
            "unit_label": "BTC",
            # False: makro/nyhets-tolkningen i context_builder.py är kalibrerad
            # för HUR DET PÅVERKAR GULD (t.ex. "sjunkande realränta -> stärker
            # guldets attraktivitet"). Samma logik gäller inte BTC. Tills en
            # egen BTC-kalibrerad modell finns körs BTC bara på technical_score.
            "use_fundamental_context": False,
            "max_hold_minutes": 30,
            "min_confidence_to_trade": 8.0,
            "breakeven_trigger_r": 0.5,
            "breakeven_buffer_r": 0.1,
            # Krypto har mycket lägre EU-tillåten hävstång än guld (1:2 mot
            # 1:20) - viktigt att INTE använda samma hävstång för båda.
            "leverage": 2,
            "max_margin_pct_per_trade": 0.5,
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

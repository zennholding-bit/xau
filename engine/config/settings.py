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

    # Total marginal (2026-08-20): en riktig broker delar INTE upp marginal
    # per symbol - all marginal låst av ALLA öppna positioner (guld + krypto
    # ihop) dras från samma konto. TOTAL_MARGIN_CAP_PCT sätter ett tak för
    # hur stor andel av kontosaldot som får vara låst totalt, över alla
    # symboler, samtidigt. 0.6 = max 60% av saldot i marginal samtidigt,
    # vilket lämnar god marginal-nivå (margin level) kvar innan IC Markets
    # 50%-stop-out-gräns skulle kunna nås vid ogynnsam prisrörelse.
    TOTAL_MARGIN_CAP_PCT: float = 0.6

    # --- Signal thresholds & risk ---
    # Fokus enbart på XAUUSD (2026-08-20): BTCUSD, NDX, SPX och WTI togs alla
    # bort - beslutet var att lägga allt fokus på att göra guld-motorn
    # perfekt istället för att sprida ut kvalitet över flera okalibrerade
    # instrument samtidigt.
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

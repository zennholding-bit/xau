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
    # max_hold_minutes TOGS BORT (2026-08-20) - trades stänger nu bara vid
    # SL/TP-träff, precis som på ett riktigt broker-konto (mäklare stänger
    # aldrig en position bara för att tiden gått). sl_atr_mult tightades
    # tidigare (0.6->0.4 XAU, 0.8->0.6 BTC) för snabbare in/ut.
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
        # Nya instrument (2026-08-20): NDX (Nasdaq-100), SPX (S&P 500), WTI
        # (råolja). VIKTIGT samma varning som gällde BTC: use_fundamental_
        # context=False för alla tre, eftersom makro-tolkningen i
        # context_builder.py är kalibrerad specifikt för HUR DET PÅVERKAR
        # GULD ("sjunkande realränta -> stärker guldets attraktivitet") -
        # den logiken stämmer inte rakt av för aktieindex (mer komplex
        # ränte-relation) eller olja (drivs mer av utbud/efterfrågan/OPEC än
        # av räntor). Alla tre kör därför bara på technical_score tills
        # tillgångsspecifik makro-kalibrering byggs.
        #
        # Trösklar/SL satta KONSERVATIVT och OKALIBRERAT (0.15, bredare SL än
        # guldets 0.05/0.4) - vi har ingen observerad score-fördelning för
        # dessa än. Justera efter några dagars drift, precis som XAUUSD:s
        # 0.28->0.05 togs fram genom att titta på faktisk data.
        #
        # Hävstång matchar IC Markets EU-reglerade gränser: index 1:5,
        # råvaror (olja) 1:10.
        "NDX": {
            "buy_threshold": 0.15,
            "sell_threshold": -0.15,
            "range_buy_threshold": 0.15,
            "range_sell_threshold": -0.15,
            "max_risk_pct": 0.15,
            "sl_atr_mult": 0.6,
            "rr_target": 1.0,
            "timeframe": "1h",
            "unit_label": "kontrakt",
            "use_fundamental_context": False,
            "min_confidence_to_trade": 10.0,
            "breakeven_trigger_r": 0.5,
            "breakeven_buffer_r": 0.1,
            "leverage": 5,
            "max_margin_pct_per_trade": 0.5,
        },
        "SPX": {
            "buy_threshold": 0.15,
            "sell_threshold": -0.15,
            "range_buy_threshold": 0.15,
            "range_sell_threshold": -0.15,
            "max_risk_pct": 0.15,
            "sl_atr_mult": 0.6,
            "rr_target": 1.0,
            "timeframe": "1h",
            "unit_label": "kontrakt",
            "use_fundamental_context": False,
            "min_confidence_to_trade": 10.0,
            "breakeven_trigger_r": 0.5,
            "breakeven_buffer_r": 0.1,
            "leverage": 5,
            "max_margin_pct_per_trade": 0.5,
        },
        "WTI": {
            "buy_threshold": 0.15,
            "sell_threshold": -0.15,
            "range_buy_threshold": 0.15,
            "range_sell_threshold": -0.15,
            "max_risk_pct": 0.15,
            "sl_atr_mult": 0.6,
            "rr_target": 1.0,
            "timeframe": "1h",
            "unit_label": "fat",
            "use_fundamental_context": False,
            "min_confidence_to_trade": 10.0,
            "breakeven_trigger_r": 0.5,
            "breakeven_buffer_r": 0.1,
            "leverage": 10,
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

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
            # Höjd (2026-08-20) från 0.2% -> 0.75% på användarens begäran -
            # 0.2% gav bara ~10 SEK risk per trade på ett 5000 SEK-konto,
            # vilket kändes för litet för att märkas. 0.75% ger ~35-40 SEK
            # risk/vinst istället. Marginal-kollen (cap_size_by_margin,
            # TOTAL_MARGIN_CAP_PCT) skalar fortfarande ner storleken om en
            # trade skulle kräva mer marginal än rimligt - höjd risk% byter
            # alltså inte bort det skyddet, den höjer bara taket innan det
            # slår till.
            "max_risk_pct": 0.75,
            "sl_atr_mult": 0.4,
            # Höjd (2026-08-20) från 1.0 -> 1.5: data visade att 20 av 21
            # vinster stängdes i förtid av breakeven (snitt 0.82 SEK) medan
            # den enda som nådde full TP gav 25.43 SEK - 31x mer. Med TP bara
            # 1R bort låg breakeven-triggern (0.5R) exakt halvvägs, så minsta
            # studs tillbaka stängde traden. Mer avstånd till TP ger riktigt
            # utrymme att springa innan målet nås.
            "rr_target": 1.5,
            # Tak (2026-08-20) på hur långt strukturmodellen får skjuta TP
            # även om nästa verkliga motstånd/stöd ligger längre bort - annars
            # kan mål bli orealistiskt avlägsna (se risk_engine.py:s
            # structure_based_sltp för bakgrund). 2.0 = TP får max bli dubbelt
            # så långt bort som SL, aldrig mer.
            "max_rr_cap": 2.0,
            # 2026-08-21 (uppdaterad): pip_size används fortfarande av
            # dashboarden och säkerhetsnätet nedan. De TIGHTA gränserna
            # (60-300) togs bort som primär mekanism - de körde över
            # modellernas egna, redan konsekventa RR-förhållanden och gav
            # RR mellan 0.26 och 5.01 på olika trades istället för ett
            # stabilt förhållande. Nu bara ett extremt vitt säkerhetsnät.
            "pip_size": 0.01,
            "min_tp_pips_safety_net": 15,
            "max_tp_pips_safety_net": 1000,
            # Avvisar strukturbaserad SL om den är bredare än detta ×ATR -
            # se signal_engine.py för fullständig förklaring av varför.
            "max_structure_sl_atr_mult": 2.5,
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
            # Höjd (2026-08-20) från 0.5 -> 0.7: i kombination med rr_target
            # 1.5 innebär det att breakeven nu triggar vid 0.7R av totalt
            # 1.5R till TP (47% av vägen, inte 100% som tidigare vid 0.5R/1R)
            # - fortfarande ett skydd, men mycket senare och närmare målet,
            # så färre vinster stryps i förtid.
            # Höjd (2026-08-20, tredje justeringen) från 0.7 -> 0.9: data
            # visade att även 0.7R fortfarande fångade 66% av alla vinster i
            # förtid (snitt 1.62 SEK mot 12.90 SEK för de som nådde full TP).
            # Misstänkt orsak: med en tight SL (0.4xATR) når priset 0.7R ofta
            # bara av vanligt marknadsbrus, inte en riktig rörelse. 0.9R
            # triggar nu vid 60% av vägen till TP (var 47% vid 0.7R) - mer
            # utrymme för traden att faktiskt nå TP innan skyddet låser in.
            "breakeven_trigger_r": 0.9,
            # Höjd (2026-08-20) från 0.1R -> 0.3R på användarens begäran -
            # ger en större garanterad vinst när breakeven-skyddet triggar
            # (tidigare snitt +1.62 SEK per räddad trade, nu ~3x så mycket).
            # Avvägning: SL flyttas nu längre bort från entry vid trigger,
            # vilket kräver en något större rörelse tillbaka för att träffas.
            "breakeven_buffer_r": 0.3,
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

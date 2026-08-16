# XAU (v0.1 - MVP)

Ett automatiskt system som samlar marknadsdata för guld (XAU/USD), kör
deterministisk teknisk analys, genererar BUY/SELL/NO_TRADE-signaler med
entry/SL/TP/confidence, och paper-tradar dem (simulerat, inga riktiga pengar).

**INGEN riktig handel sker eller kan ske i denna version.** `LiveBroker` är
permanent inaktiverad i koden (se `engine/paper_trading/broker_interface.py`).

## Vad som fungerar just nu (v0.1)

✅ Marknadsdata (XAU/USD + 10 cross-market-symboler) via yfinance, gratis
✅ Deterministisk teknisk analys: EMA20/50/200, RSI, MACD, ATR, volatilitet,
   support/resistance, market structure (HH/HL vs LH/LL), breakout-detektion
✅ Signal engine som kombinerar scores till final_score + confidence, med
   automatisk nedviktning av confidence när data saknas
✅ Risk engine: ATR-baserad och struktur-baserad SL/TP, position sizing (0.5% risk/trade)
✅ Paper trading engine: öppnar/stänger trades, räknar P&L/R-multiple, uppdaterar saldo
✅ Fullständigt databasschema (Supabase/Postgres) för hela pipelinen inkl. audit-trail
✅ GitHub Actions-workflows för schemalagd körning (gratis)
✅ Dashboard (Next.js) - KPI-kort, equity curve, latest signals-panel, datumfilter
✅ 21 automatiska tester, alla gröna

## Vad som INTE är byggt än (nästa steg)

❌ Makrodata-ingestion (CPI, NFP, Fed Funds Rate via FRED API) - tabeller finns, ingestion saknas
❌ Nyhets-ingestion + AI/regelbaserad analys - tabeller finns, ingestion saknas
❌ Backtesting-modul - databasstruktur klar, motor saknas
❌ Cross-market score-beräkning (just nu `data_quality="missing"`)
❌ Signalens detaljvy / "Varför togs denna trade?"-popup - kommer i nästa dashboard-iteration

Fram tills nyheter/makro finns inkopplat körs signal engine **enbart på teknisk
analys**, och systemet dämpar automatiskt confidence för att kompensera
(se `engine/signal_engine/signal_engine.py` - `_renormalized_weights`).

---

## Dashboard - deploy till Vercel

Dashboarden (`dashboard/`) är en Next.js-app som läser direkt från Supabase.
Den **skriver aldrig** till databasen - bara GitHub Actions gör det. Därför
använder dashboarden Supabase `anon`-nyckeln (läs-nyckel), inte `service_role`.

### Steg för att deploya

1. Gå till https://vercel.com, logga in med GitHub.
2. **Add New -> Project** -> välj ditt `xau`-repo.
3. **Viktigt:** i "Root Directory" - klicka **Edit** och välj mappen `dashboard`
   (inte repots rot, annars hittar Vercel ingen Next.js-app).
4. Under **Environment Variables**, lägg in:
   - `NEXT_PUBLIC_SUPABASE_URL` = din Supabase Project URL (samma som i GitHub Secrets)
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY` = din Supabase **anon**-nyckel (Project Settings -> API Keys ->
     `anon` `public`, INTE `service_role`)
5. Klicka **Deploy**.

Efter deploy får du en URL (typ `xau-xyz.vercel.app`) där dashboarden syns live,
och uppdateras automatiskt varje gång GitHub Actions skriver nya signaler/trades.

### Testa lokalt innan deploy (valfritt)

```bash
cd dashboard
npm install
cp .env.local.example .env.local   # fyll i dina Supabase-uppgifter
npm run dev
```
Öppna http://localhost:3000

---

## Arkitektur

```
GitHub Actions (cron var 15:e min)
        │
        ▼
  engine/signal_engine/run_signal_cycle.py
        │
        ├─► data_ingestion/market_data  (yfinance, gratis)
        ├─► analysis/technical          (EMA/RSI/MACD/ATR/struktur)
        ├─► signal_engine                (kombinerar scores -> BUY/SELL/NO_TRADE)
        ├─► risk_engine                  (SL/TP, position sizing)
        └─► paper_trading                (öppnar/stänger simulerade trades)
                │
                ▼
          Supabase (Postgres)
                │
                ▼
      Dashboard (Next.js på Vercel) - byggs i nästa steg, läser direkt från Supabase
```

**Varför ingen server behövs:** GitHub Actions kör Python-scripten på schema
(gratis, inom GitHub:s gränser), skriver resultatet till Supabase, och
stängs sedan ner. Ingen process behöver vara "på" dygnet runt.

---

## Installation

### 1. Python

Kräver Python 3.11+.

```bash
cd xau-trading-system
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Skapa Supabase-projekt

1. Gå till https://supabase.com och skapa ett gratis projekt.
2. Öppna **SQL Editor** i Supabase-dashboarden.
3. Klistra in hela innehållet från `engine/database/schema.sql` och kör det.
   Detta skapar alla tabeller (market_prices, signals, paper_trades, etc).
4. Gå till **Project Settings -> API** och kopiera:
   - `Project URL` -> blir `SUPABASE_URL`
   - `service_role` secret key -> blir `SUPABASE_SERVICE_ROLE_KEY`
   (Använd INTE `anon`-nyckeln för backend-scripten.)

### 3. Miljövariabler

```bash
cp .env.example .env
```

Öppna `.env` och fyll i `SUPABASE_URL` och `SUPABASE_SERVICE_ROLE_KEY`.

### 4. Testa lokalt

```bash
python -m engine.data_ingestion.market_data.run_ingest   # hämtar & sparar marknadsdata
python -m engine.signal_engine.run_signal_cycle           # kör en full signal-cykel
```

### 5. Kör testerna

```bash
pytest tests/ -v
```

---

## Automatisk körning via GitHub Actions (gratis)

1. Pusha detta repo till GitHub.
2. Gå till **repo -> Settings -> Secrets and variables -> Actions**.
3. Lägg till secrets:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `FRED_API_KEY` (när du skaffat en, se nedan)
4. Workflows i `.github/workflows/` körs automatiskt:
   - `market_data_ingest.yml` - varje timme, bred historik
   - `signal_cycle.yml` - var 15:e minut, hela signal-pipelinen
5. Du kan även trigga dem manuellt: repo -> **Actions** -> välj workflow -> **Run workflow**.

---

## Vilka konton/API-nycklar du behöver skaffa själv

| Nyckel | Krävs för | Var du skaffar den | Gratis? |
|---|---|---|---|
| Supabase URL + service_role key | Hela databasen | https://supabase.com | Ja (free tier) |
| `FRED_API_KEY` | Makrodata (CPI, NFP, etc) - **byggs i nästa steg** | https://fred.stlouisfed.org/docs/api/api_key.html | Ja |
| `OPENAI_API_KEY` (valfritt) | AI-analys av nyheter - **byggs senare, du valde regelbaserat först** | https://platform.openai.com | Nej, kostar per anrop |

Marknadsdata (yfinance) kräver ingen nyckel alls.

---

## Konfiguration

Alla trösklar och riskparametrar styrs i `.env` / `engine/config/settings.py`:

- `STARTING_BALANCE_SEK` (default 100 000)
- `MAX_RISK_PER_TRADE_PCT` (default 0.5%)
- `BUY_THRESHOLD` / `SELL_THRESHOLD` (default ±0.65)

---

## Begränsningar med gratisdata just nu

- **yfinance** har inga garantier om upptid/latens - kan tillfälligt saknas.
  Systemet hanterar detta genom att hoppa över och logga, inte krascha.
- 1-minutersdata stöds inte i v1 (yfinance begränsar historik kraftigt för 1m).
- Ingen riktig orderbok/spread - spread simuleras inte ännu i paper trading (läggs till).
- Utan nyheter/makro kopplat blir signal engine begränsad till teknisk analys,
  vilket enligt spec ska hålla confidence nere (vilket det gör - verifierat i tester).

## Vad som bör uppgraderas först om systemet visar edge

1. Riktig realtids-tick-data för XAU/USD (istället för yfinance 1h-delay)
2. Betald nyhets-API med lägre latens (t.ex. Benzinga, Bloomberg) istället för RSS
3. FRED + en andra makrokälla för redundans
4. Spread/slippage-modellering i paper trading för mer realistisk P&L

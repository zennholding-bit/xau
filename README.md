# XAU (v0.1 - MVP)

Ett automatiskt system som samlar marknadsdata för guld (XAU/USD), kör
deterministisk teknisk analys, genererar BUY/SELL/NO_TRADE-signaler med
entry/SL/TP/confidence, och paper-tradar dem (simulerat, inga riktiga pengar).

**INGEN riktig handel sker eller kan ske i denna version.** `LiveBroker` är
permanent inaktiverad i koden (se `engine/paper_trading/broker_interface.py`).

## Vad som fungerar just nu (v0.2)

✅ Marknadsdata (XAU/USD, 5-minuters candles) via Twelve Data, gratis API
✅ Deterministisk teknisk analys: EMA20/50/200, RSI, MACD, ATR, volatilitet,
   support/resistance, market structure (HH/HL vs LH/LL), breakout-detektion
✅ **Makrodata (FRED)**: CPI, Core CPI, PCE, NFP, arbetslöshet, Fed Funds Rate,
   räntor m.m. - regelbaserad tolkning genom kända transmissionskanaler till guld
✅ **Nyhetsinsamling (RSS)**: Fed, inflation, geopolitik, energi, finansiell
   stress - från 8 gratis RSS-källor, med dedup/klustring så samma händelse
   från flera källor inte räknas dubbelt
✅ **Regelbaserad fundamental-analys**: varje nyhet/makrohändelse tolkas genom
   en ekonomisk transmissionskanal (t.ex. geopolitik → safe haven-efterfrågan
   → guld), inte bara "bra/dåligt". Se `engine/analysis/fundamental/`
✅ **Cross-market score**: DXY, US10Y-ränta och WTI-olja vägs in via kända
   samband till guldpriset
✅ Signal engine kombinerar teknisk + fundamental + makro + nyheter +
   cross-market till ett final_score, med automatisk nedviktning av
   confidence när enskild data saknas
✅ Risk engine: ATR-baserad och struktur-baserad SL/TP, position sizing (0.5% risk/trade)
✅ Paper trading engine: öppnar/stänger trades, räknar P&L/R-multiple, uppdaterar saldo
✅ Fullständig auditbarhet: varje signal länkas till exakt vilka nyheter och
   makrohändelser som låg bakom den (signal_news_links / signal_macro_links)
✅ Fullständigt databasschema (Supabase/Postgres) för hela pipelinen
✅ GitHub Actions-workflows för schemalagd körning (gratis) - signaler var
   5:e minut, nyheter var 30:e minut, makrodata var 6:e timme
✅ Dashboard (Next.js) - KPI-kort, equity curve, latest signals-panel, datumfilter
✅ 54 automatiska tester, alla gröna

## Vad som INTE är byggt än (nästa steg)

❌ AI/LLM-baserad analys - just nu regelbaserat (du valde detta i v1). Kan
   kopplas in senare (t.ex. OpenAI) utan att signal-motorn behöver ändras -
   se `AI_PROVIDER` i `.env.example`
❌ Backtesting-modul - databasstruktur klar, motor saknas
❌ Signalens detaljvy / "Varför togs denna trade?"-popup i dashboarden -
   datan finns redan (signal_news_links/signal_macro_links), bara UI saknas

**Viktig ärlighet om makrodata:** FRED (gratis) ger bara FAKTISKA publicerade
värden, inte analytikerkonsensus/forecast. Det betyder att vi inte kan räkna
"överraskning vs förväntan" (kräver en betald ekonomisk kalender-tjänst).
Istället används förändring mot föregående publicering som en transparent
gratis-proxy. `forecast`/`surprise`-fälten i databasen lämnas NULL - vi
låtsas aldrig ha data vi inte har.

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
| `TWELVE_DATA_API_KEY` | **Marknadsdata (XAU/USD)** | https://twelvedata.com/pricing (Basic/Free) | Ja (800 anrop/dag) |
| `FRED_API_KEY` | **Makrodata (CPI, NFP, Fed Funds Rate m.m.)** | https://fred.stlouisfed.org/docs/api/api_key.html | Ja |
| `OPENAI_API_KEY` (valfritt) | AI-analys av nyheter - **ej byggt, systemet kör regelbaserat** | https://platform.openai.com | Nej, kostar per anrop |

### Steg-för-steg: skaffa FRED-nyckeln

1. Gå till https://fred.stlouisfed.org/docs/api/api_key.html
2. Klicka "Request API Key" (kräver ett gratis FRED-konto - registrera med mejl)
3. Fyll i det korta formuläret (används bara internt av FRED, ingen betalning)
4. Nyckeln visas direkt efter registrering - kopiera den
5. Lägg in i **GitHub → repo → Settings → Secrets and variables → Actions →
   New repository secret**:
   - Name: `FRED_API_KEY`
   - Secret: din nyckel

Ingen annan konfiguration behövs - `macro_data_ingest.yml`-workflowet plockar
upp den automatiskt.

Marknadsdata krävde tidigare ingen nyckel (yfinance/Stooq), men båda dessa
gratis "scraping"-källor visade sig blockera trafik från GitHub Actions med
bot-skydd. Twelve Data är en riktig API och kräver därför en (gratis) nyckel.
RSS-nyheter kräver ingen nyckel alls (RSS är byggt för maskinell åtkomst).

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

-- =====================================================================
-- XAU/USD AI Trading System - Database Schema
-- Kör detta i Supabase SQL Editor (Project -> SQL Editor -> New query)
-- =====================================================================

-- ---------------------------------------------------------------------
-- MARKET PRICES
-- ---------------------------------------------------------------------
create table if not exists market_prices (
    id              bigserial primary key,
    symbol          text not null,              -- t.ex. 'XAUUSD', 'DXY', 'US10Y', 'WTI'
    timeframe       text not null,               -- '1m','5m','15m','1h','4h','1d'
    ts              timestamptz not null,        -- candle open time (UTC)
    open            numeric,
    high            numeric,
    low             numeric,
    close           numeric,
    volume          numeric,
    spread          numeric,
    source          text not null,
    received_at     timestamptz not null default now(),
    quality_score   numeric default 1.0,         -- 0-1, 1 = fullt tillförlitlig
    unique (symbol, timeframe, ts, source)
);
create index if not exists idx_market_prices_lookup
    on market_prices (symbol, timeframe, ts desc);

-- ---------------------------------------------------------------------
-- MACRO EVENTS (CPI, NFP, Fed Funds Rate, etc.)
-- ---------------------------------------------------------------------
create table if not exists macro_events (
    id                  bigserial primary key,
    event_code          text not null,           -- 'US_CPI_YOY', 'US_NFP', 'FED_FUNDS_RATE', ...
    event_name          text not null,
    country             text default 'US',
    release_time        timestamptz not null,    -- exakt publiceringstid (kritiskt för lookahead-skydd)
    actual              numeric,
    previous             numeric,
    forecast            numeric,
    surprise            numeric,                 -- actual - forecast
    surprise_pct        numeric,
    revision_previous   numeric,
    unit                text,
    source              text not null,
    received_at         timestamptz not null default now(),
    quality_score        numeric default 1.0,
    unique (event_code, release_time, source)
);
create index if not exists idx_macro_events_time on macro_events (release_time desc);
create index if not exists idx_macro_events_code on macro_events (event_code);

-- ---------------------------------------------------------------------
-- NEWS ARTICLES (raw ingestion, dedup via cluster_id)
-- ---------------------------------------------------------------------
create table if not exists news_articles (
    id                  bigserial primary key,
    external_id         text,                    -- id/guid från källan om finns
    source              text not null,
    headline            text not null,
    summary             text,
    url                 text,
    published_at        timestamptz not null,    -- publiceringstid, respekteras strikt för lookahead
    received_at         timestamptz not null default now(),
    category            text,                    -- 'inflation','geopolitics','central_bank','energy',...
    mentioned_countries  text[],
    mentioned_assets     text[],
    cluster_id          text,                    -- grupperar samma händelse från flera källor
    raw_hash            text,                    -- hash av normaliserad headline för snabb dedup
    quality_score        numeric default 1.0,
    unique (source, external_id)
);
create index if not exists idx_news_published on news_articles (published_at desc);
create index if not exists idx_news_cluster on news_articles (cluster_id);
create index if not exists idx_news_hash on news_articles (raw_hash);

-- ---------------------------------------------------------------------
-- NEWS ANALYSIS (AI/regelbaserad output per artikel eller kluster)
-- ---------------------------------------------------------------------
create table if not exists news_analysis (
    id                      bigserial primary key,
    news_id                 bigint references news_articles(id) on delete cascade,
    cluster_id              text,
    analyzer_version        text not null,        -- 'rule_based_v1', 'openai_gpt4_v1', ...
    importance_score        numeric,              -- 0-100
    sentiment               text,                 -- 'positive','negative','neutral'
    xau_direction           text,                 -- 'bullish','bearish','neutral'
    xau_score               numeric,              -- -1 .. +1
    usd_direction           text,
    yield_direction         text,
    oil_direction            text,
    risk_sentiment           text,                -- 'risk_on','risk_off','mixed'
    novelty_score            numeric,              -- 0-1, hur unik/ny händelsen är
    reasoning_summary        text,
    conflicting_factors      jsonb,
    time_horizon_scores       jsonb,               -- {"15m":0.7,"1h":0.8,...}
    raw_output                jsonb,               -- full rådata från analysen
    created_at                timestamptz not null default now()
);
create index if not exists idx_news_analysis_news on news_analysis (news_id);
create index if not exists idx_news_analysis_cluster on news_analysis (cluster_id);

-- ---------------------------------------------------------------------
-- TECHNICAL SNAPSHOTS (indikatorer vid en given tidpunkt)
-- ---------------------------------------------------------------------
create table if not exists technical_snapshots (
    id                  bigserial primary key,
    symbol              text not null,
    timeframe           text not null,
    ts                  timestamptz not null,
    close               numeric,
    ema_20              numeric,
    ema_50              numeric,
    ema_200             numeric,
    rsi_14              numeric,
    macd                numeric,
    macd_signal         numeric,
    macd_hist           numeric,
    atr_14              numeric,
    volatility          numeric,
    prev_high           numeric,
    prev_low            numeric,
    support             numeric,
    resistance           numeric,
    trend               text,                    -- 'up','down','sideways'
    breakout            boolean default false,
    market_structure     text,                    -- 'HH_HL','LH_LL','range',...
    momentum             numeric,
    distance_from_high   numeric,
    distance_from_low    numeric,
    technical_score       numeric,                 -- -1 .. +1
    strategy_mode         text,                    -- 'trend' eller 'range' - vilken modell som producerade scoret
    created_at            timestamptz not null default now(),
    unique (symbol, timeframe, ts)
);
create index if not exists idx_tech_snapshots_lookup
    on technical_snapshots (symbol, timeframe, ts desc);

-- ---------------------------------------------------------------------
-- SIGNALS
-- ---------------------------------------------------------------------
create table if not exists signals (
    id                      bigserial primary key,
    signal_uid              text unique not null,  -- t.ex. 'SIG-20260816-0001'
    symbol                  text not null default 'XAUUSD',
    created_at               timestamptz not null default now(),
    decision                text not null,          -- 'BUY','SELL','NO_TRADE'
    strategy_mode            text,                  -- 'trend' eller 'range' - vilka trösklar/modell som användes
    entry                    numeric,
    stop_loss                numeric,
    take_profit               numeric,
    risk_reward                numeric,
    confidence                 numeric,              -- 0-100
    final_score                numeric,              -- -1 .. +1
    technical_score             numeric,
    fundamental_score           numeric,
    macro_score                 numeric,
    news_score                  numeric,
    cross_market_score          numeric,
    risk_score                  numeric,
    volatility                  numeric,
    time_horizon                text,                -- '15m','1h','4h','24h'
    expires_at                  timestamptz,
    short_explanation           text,
    full_reasoning              text,
    market_conditions_snapshot  jsonb,               -- fryst ögonblicksbild av tekniska/makro-data vid signaltillfället
    status                       text not null default 'OPEN', -- 'OPEN','EXPIRED','CANCELLED','TRADED'
    sl_model                     text,                -- vilken SL/TP-modell som användes
    tp_model                     text
);
create index if not exists idx_signals_created on signals (created_at desc);
create index if not exists idx_signals_status on signals (status);

-- ---------------------------------------------------------------------
-- SIGNAL <-> NEWS / MACRO LINKS (auditbarhet)
-- ---------------------------------------------------------------------
create table if not exists signal_news_links (
    signal_id   bigint references signals(id) on delete cascade,
    news_id     bigint references news_articles(id) on delete cascade,
    weight      numeric default 1.0,
    primary key (signal_id, news_id)
);

create table if not exists signal_macro_links (
    signal_id       bigint references signals(id) on delete cascade,
    macro_event_id  bigint references macro_events(id) on delete cascade,
    weight          numeric default 1.0,
    primary key (signal_id, macro_event_id)
);

-- ---------------------------------------------------------------------
-- PAPER TRADES
-- ---------------------------------------------------------------------
create table if not exists paper_trades (
    id                  bigserial primary key,
    signal_id           bigint references signals(id) on delete set null,
    symbol              text not null default 'XAUUSD',
    direction           text not null,           -- 'BUY','SELL'
    entry_time           timestamptz not null,
    exit_time            timestamptz,
    entry_price           numeric not null,
    exit_price            numeric,
    stop_loss             numeric not null,
    take_profit            numeric not null,
    position_size           numeric not null,      -- i lot/oz beroende på symbol
    risk_amount_sek         numeric not null,       -- SEK riskerat på traden
    spread_cost              numeric default 0,
    slippage                 numeric default 0,
    commission                numeric default 0,
    pnl_sek                  numeric,
    pnl_pct                   numeric,
    r_multiple                 numeric,
    mfe                        numeric,              -- max favorable excursion
    mae                        numeric,              -- max adverse excursion
    outcome                    text,                 -- 'WIN','LOSS','BREAKEVEN','EXPIRED','CANCELLED','OPEN'
    account_balance_after       numeric,
    created_at                   timestamptz not null default now()
);
create index if not exists idx_paper_trades_entry on paper_trades (entry_time desc);
create index if not exists idx_paper_trades_outcome on paper_trades (outcome);

-- ---------------------------------------------------------------------
-- TRADE EVENTS (audit-logg per trade: öppning, partial, justering, stängning)
-- ---------------------------------------------------------------------
create table if not exists trade_events (
    id          bigserial primary key,
    trade_id    bigint references paper_trades(id) on delete cascade,
    event_type  text not null,   -- 'OPENED','SL_HIT','TP_HIT','EXPIRED','CANCELLED','MANUAL_CLOSE'
    event_time  timestamptz not null default now(),
    price        numeric,
    details      jsonb
);

-- ---------------------------------------------------------------------
-- DAILY STATISTICS (aggregerat, snabbar upp dashboard)
-- ---------------------------------------------------------------------
create table if not exists daily_statistics (
    id                  bigserial primary key,
    date                 date not null unique,
    account_balance       numeric,
    daily_pnl_sek          numeric,
    cumulative_pnl_sek      numeric,
    trades_taken             integer default 0,
    wins                      integer default 0,
    losses                    integer default 0,
    breakeven                 integer default 0,
    win_rate                   numeric,
    avg_rr                     numeric,
    profit_factor               numeric,
    max_drawdown_pct              numeric,
    signals_generated              integer default 0,
    buy_signals                     integer default 0,
    sell_signals                    integer default 0,
    no_trade_signals                integer default 0,
    created_at                       timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- SYSTEM RUNS (loggar varje körning av GitHub Actions-jobb)
-- ---------------------------------------------------------------------
create table if not exists system_runs (
    id              bigserial primary key,
    run_type        text not null,   -- 'market_data','macro_data','news','signal_engine','paper_trading'
    started_at       timestamptz not null default now(),
    finished_at       timestamptz,
    status             text default 'RUNNING',  -- 'RUNNING','SUCCESS','FAILED','PARTIAL'
    items_processed     integer default 0,
    errors               jsonb,
    log_summary          text
);

-- ---------------------------------------------------------------------
-- ACCOUNT STATE (singelrad, håller koll på virtuellt saldo just nu)
-- ---------------------------------------------------------------------
create table if not exists account_state (
    id                      int primary key default 1,
    balance_sek              numeric not null default 100000,
    starting_balance_sek       numeric not null default 100000,
    updated_at                  timestamptz not null default now(),
    constraint single_row check (id = 1)
);
insert into account_state (id, balance_sek, starting_balance_sek)
    values (1, 100000, 100000)
    on conflict (id) do nothing;

-- ---------------------------------------------------------------------
-- ROW LEVEL SECURITY: enkel setup - inaktiverat för v1 (privat projekt,
-- anropas endast från GitHub Actions med service_role key, aldrig från browsern)
-- ---------------------------------------------------------------------
-- Dashboarden ska läsa via en read-only anon-nyckel med RLS-policies om
-- projektet någonsin blir publikt. För v1 (privat bruk) lämnas RLS av.

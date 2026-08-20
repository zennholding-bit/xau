"""
Master entry point för en full signal-cykel:

1. Hämta senaste marknadsdata för XAU/USD
2. Kör teknisk analys -> technical_score + snapshot
3. Hämta makrodata, nyheter och cross-market-kontext från databasen
   (redan insamlat av separata schemalagda jobb) -> macro/news/fundamental/
   cross_market-scores, med strikt lookahead-skydd (bara data publicerad
   före "nu" räknas)
4. Bygg signal via signal_engine
5. Spara signal + snapshot + länkar till källnyheter/makrohändelser i databasen
6. Kolla öppna paper trades mot senaste candle (SL/TP)
7. Om signalen kvalificerar: öppna ny paper trade
8. Logga hela körningen i system_runs

Körs av GitHub Actions (se .github/workflows/signal_cycle.yml).
"""
from __future__ import annotations
import logging
import uuid
import pandas as pd
from datetime import datetime, timezone

from engine.config.settings import settings
from engine.data_ingestion.market_data.twelvedata_provider import fetch_ohlcv
from engine.analysis.technical.engine import analyze as analyze_technical
from engine.analysis.fundamental.context_builder import build_fundamental_context
from engine.signal_engine.signal_engine import ScoreInputs, build_signal
from engine.paper_trading.broker_interface import get_active_broker
from engine.paper_trading.paper_trading import get_account_balance
from engine.database.client import insert, upsert, log_run_start, log_run_finish

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SYMBOL = settings.PRIMARY_SYMBOL  # default när inget argument ges, se __main__ längst ned


def _generate_signal_uid() -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"SIG-{today}-{uuid.uuid4().hex[:6].upper()}"


def run(symbol: str = SYMBOL) -> dict:
    cfg = settings.SYMBOLS.get(symbol)
    if cfg is None:
        raise ValueError(f"Okänd symbol '{symbol}' - lägg till den i settings.SYMBOLS först.")
    analysis_timeframe = cfg["timeframe"]

    run_id = log_run_start(f"signal_engine:{symbol}")
    errors = []

    try:
        df = fetch_ohlcv(symbol, analysis_timeframe)
        if df.empty or len(df) < 30:
            msg = f"Otillräcklig marknadsdata för {symbol} ({analysis_timeframe}) - avbryter cykeln."
            logger.warning(msg)
            log_run_finish(run_id, "FAILED", errors=[{"error": msg}], log_summary=msg)
            return {"status": "no_data"}

        snapshot = analyze_technical(df, symbol, analysis_timeframe)
        if snapshot is None:
            msg = "Teknisk analys kunde inte köras (för lite data)."
            logger.warning(msg)
            log_run_finish(run_id, "FAILED", errors=[{"error": msg}], log_summary=msg)
            return {"status": "analysis_failed"}

        upsert("technical_snapshots", [snapshot], on_conflict="symbol,timeframe,ts")

        # Hämta makro/nyheter/cross-market från databasen. as_of = nu, vilket
        # garanterar att bara data publicerad FÖRE denna signal räknas in
        # (lookahead-skydd - se context_builder.py).
        # OBS: tolkningen i context_builder.py är kalibrerad för hur makro/
        # nyheter påverkar GULD specifikt - körs därför bara för symboler med
        # use_fundamental_context=True (se settings.SYMBOLS). Andra symboler
        # (t.ex. BTCUSD) får dessa källor markerade som "missing" tills en
        # egen kalibrerad modell finns, så renormaliseringen i signal_engine
        # lägger all vikt på technical_score istället för att felaktigt
        # applicera guld-logik.
        if cfg.get("use_fundamental_context", True):
            as_of = datetime.now(timezone.utc)
            ctx = build_fundamental_context(as_of)
        else:
            as_of = datetime.now(timezone.utc)
            ctx = {
                "fundamental_score": 0.0, "macro_score": 0.0, "news_score": 0.0,
                "cross_market_score": 0.0,
                "data_quality": {"fundamental": "missing", "macro": "missing",
                                  "news": "missing", "cross_market": "missing"},
                "macro_reasoning": "Ej tillämpat - use_fundamental_context=False för denna symbol.",
                "news_reasoning": "Ej tillämpat - use_fundamental_context=False för denna symbol.",
                "cross_market_reasoning": "Ej tillämpat - use_fundamental_context=False för denna symbol.",
                "news_ids": [], "macro_event_ids": [],
            }

        scores = ScoreInputs(
            technical_score=snapshot["technical_score"],
            fundamental_score=ctx["fundamental_score"],
            macro_score=ctx["macro_score"],
            news_score=ctx["news_score"],
            cross_market_score=ctx["cross_market_score"],
            data_quality={"technical": "ok", **ctx["data_quality"]},
        )

        account_balance = get_account_balance()
        signal = build_signal(
            symbol=symbol,
            current_price=snapshot["close"],
            atr=snapshot["atr_14"],
            support=snapshot["support"],
            resistance=snapshot["resistance"],
            scores=scores,
            account_balance=account_balance,
            time_horizon=analysis_timeframe,
            strategy_mode=snapshot.get("strategy_mode", "trend"),
        )
        signal["signal_uid"] = _generate_signal_uid()
        signal["market_conditions_snapshot"] = snapshot
        signal["status"] = "OPEN"
        signal["expires_at"] = None

        # Bygg en fullständig, läsbar motivering som väver ihop teknik + fundamenta
        signal["full_reasoning"] = (
            f"{signal.get('full_reasoning', '')} "
            f"MAKRO: {ctx['macro_reasoning']} "
            f"NYHETER: {ctx['news_reasoning']} "
            f"CROSS-MARKET: {ctx['cross_market_reasoning']}"
        ).strip()

        saved_signal = insert("signals", [signal])
        saved_signal = saved_signal[0] if saved_signal else signal
        signal_db_id = saved_signal.get("id")
        logger.info("Signal skapad: %s %s (confidence=%s, final_score=%s)",
                    saved_signal.get("signal_uid"), saved_signal.get("decision"),
                    saved_signal.get("confidence"), saved_signal.get("final_score"))

        # Länka signalen till sina källor för full auditbarhet ("Varför togs denna trade?")
        if signal_db_id:
            if ctx["news_ids"]:
                insert("signal_news_links", [
                    {"signal_id": signal_db_id, "news_id": nid, "weight": 1.0} for nid in ctx["news_ids"]
                ])
            if ctx["macro_event_ids"]:
                insert("signal_macro_links", [
                    {"signal_id": signal_db_id, "macro_event_id": mid, "weight": 1.0} for mid in ctx["macro_event_ids"]
                ])

        broker = get_active_broker()

        # 1. Kolla öppna trades mot senaste candle
        latest_candle = {
            "high": float(df["high"].iloc[-1]),
            "low": float(df["low"].iloc[-1]),
            "close": float(df["close"].iloc[-1]),
            "ts": pd.Timestamp(df["ts"].iloc[-1]).to_pydatetime(),
        }
        closed_trades = broker.check_open_positions(latest_candle, symbol)
        for t in closed_trades:
            logger.info("Trade stängd: id=%s outcome=%s pnl_sek=%s", t.get("id"), t.get("outcome"), t.get("pnl_sek"))

        # 2. Öppna ny trade om signalen kvalificerar
        new_trade = None
        if saved_signal.get("decision") != "NO_TRADE":
            new_trade = broker.place_order(saved_signal)
            if new_trade:
                logger.info("Ny paper trade öppnad: id=%s %s @ %s", new_trade.get("id"),
                            new_trade.get("direction"), new_trade.get("entry_price"))

        log_run_finish(run_id, "SUCCESS", items_processed=1,
                        log_summary=f"Signal {saved_signal.get('decision')} skapad, "
                                    f"{len(closed_trades)} trades stängda, "
                                    f"{'1 ny trade öppnad' if new_trade else 'ingen ny trade'}.")

        return {"status": "ok", "signal": saved_signal, "closed_trades": closed_trades, "new_trade": new_trade}

    except Exception as e:
        logger.exception("Signal-cykeln kraschade")
        log_run_finish(run_id, "FAILED", errors=[{"error": str(e)}], log_summary=str(e))
        raise


if __name__ == "__main__":
    import sys
    run(sys.argv[1] if len(sys.argv) > 1 else SYMBOL)

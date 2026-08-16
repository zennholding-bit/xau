"""
Master entry point för en full signal-cykel:

1. Hämta senaste marknadsdata för XAU/USD (+ cross-market-symboler)
2. Kör teknisk analys -> technical_score + snapshot
3. (Fundamental/makro/nyheter: markeras "missing" tills de modulerna finns)
4. Bygg signal via signal_engine
5. Spara signal + snapshot i databasen
6. Kolla öppna paper trades mot senaste candle (SL/TP)
7. Om signalen kvalificerar: öppna ny paper trade
8. Logga hela körningen i system_runs

Körs av GitHub Actions (se .github/workflows/signal_cycle.yml).
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone

from engine.config.settings import settings
from engine.data_ingestion.market_data.yfinance_provider import fetch_ohlcv
from engine.analysis.technical.engine import analyze as analyze_technical
from engine.signal_engine.signal_engine import ScoreInputs, build_signal
from engine.paper_trading.broker_interface import get_active_broker
from engine.paper_trading.paper_trading import get_account_balance
from engine.database.client import insert, log_run_start, log_run_finish

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SYMBOL = settings.PRIMARY_SYMBOL  # "XAUUSD"
ANALYSIS_TIMEFRAME = "1h"  # signalgenerering körs på 1h-chart i v1


def _generate_signal_uid() -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"SIG-{today}-{uuid.uuid4().hex[:6].upper()}"


def run() -> dict:
    run_id = log_run_start("signal_engine")
    errors = []

    try:
        df = fetch_ohlcv(SYMBOL, ANALYSIS_TIMEFRAME)
        if df.empty or len(df) < 30:
            msg = f"Otillräcklig marknadsdata för {SYMBOL} ({ANALYSIS_TIMEFRAME}) - avbryter cykeln."
            logger.warning(msg)
            log_run_finish(run_id, "FAILED", errors=[{"error": msg}], log_summary=msg)
            return {"status": "no_data"}

        snapshot = analyze_technical(df, SYMBOL, ANALYSIS_TIMEFRAME)
        if snapshot is None:
            msg = "Teknisk analys kunde inte köras (för lite data)."
            logger.warning(msg)
            log_run_finish(run_id, "FAILED", errors=[{"error": msg}], log_summary=msg)
            return {"status": "analysis_failed"}

        insert("technical_snapshots", [snapshot])

        # Fundamental/makro/nyheter är inte inkopplade ännu i denna version.
        # Markeras explicit som "missing" så signal_engine renormaliserar
        # vikterna och dämpar confidence istället för att gissa ett värde.
        scores = ScoreInputs(
            technical_score=snapshot["technical_score"],
            fundamental_score=0.0,
            macro_score=0.0,
            news_score=0.0,
            cross_market_score=0.0,
            data_quality={
                "technical": "ok",
                "fundamental": "missing",
                "macro": "missing",
                "news": "missing",
                "cross_market": "missing",
            },
        )

        account_balance = get_account_balance()
        signal = build_signal(
            symbol=SYMBOL,
            current_price=snapshot["close"],
            atr=snapshot["atr_14"],
            support=snapshot["support"],
            resistance=snapshot["resistance"],
            scores=scores,
            account_balance=account_balance,
            time_horizon=ANALYSIS_TIMEFRAME,
        )
        signal["signal_uid"] = _generate_signal_uid()
        signal["market_conditions_snapshot"] = snapshot
        signal["status"] = "OPEN"
        # Signalen anses giltig i 4h innan den räknas som expired om ingen trade tagits
        signal["expires_at"] = None

        saved_signal = insert("signals", [signal])
        saved_signal = saved_signal[0] if saved_signal else signal
        logger.info("Signal skapad: %s %s (confidence=%s, final_score=%s)",
                    saved_signal.get("signal_uid"), saved_signal.get("decision"),
                    saved_signal.get("confidence"), saved_signal.get("final_score"))

        broker = get_active_broker()

        # 1. Kolla öppna trades mot senaste candle
        latest_candle = {
            "high": float(df["high"].iloc[-1]),
            "low": float(df["low"].iloc[-1]),
        }
        closed_trades = broker.check_open_positions(latest_candle)
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
    run()

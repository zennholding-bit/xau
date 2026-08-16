"""
Entry point: hämtar marknadsdata för alla symboler/timeframes och
skriver till market_prices i Supabase. Körs av GitHub Actions.

Kraschar aldrig helt systemet - varje symbol/timeframe hanteras isolerat,
fel loggas till system_runs.
"""
import logging
import pandas as pd

from engine.data_ingestion.market_data.stooq_provider import fetch_ohlcv, STOOQ_SYMBOLS
from engine.database.client import upsert, log_run_start, log_run_finish

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# v1 kör endast på dagsdata (se stooq_provider.py-docstringen för varför)
TIMEFRAMES = ["1d"]


def rows_from_df(symbol: str, timeframe: str, df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    # Spara bara de senaste raderna för att hålla batchstorleken rimlig
    df_tail = df.tail(500)
    rows = []
    for _, r in df_tail.iterrows():
        rows.append({
            "symbol": symbol,
            "timeframe": timeframe,
            "ts": r["ts"].isoformat(),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": float(r["volume"]) if pd.notna(r.get("volume")) else None,
            "source": "stooq",
            "quality_score": 1.0,
        })
    return rows


def main() -> None:
    run_id = log_run_start("market_data")
    total = 0
    errors = []

    for symbol in STOOQ_SYMBOLS:
        for tf in TIMEFRAMES:
            try:
                df = fetch_ohlcv(symbol, tf)
                rows = rows_from_df(symbol, tf, df)
                if rows:
                    n = upsert("market_prices", rows, on_conflict="symbol,timeframe,ts,source")
                    total += n
                    logger.info("Sparade %s rader för %s %s", n, symbol, tf)
                else:
                    logger.warning("Ingen data för %s %s - hoppar över", symbol, tf)
                    errors.append({"symbol": symbol, "timeframe": tf, "error": "no_data"})
            except Exception as e:
                logger.exception("Fel vid ingestion av %s %s", symbol, tf)
                errors.append({"symbol": symbol, "timeframe": tf, "error": str(e)})

    status = "SUCCESS" if not errors else ("PARTIAL" if total > 0 else "FAILED")
    log_run_finish(run_id, status, items_processed=total, errors=errors,
                    log_summary=f"{total} rader sparade, {len(errors)} fel")
    logger.info("Klar. Status=%s, totalt=%s, fel=%s", status, total, len(errors))


if __name__ == "__main__":
    main()

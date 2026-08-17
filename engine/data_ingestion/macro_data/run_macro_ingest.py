"""
Entry point: hämtar senaste makrodata från FRED och sparar till macro_events
i Supabase. Körs av GitHub Actions (mer sällan än signal-cykeln, eftersom
makrodata publiceras sällan).
"""
import logging

from engine.data_ingestion.macro_data.fred_provider import fetch_all_series
from engine.database.client import upsert, log_run_start, log_run_finish

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    run_id = log_run_start("macro_data")
    releases = fetch_all_series()

    if not releases:
        log_run_finish(run_id, "FAILED", errors=[{"error": "no_releases"}],
                        log_summary="Ingen makrodata kunde hämtas")
        logger.error("Ingen makrodata kunde hämtas")
        return

    n = upsert("macro_events", releases, on_conflict="event_code,release_time,source")
    status = "SUCCESS" if n == len(releases) else "PARTIAL"
    log_run_finish(run_id, status, items_processed=n,
                    log_summary=f"{n} makrohändelser sparade av {len(releases)} hämtade")
    logger.info("Klar. %s av %s makroserier sparade.", n, len(releases))


if __name__ == "__main__":
    main()

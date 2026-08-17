"""
Entry point: hämtar nyheter från RSS-flöden, dedupar/klustrar dem och
sparar till news_articles i Supabase. Körs av GitHub Actions.
"""
import logging

from engine.data_ingestion.news.rss_provider import fetch_all_news
from engine.data_ingestion.news.dedup import assign_clusters
from engine.database.client import upsert, log_run_start, log_run_finish

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    run_id = log_run_start("news")
    articles = fetch_all_news()

    if not articles:
        log_run_finish(run_id, "FAILED", errors=[{"error": "no_articles"}],
                        log_summary="Inga nyhetsartiklar kunde hämtas")
        logger.error("Inga nyhetsartiklar kunde hämtas")
        return

    articles.sort(key=lambda a: a["published_at"])
    articles = assign_clusters(articles)

    n = upsert("news_articles", articles, on_conflict="source,external_id")
    log_run_finish(run_id, "SUCCESS", items_processed=n,
                    log_summary=f"{n} nyhetsartiklar sparade")
    logger.info("Klar. %s artiklar sparade.", n)


if __name__ == "__main__":
    main()

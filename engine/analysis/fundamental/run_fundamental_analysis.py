"""
Entry point: analyserar nyheter som ännu inte har en news_analysis-rad,
och sparar det regelbaserade resultatet. Körs av GitHub Actions efter
news-ingestion.
"""
import logging

from engine.data_ingestion.news.rss_provider import categorize, compute_importance
from engine.analysis.fundamental.news_scoring import score_article
from engine.database.client import get_db, insert, log_run_start, log_run_finish

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ANALYZER_VERSION = "rule_based_v1"


def get_unanalyzed_articles(limit: int = 200) -> list[dict]:
    """Hämtar de senaste artiklarna som ännu inte analyserats av denna analyzer-version."""
    db = get_db()
    already_analyzed = db.table("news_analysis") \
        .select("news_id") \
        .eq("analyzer_version", ANALYZER_VERSION) \
        .execute()
    analyzed_ids = {row["news_id"] for row in already_analyzed.data} if already_analyzed.data else set()

    recent = db.table("news_articles") \
        .select("*") \
        .order("published_at", desc=True) \
        .limit(limit) \
        .execute()

    return [a for a in (recent.data or []) if a["id"] not in analyzed_ids]


def main() -> None:
    run_id = log_run_start("fundamental_analysis")
    articles = get_unanalyzed_articles()

    if not articles:
        log_run_finish(run_id, "SUCCESS", items_processed=0,
                        log_summary="Inga nya artiklar att analysera")
        logger.info("Inga nya artiklar att analysera.")
        return

    rows = []
    for article in articles:
        full_text = f"{article.get('headline', '')} {article.get('summary', '')}"
        categories = categorize(full_text)
        importance = compute_importance(categories, article.get("source", ""))
        result = score_article(categories, importance)

        rows.append({
            "news_id": article["id"],
            "cluster_id": article.get("cluster_id"),
            "analyzer_version": ANALYZER_VERSION,
            "importance_score": importance,
            "sentiment": "positive" if result.xau_score > 0.1 else ("negative" if result.xau_score < -0.1 else "neutral"),
            "xau_direction": result.xau_direction,
            "xau_score": round(result.xau_score, 4),
            "usd_direction": "bearish" if result.xau_score > 0.1 else ("bullish" if result.xau_score < -0.1 else "neutral"),
            "yield_direction": None,
            "oil_direction": None,
            "risk_sentiment": result.risk_sentiment,
            "novelty_score": 1.0,  # v1: dedup hanteras via cluster_id, inte gradvis novelty
            "reasoning_summary": result.reasoning_summary,
            "conflicting_factors": result.conflicting_factors,
            "time_horizon_scores": {
                "15m": round(result.xau_score * 0.6, 3),
                "1h": round(result.xau_score * 0.8, 3),
                "4h": round(result.xau_score, 3),
                "24h": round(result.xau_score * 0.7, 3),
            },
            "raw_output": {
                "categories": categories,
                "importance": importance,
                "headline": article.get("headline"),
            },
        })

    saved = insert("news_analysis", rows)
    log_run_finish(run_id, "SUCCESS", items_processed=len(saved),
                    log_summary=f"{len(saved)} artiklar analyserade (regelbaserat)")
    logger.info("Klar. %s artiklar analyserade.", len(saved))


if __name__ == "__main__":
    main()

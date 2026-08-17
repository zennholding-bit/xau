"""
Hämtar redan insamlad och analyserad makro-/nyhets-/cross-market-data från
databasen och kombinerar den till scores redo för signal_engine.

VIKTIGT - LOOKAHEAD-SKYDD: alla frågor filtrerar strikt på
release_time <= now() / published_at <= now(). En makrosiffra publicerad
14:30 får aldrig påverka en signal skapad 14:29, exakt som specen kräver.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone

from engine.database.client import get_db
from engine.analysis.fundamental.macro_scoring import score_macro_events
from engine.analysis.fundamental.news_scoring import aggregate_news_scores
from engine.analysis.technical.cross_market import CrossMarketInput, score_cross_market

logger = logging.getLogger(__name__)

MACRO_LOOKBACK_DAYS = 45     # makrodata är sällsynt - vidare fönster
NEWS_LOOKBACK_HOURS = 24     # nyheter är färskvara
CROSS_MARKET_LOOKBACK_DAYS = 20  # för att räkna trend (senaste vs ~20 dagar sedan)


def get_macro_context(as_of: datetime) -> tuple[float, str, list[int]]:
    """Returnerar (macro_score, reasoning, macro_event_ids) för senaste publiceringen av varje serie."""
    db = get_db()
    cutoff = (as_of - timedelta(days=MACRO_LOOKBACK_DAYS)).isoformat()

    res = db.table("macro_events") \
        .select("*") \
        .lte("release_time", as_of.isoformat()) \
        .gte("release_time", cutoff) \
        .order("release_time", desc=True) \
        .execute()

    events = res.data or []
    if not events:
        return 0.0, "Ingen makrodata tillgänglig i tidsfönstret.", []

    # Ta bara senaste publiceringen per event_code
    latest_per_code: dict[str, dict] = {}
    for e in events:
        code = e["event_code"]
        if code not in latest_per_code:
            latest_per_code[code] = e

    score, reasoning, _ = score_macro_events(list(latest_per_code.values()))
    event_ids = [e["id"] for e in latest_per_code.values()]
    return score, reasoning, event_ids


def get_news_context(as_of: datetime) -> tuple[float, str, list[int]]:
    """Returnerar (news_score, reasoning, news_ids) för relevanta nyheter i tidsfönstret."""
    db = get_db()
    cutoff = (as_of - timedelta(hours=NEWS_LOOKBACK_HOURS)).isoformat()

    articles_res = db.table("news_articles") \
        .select("id, headline, published_at, cluster_id") \
        .lte("published_at", as_of.isoformat()) \
        .gte("published_at", cutoff) \
        .execute()
    articles = {a["id"]: a for a in (articles_res.data or [])}

    if not articles:
        return 0.0, "Inga nyheter i tidsfönstret.", []

    analysis_res = db.table("news_analysis") \
        .select("*") \
        .in_("news_id", list(articles.keys())) \
        .eq("analyzer_version", "rule_based_v1") \
        .execute()
    analyses = analysis_res.data or []

    if not analyses:
        return 0.0, "Nyheter finns men är inte analyserade ännu.", []

    # Dedup: en artikel per cluster_id (undvik att samma händelse räknas flera gånger)
    seen_clusters: set[str] = set()
    scored_articles = []
    news_ids = []
    for a in analyses:
        article = articles.get(a["news_id"])
        if not article:
            continue
        cluster_id = article.get("cluster_id")
        if cluster_id in seen_clusters:
            continue
        seen_clusters.add(cluster_id)
        scored_articles.append({
            "xau_score": a["xau_score"],
            "importance_score": a["importance_score"],
            "headline": article["headline"],
        })
        news_ids.append(a["news_id"])

    score, reasoning = aggregate_news_scores(scored_articles)
    return score, reasoning, news_ids


def get_cross_market_context(as_of: datetime) -> tuple[float, str]:
    """Returnerar (cross_market_score, reasoning) baserat på DXY/US10Y/WTI-trend."""
    db = get_db()
    cutoff = (as_of - timedelta(days=CROSS_MARKET_LOOKBACK_DAYS)).isoformat()

    inputs = []
    for symbol in ("DXY", "US10Y", "WTI"):
        res = db.table("market_prices") \
            .select("close, ts") \
            .eq("symbol", symbol).eq("timeframe", "1d") \
            .lte("ts", as_of.isoformat()) \
            .order("ts", desc=True) \
            .limit(1) \
            .execute()
        latest = res.data[0] if res.data else None

        prior_res = db.table("market_prices") \
            .select("close, ts") \
            .eq("symbol", symbol).eq("timeframe", "1d") \
            .lte("ts", cutoff) \
            .order("ts", desc=True) \
            .limit(1) \
            .execute()
        prior = prior_res.data[0] if prior_res.data else None

        inputs.append(CrossMarketInput(
            symbol=symbol,
            latest_close=latest["close"] if latest else None,
            prior_close=prior["close"] if prior else None,
        ))

    return score_cross_market(inputs)


def build_fundamental_context(as_of: datetime | None = None) -> dict:
    """
    Samlar allt till ett dict redo att användas av run_signal_cycle.py.
    Returnerar scores + reasoning + de ID:n som ska länkas till signalen
    (signal_news_links / signal_macro_links) för full auditbarhet.
    """
    as_of = as_of or datetime.now(timezone.utc)

    macro_score, macro_reasoning, macro_event_ids = get_macro_context(as_of)
    news_score, news_reasoning, news_ids = get_news_context(as_of)
    cross_market_score, cross_market_reasoning = get_cross_market_context(as_of)

    # fundamental_score: sammanvägd "stora bilden"-tolkning av makro + nyheter,
    # motsvarande specens "AI-baserad fundamental analys"-lager.
    fundamental_score = 0.6 * macro_score + 0.4 * news_score
    fundamental_score = max(-1.0, min(1.0, fundamental_score))

    data_quality = {
        "macro": "ok" if macro_event_ids else "missing",
        "news": "ok" if news_ids else "missing",
        "cross_market": "ok" if cross_market_reasoning != "Ingen cross-market-data tillgänglig." else "missing",
        "fundamental": "ok" if (macro_event_ids or news_ids) else "missing",
    }

    return {
        "macro_score": macro_score,
        "macro_reasoning": macro_reasoning,
        "macro_event_ids": macro_event_ids,
        "news_score": news_score,
        "news_reasoning": news_reasoning,
        "news_ids": news_ids,
        "cross_market_score": cross_market_score,
        "cross_market_reasoning": cross_market_reasoning,
        "fundamental_score": fundamental_score,
        "data_quality": data_quality,
    }

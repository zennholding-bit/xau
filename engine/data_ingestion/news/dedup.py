"""
Dedup/klustring: undviker att samma händelse från flera källor räknas som
flera separata nyheter (spec-krav).

v1-strategi: normaliserad rubrik-hash (exakt likhet efter normalisering)
plus enkel ordöverlappning (Jaccard-likhet) mot nyligen sedda rubriker
inom ett kort tidsfönster. Detta fångar upp exakta dubbletter och nästan
identiska rubriker (t.ex. "Fed hints at rate cut" vs "Fed hints at rate cuts")
utan att kräva en tung NLP-modell.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

from engine.data_ingestion.news.rss_provider import _normalize_headline

DEDUP_WINDOW_HOURS = 12
JACCARD_THRESHOLD = 0.5


def _word_set(text: str) -> set[str]:
    return set(_normalize_headline(text).split())


def jaccard_similarity(a: str, b: str) -> float:
    set_a, set_b = _word_set(a), _word_set(b)
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


def assign_clusters(articles: list[dict]) -> list[dict]:
    """
    Går igenom en lista artiklar (redan sorterad efter published_at) och
    tilldelar samma cluster_id till artiklar som är nästan identiska och
    publicerade inom DEDUP_WINDOW_HOURS av varandra. Muterar och returnerar
    listan med uppdaterade cluster_id-fält.
    """
    clusters: list[dict] = []  # [{"cluster_id": str, "headline": str, "published_at": datetime}]

    for article in articles:
        headline = article["headline"]
        published_at = article["published_at"]
        if isinstance(published_at, str):
            published_at = datetime.fromisoformat(published_at.replace("Z", "+00:00"))

        matched_cluster = None
        for cluster in clusters:
            time_diff = abs((published_at - cluster["published_at"]).total_seconds() / 3600)
            if time_diff > DEDUP_WINDOW_HOURS:
                continue
            if jaccard_similarity(headline, cluster["headline"]) >= JACCARD_THRESHOLD:
                matched_cluster = cluster
                break

        if matched_cluster:
            article["cluster_id"] = matched_cluster["cluster_id"]
        else:
            clusters.append({
                "cluster_id": article["cluster_id"],
                "headline": headline,
                "published_at": published_at,
            })

    return articles

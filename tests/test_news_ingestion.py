from engine.data_ingestion.news.rss_provider import (
    categorize, extract_countries, compute_headline_hash, compute_importance,
)
from engine.data_ingestion.news.dedup import jaccard_similarity, assign_clusters
from datetime import datetime, timezone, timedelta


def test_categorize_detects_central_bank():
    categories = categorize("Federal Reserve signals possible rate hike next month")
    assert "central_bank" in categories


def test_categorize_detects_geopolitics():
    categories = categorize("Tensions escalate as Iran threatens military response")
    assert "geopolitics" in categories


def test_categorize_falls_back_to_general():
    categories = categorize("Local bakery wins award for best bread")
    assert categories == ["general"]


def test_extract_countries_finds_multiple():
    countries = extract_countries("China and Russia sign new trade agreement")
    assert "CN" in countries
    assert "RU" in countries


def test_headline_hash_is_consistent():
    h1 = compute_headline_hash("Fed Raises Interest Rates by 25bps")
    h2 = compute_headline_hash("fed raises interest rates by 25bps")  # olika skiftläge
    assert h1 == h2  # ska normaliseras till samma hash


def test_headline_hash_differs_for_different_content():
    h1 = compute_headline_hash("Fed raises rates")
    h2 = compute_headline_hash("Fed cuts rates")
    assert h1 != h2


def test_importance_higher_for_central_bank_than_general():
    imp_cb = compute_importance(["central_bank"], "Test Source")
    imp_general = compute_importance(["general"], "Test Source")
    assert imp_cb > imp_general


def test_jaccard_similarity_identical_headlines():
    sim = jaccard_similarity("Fed raises rates by 25bps", "Fed raises rates by 25bps")
    assert sim == 1.0


def test_jaccard_similarity_unrelated_headlines():
    sim = jaccard_similarity("Fed raises interest rates today", "Local weather forecast sunny")
    assert sim < 0.3


def test_assign_clusters_groups_similar_headlines():
    now = datetime.now(timezone.utc)
    articles = [
        {"headline": "Fed raises interest rates by 25 basis points", "published_at": now, "cluster_id": "a"},
        {"headline": "Fed raises interest rates by 25bps", "published_at": now + timedelta(minutes=5), "cluster_id": "b"},
    ]
    result = assign_clusters(articles)
    assert result[0]["cluster_id"] == result[1]["cluster_id"]  # ska klustras ihop


def test_assign_clusters_keeps_unrelated_separate():
    now = datetime.now(timezone.utc)
    articles = [
        {"headline": "Fed raises interest rates", "published_at": now, "cluster_id": "a"},
        {"headline": "Oil prices drop sharply today", "published_at": now, "cluster_id": "b"},
    ]
    result = assign_clusters(articles)
    assert result[0]["cluster_id"] != result[1]["cluster_id"]


def test_assign_clusters_respects_time_window():
    now = datetime.now(timezone.utc)
    articles = [
        {"headline": "Fed raises interest rates by 25bps", "published_at": now, "cluster_id": "a"},
        {"headline": "Fed raises interest rates by 25bps", "published_at": now + timedelta(hours=24), "cluster_id": "b"},
    ]
    result = assign_clusters(articles)
    assert result[0]["cluster_id"] != result[1]["cluster_id"]  # för långt isär i tid

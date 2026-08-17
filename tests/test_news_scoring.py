from engine.analysis.fundamental.news_scoring import score_article, aggregate_news_scores


def test_geopolitics_is_bullish_for_gold():
    result = score_article(["geopolitics"], importance=90)
    assert result.xau_score > 0
    assert result.xau_direction == "bullish"
    assert result.risk_sentiment == "risk_off"


def test_financial_stability_is_strongly_bullish():
    result = score_article(["financial_stability"], importance=90)
    assert result.xau_score > 0.3  # ska vara en av de starkaste kategorierna


def test_employment_is_slightly_bearish():
    result = score_article(["employment"], importance=80)
    assert result.xau_score < 0


def test_general_category_is_near_neutral():
    result = score_article(["general"], importance=30)
    assert abs(result.xau_score) < 0.15


def test_low_importance_dampens_score():
    high_importance = score_article(["geopolitics"], importance=100)
    low_importance = score_article(["geopolitics"], importance=10)
    assert abs(low_importance.xau_score) < abs(high_importance.xau_score)


def test_empty_categories_defaults_to_general():
    result = score_article([], importance=50)
    assert result.xau_direction in ("neutral", "bullish", "bearish")


def test_aggregate_weights_by_importance():
    articles = [
        {"xau_score": 0.8, "importance_score": 90, "headline": "Big news"},
        {"xau_score": -0.1, "importance_score": 10, "headline": "Minor news"},
    ]
    score, summary = aggregate_news_scores(articles)
    # Det viktiga articleset ska dominera
    assert score > 0.5
    assert "Big news" in summary


def test_aggregate_empty_list_returns_neutral():
    score, summary = aggregate_news_scores([])
    assert score == 0.0

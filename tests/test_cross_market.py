from engine.analysis.technical.cross_market import CrossMarketInput, score_cross_market


def test_dxy_up_is_bearish_for_gold():
    inputs = [CrossMarketInput(symbol="DXY", latest_close=105.0, prior_close=100.0)]
    score, summary = score_cross_market(inputs)
    assert score < 0


def test_us10y_up_is_bearish_for_gold():
    inputs = [CrossMarketInput(symbol="US10Y", latest_close=4.5, prior_close=4.0)]
    score, summary = score_cross_market(inputs)
    assert score < 0


def test_wti_up_is_bullish_for_gold():
    inputs = [CrossMarketInput(symbol="WTI", latest_close=90.0, prior_close=80.0)]
    score, summary = score_cross_market(inputs)
    assert score > 0


def test_missing_data_is_skipped_not_crashed():
    inputs = [
        CrossMarketInput(symbol="DXY", latest_close=None, prior_close=None),
        CrossMarketInput(symbol="US10Y", latest_close=4.5, prior_close=4.0),
    ]
    score, summary = score_cross_market(inputs)
    assert score < 0  # bara US10Y bidrar, men det ska fortfarande fungera


def test_no_data_at_all_returns_neutral():
    inputs = [CrossMarketInput(symbol="DXY", latest_close=None, prior_close=None)]
    score, summary = score_cross_market(inputs)
    assert score == 0.0


def test_score_bounded():
    inputs = [CrossMarketInput(symbol="DXY", latest_close=200.0, prior_close=50.0)]  # extrem rörelse
    score, summary = score_cross_market(inputs)
    assert -1.0 <= score <= 1.0

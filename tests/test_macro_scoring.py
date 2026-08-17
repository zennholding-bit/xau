from engine.analysis.fundamental.macro_scoring import score_single_event, score_macro_events


def test_higher_core_cpi_is_bearish_for_gold():
    event = {"event_code": "US_CORE_CPI", "actual": 3.5, "previous": 3.0}
    result = score_single_event(event)
    assert result is not None
    assert result.score < 0  # högre kärninflation -> bearish enligt vår modell
    assert result.direction == "bearish"


def test_higher_unemployment_is_bullish_for_gold():
    event = {"event_code": "US_UNEMPLOYMENT_RATE", "actual": 4.5, "previous": 4.0}
    result = score_single_event(event)
    assert result is not None
    assert result.score > 0  # högre arbetslöshet -> duvaktigt -> bullish guld
    assert result.direction == "bullish"


def test_rate_hike_is_bearish_for_gold():
    event = {"event_code": "FED_FUNDS_RATE", "actual": 5.5, "previous": 5.25}
    result = score_single_event(event)
    assert result is not None
    assert result.score < 0


def test_unknown_event_code_returns_none():
    event = {"event_code": "SOME_UNKNOWN_SERIES", "actual": 1.0, "previous": 0.5}
    assert score_single_event(event) is None


def test_missing_values_returns_none():
    event = {"event_code": "US_CPI", "actual": None, "previous": 3.0}
    assert score_single_event(event) is None


def test_combined_score_within_bounds():
    events = [
        {"event_code": "US_CORE_CPI", "actual": 4.0, "previous": 3.0},
        {"event_code": "FED_FUNDS_RATE", "actual": 5.5, "previous": 5.25},
        {"event_code": "US_UNEMPLOYMENT_RATE", "actual": 3.5, "previous": 4.0},
    ]
    score, summary, results = score_macro_events(events)
    assert -1.0 <= score <= 1.0
    assert len(results) == 3
    assert len(summary) > 0


def test_empty_events_returns_neutral():
    score, summary, results = score_macro_events([])
    assert score == 0.0
    assert results == []

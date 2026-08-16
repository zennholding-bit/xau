from engine.signal_engine.signal_engine import (
    ScoreInputs, calculate_final_score, decide, calculate_confidence, build_signal,
)


def test_decide_buy_above_threshold():
    assert decide(0.70) == "BUY"


def test_decide_sell_below_threshold():
    assert decide(-0.70) == "SELL"


def test_decide_no_trade_in_neutral_zone():
    assert decide(0.10) == "NO_TRADE"
    assert decide(-0.10) == "NO_TRADE"


def test_final_score_renormalizes_when_sources_missing():
    scores = ScoreInputs(
        technical_score=0.8,
        fundamental_score=0.0,
        macro_score=0.0,
        news_score=0.0,
        cross_market_score=0.0,
        data_quality={"fundamental": "missing", "macro": "missing", "news": "missing", "cross_market": "missing"},
    )
    final, weights = calculate_final_score(scores)
    # Med allt utom technical borttaget ska technical få 100% vikt
    assert weights == {"technical": 1.0}
    assert abs(final - 0.8) < 1e-6


def test_confidence_lower_when_data_missing():
    full_quality = {"technical": "ok", "fundamental": "ok", "macro": "ok", "news": "ok", "cross_market": "ok"}
    missing_quality = {"technical": "ok", "fundamental": "missing", "macro": "missing", "news": "missing", "cross_market": "missing"}
    full_weights = {"technical": 0.4, "fundamental": 0.2, "macro": 0.15, "news": 0.15, "cross_market": 0.1}
    missing_weights = {"technical": 1.0}

    c_full = calculate_confidence(0.8, full_quality, full_weights)
    c_missing = calculate_confidence(0.8, missing_quality, missing_weights)
    assert c_missing < c_full  # mindre datatäckning -> lägre confidence


def test_build_signal_no_trade_has_no_entry():
    scores = ScoreInputs(technical_score=0.1, data_quality={"fundamental": "missing", "macro": "missing", "news": "missing", "cross_market": "missing"})
    signal = build_signal("XAUUSD", current_price=2000.0, atr=10.0, support=1980.0,
                           resistance=2020.0, scores=scores, account_balance=100_000)
    assert signal["decision"] == "NO_TRADE"
    assert signal["entry"] is None


def test_build_signal_buy_has_valid_sl_tp():
    scores = ScoreInputs(technical_score=0.9, data_quality={"fundamental": "missing", "macro": "missing", "news": "missing", "cross_market": "missing"})
    signal = build_signal("XAUUSD", current_price=2000.0, atr=10.0, support=1980.0,
                           resistance=2050.0, scores=scores, account_balance=100_000)
    assert signal["decision"] == "BUY"
    assert signal["stop_loss"] < signal["entry"] < signal["take_profit"]
    assert signal["risk_reward"] > 0

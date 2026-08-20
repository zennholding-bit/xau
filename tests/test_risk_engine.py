from engine.risk_engine.risk_engine import atr_based_sltp, structure_based_sltp, calculate_position_size


def test_atr_based_sltp_buy_direction():
    r = atr_based_sltp(entry=2000.0, direction="BUY", atr=10.0, sl_atr_mult=1.5, rr_target=2.0)
    assert r.stop_loss < 2000.0
    assert r.take_profit > 2000.0
    assert abs(r.risk_reward - 2.0) < 1e-6


def test_atr_based_sltp_sell_direction():
    r = atr_based_sltp(entry=2000.0, direction="SELL", atr=10.0, sl_atr_mult=1.5, rr_target=2.0)
    assert r.stop_loss > 2000.0
    assert r.take_profit < 2000.0


def test_structure_based_sltp_falls_back_without_support():
    r = structure_based_sltp(entry=2000.0, direction="BUY", support=None, resistance=2050.0, atr=10.0)
    assert r.sl_model == "atr_multiple"  # fallback


def test_structure_based_sltp_uses_structure_when_available():
    r = structure_based_sltp(entry=2000.0, direction="BUY", support=1980.0, resistance=2060.0, atr=10.0)
    assert r.stop_loss < 1980.0  # under support med buffert
    assert r.sl_model == "structure_based"


def test_position_sizing_scales_with_risk_distance():
    small_risk = calculate_position_size(account_balance=100_000, risk_pct=0.5, entry=2000.0, stop_loss=1995.0)
    large_risk = calculate_position_size(account_balance=100_000, risk_pct=0.5, entry=2000.0, stop_loss=1980.0)
    # Mindre risk-distans (5) -> större position än vid större risk-distans (20)
    assert small_risk["size"] > large_risk["size"]
    assert small_risk["risk_amount_sek"] == 500.0  # 0.5% av 100 000


def test_position_sizing_zero_when_no_risk_distance():
    r = calculate_position_size(account_balance=100_000, risk_pct=0.5, entry=2000.0, stop_loss=2000.0)
    assert r["size"] == 0.0

"""
Risk Engine - beräknar Stop Loss, Take Profit och position size.

SL/TP baseras ALDRIG på fasta procenttal - alltid på ATR (volatilitet) och
struktur (support/resistance), enligt spec. Flera modeller stöds så de kan
jämföras mot varandra i backtesting.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class SLTPResult:
    stop_loss: float
    take_profit: float
    risk_reward: float
    sl_model: str
    tp_model: str


def atr_based_sltp(entry: float, direction: str, atr: float,
                    sl_atr_mult: float = 1.5, rr_target: float = 2.0) -> SLTPResult:
    """
    Enklaste och mest robusta modellen: SL = entry -/+ (ATR * multiplier),
    TP sätts för att ge önskat risk/reward.
    """
    risk_distance = atr * sl_atr_mult
    if direction == "BUY":
        sl = entry - risk_distance
        tp = entry + risk_distance * rr_target
    else:  # SELL
        sl = entry + risk_distance
        tp = entry - risk_distance * rr_target
    return SLTPResult(sl, tp, rr_target, sl_model="atr_multiple", tp_model="atr_rr_target")


def structure_based_sltp(entry: float, direction: str, support: float | None,
                          resistance: float | None, atr: float,
                          min_rr: float = 1.5) -> SLTPResult:
    """
    Placerar SL precis bortom senaste support/resistance (+ liten ATR-buffert)
    och TP mot nästa strukturella nivå, med minimikrav på risk/reward.
    Faller tillbaka till ATR-modellen om support/resistance saknas.
    """
    buffer = atr * 0.25
    if direction == "BUY":
        if support is None:
            return atr_based_sltp(entry, direction, atr)
        sl = support - buffer
        risk = entry - sl
        tp = entry + max(risk * min_rr, (resistance - entry) if resistance else risk * min_rr)
    else:
        if resistance is None:
            return atr_based_sltp(entry, direction, atr)
        sl = resistance + buffer
        risk = sl - entry
        tp = entry - max(risk * min_rr, (entry - support) if support else risk * min_rr)

    risk = abs(entry - sl)
    reward = abs(tp - entry)
    rr = reward / risk if risk > 0 else 0.0
    return SLTPResult(sl, tp, rr, sl_model="structure_based", tp_model="next_structure_level")


def calculate_position_size(account_balance: float, risk_pct: float,
                             entry: float, stop_loss: float) -> dict:
    """
    Position sizing baserat på fast risk % av kontot.
    Generisk över symboler - 'size' är i den enhet som är naturlig för
    instrumentet (oz för XAU/USD, BTC för BTC/USD, etc - se settings.SYMBOLS
    unit_label per symbol).
    """
    risk_amount_sek = account_balance * (risk_pct / 100)
    risk_per_unit = abs(entry - stop_loss)
    if risk_per_unit <= 0:
        return {"size": 0.0, "risk_amount_sek": 0.0}
    size = risk_amount_sek / risk_per_unit
    return {"size": round(size, 6), "risk_amount_sek": round(risk_amount_sek, 2)}

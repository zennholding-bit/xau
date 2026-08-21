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


def split_into_tp_legs(entry: float, direction: str, stop_loss: float, total_lots: float,
                        tp_legs: list[dict], contract_size: float, lot_step: float,
                        min_lot: float, fallback_take_profit: float) -> list[dict]:
    """
    Delar en position i flera 'ben' med olika TP-nivåer (TP1/TP2/TP3-stil)
    för delvis vinsthemtagning, istället för allt-eller-inget vid en enda TP.
    Varje ben får sin egen storlek (lots) baserat på 'fraction' i tp_legs.

    Om positionen är för liten för att delas (något ben skulle bli mindre än
    min_lot efter avrundning) faller den tillbaka till EN enda TP-nivå
    (fallback_take_profit, den ursprungliga rr_target-nivån) - annars skulle
    små positioner kunna generera ben på 0 lot, vilket vore meningslöst.
    """
    risk = abs(entry - stop_loss)
    sign = 1 if direction == "BUY" else -1

    legs = []
    for leg_cfg in tp_legs:
        leg_lots_raw = total_lots * leg_cfg["fraction"]
        leg_rounded = round(leg_lots_raw / lot_step) * lot_step
        legs.append({
            "level_r": leg_cfg["level_r"],
            "take_profit": round(entry + sign * risk * leg_cfg["level_r"], 2),
            "lots": round(leg_rounded, 2),
        })

    if any(leg["lots"] < min_lot for leg in legs) or len(legs) == 0:
        # Fallback: en enda TP-nivå med hela positionen, som innan
        single_lots = round(total_lots / lot_step) * lot_step
        return [{
            "level_r": None,
            "take_profit": round(fallback_take_profit, 2),
            "lots": round(single_lots, 2),
        }]

    return legs


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
                          min_rr: float = 1.5, max_rr: float = 2.0) -> SLTPResult:
    """
    Placerar SL precis bortom senaste support/resistance (+ liten ATR-buffert)
    och TP mot nästa strukturella nivå, med minimikrav på risk/reward (min_rr)
    OCH ett tak (max_rr) - annars kan TP skjutas väldigt långt bort om nästa
    verkliga motstånd/stöd råkar ligga fjärran, vilket gjorde mål orealistiskt
    avlägsna och sällan nådda (upptäckt 2026-08-20: en trade fick RR 2.68 fast
    rr_target var satt till 1.5, eftersom max()-logiken saknade ett tak).
    Faller tillbaka till ATR-modellen om support/resistance saknas.
    """
    buffer = atr * 0.25
    if direction == "BUY":
        if support is None:
            return atr_based_sltp(entry, direction, atr)
        sl = support - buffer
        risk = entry - sl
        structure_target = (resistance - entry) if resistance else risk * min_rr
        target_distance = max(risk * min_rr, structure_target)
        target_distance = min(target_distance, risk * max_rr)
        tp = entry + target_distance
    else:
        if resistance is None:
            return atr_based_sltp(entry, direction, atr)
        sl = resistance + buffer
        risk = sl - entry
        structure_target = (entry - support) if support else risk * min_rr
        target_distance = max(risk * min_rr, structure_target)
        target_distance = min(target_distance, risk * max_rr)
        tp = entry - target_distance

    risk = abs(entry - sl)
    reward = abs(tp - entry)
    rr = reward / risk if risk > 0 else 0.0
    return SLTPResult(sl, tp, rr, sl_model="structure_based", tp_model="next_structure_level")


def clamp_tp_to_pip_range(entry: float, direction: str, take_profit: float, stop_loss: float,
                           pip_size: float, min_tp_pips: float, max_tp_pips: float) -> SLTPResult:
    """
    Tvingar TP-avståndet (oavsett vilken modell som räknade fram det) att
    ligga inom [min_tp_pips, max_tp_pips] från entry, i faktiska pips - INTE
    bara ett RR-förhållande. Upptäckt 2026-08-20: max_rr-taket i
    structure_based_sltp räckte inte ensamt, eftersom SL i sig kan vara brett
    (t.ex. 617 pips om stöd/motstånd råkar ligga långt bort) - då gav även
    ett RR-tak på 2.0 fortfarande ett mål på över 1000 pips. Det här sätter
    en direkt, absolut gräns i pips istället, oavsett hur SL beräknades.
    """
    current_distance = abs(take_profit - entry)
    min_distance = min_tp_pips * pip_size
    max_distance = max_tp_pips * pip_size
    clamped_distance = min(max(current_distance, min_distance), max_distance)

    if clamped_distance == current_distance:
        risk = abs(entry - stop_loss)
        rr = clamped_distance / risk if risk > 0 else 0.0
        return SLTPResult(stop_loss, take_profit, rr, sl_model="unchanged", tp_model="unchanged")

    sign = 1 if direction == "BUY" else -1
    new_tp = entry + sign * clamped_distance
    risk = abs(entry - stop_loss)
    rr = clamped_distance / risk if risk > 0 else 0.0
    return SLTPResult(stop_loss, new_tp, rr, sl_model="unchanged", tp_model="pip_clamped")


def round_to_lot_size(size_units: float, contract_size: float, lot_step: float,
                       min_lot: float, max_lot: float) -> dict:
    """
    Konverterar en råstorlek (t.ex. oz) till lot, avrundar till närmaste
    lot_step (MT5 tillåter oftast bara steg om 0.01), och klipper till
    [min_lot, max_lot]. Utan detta kan systemet föreslå storlekar som inte
    går att lägga på riktigt hos en broker - för litet, eller i ett steg
    som inte accepteras.
    """
    raw_lots = size_units / contract_size
    rounded_lots = round(raw_lots / lot_step) * lot_step
    clamped_lots = min(max(rounded_lots, min_lot), max_lot)
    clamped_lots = round(clamped_lots, 2)
    return {"lots": clamped_lots, "size_units": clamped_lots * contract_size}


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


def calculate_required_margin(size: float, entry_price: float, leverage: float) -> float:
    """Marginal som skulle krävas hos brokern för att öppna en position av
    given storlek, givet hävstång. Samma prisenhet som resten av systemet
    använder för 'SEK' (dvs ingen FX-konvertering görs - konsekvent med hur
    risk_amount_sek redan räknas i entry_price:s egen valuta)."""
    if leverage <= 0:
        return float("inf")
    return (size * entry_price) / leverage


def cap_size_by_margin(size: float, entry_price: float, leverage: float,
                        account_balance: float, max_margin_pct: float) -> dict:
    """
    Skalar ner en risk-baserad positionsstorlek om den skulle kräva mer
    marginal än vad kontot rimligen bör binda upp i en enda trade (annars
    kan systemet föreslå positioner som vore omöjliga att faktiskt öppna
    hos en riktig broker med den hävstången, eller som omedelbart skulle
    äta upp för stor andel av ett litet konto).

    Returnerar {"size": justerad storlek, "margin_required": faktisk
    marginal efter ev. neddragning, "capped": bool om storleken justerades}.
    """
    margin_budget = account_balance * max_margin_pct
    margin_required = calculate_required_margin(size, entry_price, leverage)

    if margin_required <= margin_budget or margin_required <= 0:
        return {"size": size, "margin_required": round(margin_required, 2), "capped": False}

    scale = margin_budget / margin_required
    adjusted_size = size * scale
    adjusted_margin = calculate_required_margin(adjusted_size, entry_price, leverage)
    return {"size": round(adjusted_size, 6), "margin_required": round(adjusted_margin, 2), "capped": True}

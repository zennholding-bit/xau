"""
Signal Engine - kombinerar tekniskt score, fundamentalt score, makro-score,
nyhets-score och cross-market-score till ett final_score och en BUY/SELL/NO_TRADE-
signal med entry/SL/TP/confidence.

VIKTIGT: I den här första versionen finns ännu ingen nyhets- eller makromodul
kopplad in (kommer i nästa steg), så fundamental_score/macro_score/news_score
sätts till 0.0 (neutralt) med data_quality="missing". Signal engine straffar
automatiskt confidence när kritisk data saknas - enligt spec ska systemet
ALDRIG generera en hög-confidence trade om kritiska källor saknas.

Så snart nyhets-/makromoduler finns på plats kopplas deras score-output in
här utan att resten av motorn behöver ändras.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from engine.config.settings import settings
from engine.risk_engine.risk_engine import atr_based_sltp, structure_based_sltp, calculate_position_size, cap_size_by_margin

# Vikter för hur delscoren kombineras till final_score.
# Tekniskt väger tyngst tills fundamental/makro/nyheter är på plats,
# men vikterna justeras automatiskt (renormaliseras) beroende på vilken
# data som faktiskt finns tillgänglig i den aktuella körningen.
BASE_WEIGHTS = {
    "technical": 0.40,
    "fundamental": 0.20,
    "macro": 0.15,
    "news": 0.15,
    "cross_market": 0.10,
}


@dataclass
class ScoreInputs:
    technical_score: float
    fundamental_score: float = 0.0
    macro_score: float = 0.0
    news_score: float = 0.0
    cross_market_score: float = 0.0
    data_quality: dict = field(default_factory=dict)  # {"fundamental": "missing"/"ok", ...}


def _renormalized_weights(data_quality: dict) -> dict:
    """
    Om en datakälla saknas ("missing") nollas dess vikt och resterande
    vikter skalas upp proportionellt så summan förblir 1.0.
    Detta gör att systemet aldrig "hittar på" ett fundamental-score av 0
    och låtsas att det är en neutral åsikt - det exkluderas helt tills
    riktig data finns.
    """
    active = {k: w for k, w in BASE_WEIGHTS.items() if data_quality.get(k) != "missing"}
    total = sum(active.values())
    if total == 0:
        return {"technical": 1.0}
    return {k: w / total for k, w in active.items()}


def calculate_final_score(scores: ScoreInputs) -> tuple[float, dict]:
    weights = _renormalized_weights(scores.data_quality)
    components = {
        "technical": scores.technical_score,
        "fundamental": scores.fundamental_score,
        "macro": scores.macro_score,
        "news": scores.news_score,
        "cross_market": scores.cross_market_score,
    }
    final = sum(weights.get(k, 0.0) * v for k, v in components.items())
    final = max(-1.0, min(1.0, final))
    return final, weights


def calculate_confidence(final_score: float, data_quality: dict, weights: dict) -> float:
    """
    Confidence 0-100 baseras på:
    1. Hur extremt final_score är (starkare score = mer confidence)
    2. Hur stor andel av datakällorna som faktiskt var tillgängliga
       (fler bekräftande, oberoende källor = högre confidence)
    """
    strength_component = min(abs(final_score), 1.0) * 70  # max 70 poäng från styrka

    n_sources_total = len(BASE_WEIGHTS)
    n_sources_available = sum(1 for k in BASE_WEIGHTS if data_quality.get(k) != "missing")
    coverage_component = (n_sources_available / n_sources_total) * 30  # max 30 poäng från täckning

    confidence = strength_component + coverage_component
    return round(min(confidence, 100.0), 1)


def _symbol_config(symbol: str) -> dict:
    """Faller tillbaka till XAUUSD:s konfiguration om en okänd symbol skulle
    dyka upp - undviker krasch, men loggas tydligt i full_reasoning ändå."""
    return settings.SYMBOLS.get(symbol, settings.SYMBOLS["XAUUSD"])


def decide(final_score: float, strategy_mode: str, symbol: str) -> str:
    cfg = _symbol_config(symbol)
    if strategy_mode == "range":
        buy_threshold, sell_threshold = cfg["range_buy_threshold"], cfg["range_sell_threshold"]
    else:
        buy_threshold, sell_threshold = cfg["buy_threshold"], cfg["sell_threshold"]
    if final_score > buy_threshold:
        return "BUY"
    if final_score < sell_threshold:
        return "SELL"
    return "NO_TRADE"


def build_signal(
    symbol: str,
    current_price: float,
    atr: float,
    support: float | None,
    resistance: float | None,
    scores: ScoreInputs,
    account_balance: float,
    time_horizon: str = "1h",
    strategy_mode: str = "trend",
) -> dict:
    """Producerar ett komplett signal-dict redo att sparas i `signals`-tabellen.

    strategy_mode: 'trend' eller 'range' - avgör vilket trösklar-par som
    används (se settings.SYMBOLS[symbol]) och sparas med signalen för att
    kunna jämföra performance mellan modellerna.
    Alla trösklar och riskparametrar (SL-multipel, R/R-mål, max risk %) läses
    per symbol från settings.SYMBOLS - inte globalt - så olika instrument
    (t.ex. BTCUSD vs XAUUSD) kan kalibreras helt oberoende av varandra."""
    cfg = _symbol_config(symbol)
    final_score, weights_used = calculate_final_score(scores)
    confidence = calculate_confidence(final_score, scores.data_quality, weights_used)
    decision = decide(final_score, strategy_mode, symbol)
    if strategy_mode == "range":
        buy_threshold, sell_threshold = cfg["range_buy_threshold"], cfg["range_sell_threshold"]
    else:
        buy_threshold, sell_threshold = cfg["buy_threshold"], cfg["sell_threshold"]

    signal = {
        "symbol": symbol,
        "strategy_mode": strategy_mode,
        "decision": decision,
        "final_score": round(final_score, 4),
        "technical_score": round(scores.technical_score, 4),
        "fundamental_score": round(scores.fundamental_score, 4),
        "macro_score": round(scores.macro_score, 4),
        "news_score": round(scores.news_score, 4),
        "cross_market_score": round(scores.cross_market_score, 4),
        "confidence": confidence,
        "time_horizon": time_horizon,
        "risk_score": round(1.0 - (confidence / 100), 4),
    }

    if decision == "NO_TRADE":
        signal["entry"] = None
        signal["stop_loss"] = None
        signal["take_profit"] = None
        signal["risk_reward"] = None
        signal["short_explanation"] = "Inget tillräckligt starkt score i någon riktning - ingen trade tas."
        signal["full_reasoning"] = (
            f"final_score={final_score:.3f} ligger inom NO_TRADE-intervallet "
            f"({sell_threshold} till {buy_threshold}, strategy_mode={strategy_mode}, symbol={symbol}). "
            f"Vikter använda: {weights_used}."
        )
        return signal

    # Beräkna SL/TP med båda modellerna (med symbolens egna ATR-multipel/RR-mål),
    # välj den strukturbaserade om den ger rimlig risk/reward (>=1.3), annars
    # fallback till ren ATR-modell.
    structure_result = structure_based_sltp(current_price, decision, support, resistance, atr)
    if structure_result.risk_reward >= 1.3:
        sltp = structure_result
    else:
        sltp = atr_based_sltp(current_price, decision, atr,
                               sl_atr_mult=cfg["sl_atr_mult"], rr_target=cfg["rr_target"])

    sizing = calculate_position_size(account_balance, cfg["max_risk_pct"], current_price, sltp.stop_loss)

    # Marginal-koll (2026-08-20): den risk-baserade storleken kan i teorin
    # kräva mer marginal än vad kontot borde binda upp i en enda trade,
    # särskilt på ett litet konto (5000 SEK) med låg hävstång (BTC 1:2).
    # Skalar ner storleken om så behövs, så den alltid är öppningsbar på
    # riktigt hos brokern med den hävstången.
    leverage = cfg.get("leverage", 1)
    max_margin_pct = cfg.get("max_margin_pct_per_trade", 1.0)
    margin_result = cap_size_by_margin(
        sizing["size"], current_price, leverage, account_balance, max_margin_pct
    )
    if margin_result["capped"]:
        # Storleken justerades -> risk_amount_sek måste räknas om till vad
        # den FAKTISKA (nedskalade) storleken riskerar, annars skulle den
        # visade risken vara högre än vad som verkligen står på spel.
        risk_per_unit = abs(current_price - sltp.stop_loss)
        sizing["size"] = margin_result["size"]
        sizing["risk_amount_sek"] = round(margin_result["size"] * risk_per_unit, 2)

    signal["entry"] = round(current_price, 2)
    signal["stop_loss"] = round(sltp.stop_loss, 2)
    signal["take_profit"] = round(sltp.take_profit, 2)
    signal["risk_reward"] = round(sltp.risk_reward, 2)
    signal["sl_model"] = sltp.sl_model
    signal["tp_model"] = sltp.tp_model
    signal["volatility"] = atr
    signal["leverage"] = leverage
    signal["margin_required"] = margin_result["margin_required"]
    signal["short_explanation"] = (
        f"{decision} - final score {final_score:.2f}, confidence {confidence:.0f}%. "
        f"Baserat huvudsakligen på teknisk analys (fundamental/makro/nyheter ej "
        f"inkopplat i denna version)."
    )
    signal["full_reasoning"] = (
        f"technical_score={scores.technical_score:.3f}, "
        f"fundamental_score={scores.fundamental_score:.3f} (quality={scores.data_quality.get('fundamental','missing')}), "
        f"macro_score={scores.macro_score:.3f} (quality={scores.data_quality.get('macro','missing')}), "
        f"news_score={scores.news_score:.3f} (quality={scores.data_quality.get('news','missing')}), "
        f"cross_market_score={scores.cross_market_score:.3f} (quality={scores.data_quality.get('cross_market','missing')}). "
        f"Vikter använda (renormaliserade efter datatillgänglighet): {weights_used}. "
        f"SL/TP-modell: {sltp.sl_model}/{sltp.tp_model} (sl_atr_mult={cfg['sl_atr_mult']}, rr_target={cfg['rr_target']}). "
        f"Hävstång {leverage}:1, marginal krävd {margin_result['margin_required']:.2f}"
        f"{' (storlek nedskalad pga marginalgräns)' if margin_result['capped'] else ''}."
    )
    signal["position_size"] = sizing["size"]
    signal["position_size_unit"] = cfg["unit_label"]
    signal["risk_amount_sek"] = sizing["risk_amount_sek"]

    return signal

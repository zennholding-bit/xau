"""
Cross-market score: väger in hur relaterade marknader (USD-index, räntor,
olja) rör sig, eftersom de har kända, vedertagna samband med guldpriset.
Använder data som redan hämtas dagligen av market_data_ingest - inga extra
API-anrop krävs.

Samband:
- DXY (USD-index) upp -> BEARISH guld (guld prisas i USD, starkare dollar
  gör guld dyrare i andra valutor -> lägre efterfrågan)
- US10Y (räntor) upp -> BEARISH guld (högre avkastning på räntebärande
  alternativ till icke-avkastande guld)
- WTI (olja) upp -> svagt BULLISH guld (inflationsförväntningar,
  korrelerade "hard asset"-flöden)
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class CrossMarketInput:
    symbol: str
    latest_close: float | None
    prior_close: float | None  # t.ex. 20 dagar tidigare, för trend


_POLARITY = {
    "DXY": -1,
    "US10Y": -1,
    "WTI": +1,
}
_WEIGHTS = {
    "DXY": 0.45,
    "US10Y": 0.40,
    "WTI": 0.15,
}


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_cross_market(inputs: list[CrossMarketInput]) -> tuple[float, str]:
    """
    Beräknar cross_market_score utifrån trend (procentuell förändring) i
    DXY/US10Y/WTI. Symboler utan data hoppas över (renormaliserar vikterna).
    """
    contributions = []
    reasoning_parts = []

    for inp in inputs:
        if inp.symbol not in _POLARITY:
            continue
        if inp.latest_close is None or inp.prior_close is None or inp.prior_close == 0:
            continue

        pct_change = (inp.latest_close - inp.prior_close) / inp.prior_close
        normalized = _clip(pct_change * 20)  # skala: 5% rörelse -> fullt utslag
        score = normalized * _POLARITY[inp.symbol]
        weight = _WEIGHTS[inp.symbol]
        contributions.append((score, weight))

        direction_text = "upp" if pct_change > 0 else "ner"
        reasoning_parts.append(f"{inp.symbol} {direction_text} {pct_change*100:.1f}%")

    if not contributions:
        return 0.0, "Ingen cross-market-data tillgänglig."

    total_weight = sum(w for _, w in contributions)
    combined = sum(s * w for s, w in contributions) / total_weight
    combined = _clip(combined)

    summary = "Cross-market: " + ", ".join(reasoning_parts)
    return combined, summary

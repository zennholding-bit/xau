"""
Regelbaserad (deterministisk, ingen AI) tolkning av makrodata för XAU/USD.

Varje seriekategori har en känd ekonomisk transmissionskanal till guld:

- Stigande inflation (CPI/Core CPI/PCE) än föregående mätning
  -> marknaden väntar sig mer hökaktig Fed -> högre realräntor -> BEARISH guld
  (motsatt effekt av "guld som inflationsskydd" dominerar på kort sikt via
  räntekanalen - detta är en förenkling, verkligheten är mer komplex, men
  är en vedertagen tumregel tills en AI-modell kan väga fler faktorer)

- Starkare arbetsmarknad (NFP upp, arbetslöshet ner)
  -> hökaktigt -> BEARISH guld

- Höjd styrränta (Fed Funds Rate)
  -> högre opportunitetskostnad att hålla icke-avkastande guld -> BEARISH

- Stigande obligationsräntor (10Y yield)
  -> BEARISH guld (högre avkastning på alternativ)

- Stigande realränta (TIPS yield)
  -> starkt BEARISH guld (guld har ingen egen avkastning att konkurrera med)

- Fler nyanmälda arbetslösa (jobless claims)
  -> duvaktigt/svagare ekonomi -> BULLISH guld

Varje faktor viktas efter hur direkt kopplad den är till guldpriset historiskt.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class MacroFactorResult:
    event_code: str
    direction: str      # "bullish" | "bearish" | "neutral"
    score: float         # -1..+1, bidrag till XAU
    weight: float         # hur mycket denna faktor väger i totalen
    reasoning: str


# Vikter: hur starkt varje seriekategori historiskt påverkar guld.
# Realränta och Fed Funds Rate väger tyngst (mest direkt kanal till guld).
_FACTOR_WEIGHTS = {
    "US10Y_REAL_YIELD": 0.25,
    "FED_FUNDS_RATE": 0.20,
    "US_CORE_CPI": 0.15,
    "US_CPI": 0.10,
    "US_CORE_PCE": 0.10,
    "US_NFP": 0.08,
    "US_UNEMPLOYMENT_RATE": 0.05,
    "US10Y_YIELD": 0.05,
    "US_INITIAL_JOBLESS_CLAIMS": 0.02,
}

# Riktning: +1 betyder att en ÖKNING i serien är BULLISH för guld,
# -1 betyder att en ÖKNING i serien är BEARISH för guld.
_FACTOR_POLARITY = {
    "US10Y_REAL_YIELD": -1,
    "FED_FUNDS_RATE": -1,
    "US_CORE_CPI": -1,
    "US_CPI": -1,
    "US_CORE_PCE": -1,
    "US_NFP": -1,
    "US_UNEMPLOYMENT_RATE": +1,
    "US10Y_YIELD": -1,
    "US_INITIAL_JOBLESS_CLAIMS": +1,
}

_REASONING_TEMPLATES = {
    "US10Y_REAL_YIELD": "Realräntan {direction_text} ({change:+.2f}) - {effect} guldets attraktivitet mot räntebärande alternativ.",
    "FED_FUNDS_RATE": "Styrräntan {direction_text} ({change:+.2f}) - {effect} opportunitetskostnaden att hålla guld.",
    "US_CORE_CPI": "Kärn-KPI {direction_text} ({change:+.2f}) - {effect} förväntningar på Fed:s räntebana.",
    "US_CPI": "KPI {direction_text} ({change:+.2f}) - {effect} förväntningar på Fed:s räntebana.",
    "US_CORE_PCE": "Kärn-PCE {direction_text} ({change:+.2f}) - {effect} Fed:s föredragna inflationsmått.",
    "US_NFP": "Sysselsättningen {direction_text} ({change:+.0f}k) - {effect} bilden av en stark arbetsmarknad.",
    "US_UNEMPLOYMENT_RATE": "Arbetslösheten {direction_text} ({change:+.2f}pp) - {effect} sannolikheten för Fed-lättnader.",
    "US10Y_YIELD": "10-åriga räntan {direction_text} ({change:+.2f}) - {effect} guldets relativa avkastning.",
    "US_INITIAL_JOBLESS_CLAIMS": "Nyanmälda arbetslösa {direction_text} ({change:+.0f}) - {effect} bilden av arbetsmarknadens styrka.",
}


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_single_event(event: dict) -> MacroFactorResult | None:
    """
    Beräknar ett score för en enskild makrohändelse baserat på förändring
    mot föregående publicering (actual - previous).
    """
    code = event.get("event_code")
    if code not in _FACTOR_WEIGHTS:
        return None

    actual = event.get("actual")
    previous = event.get("previous")
    if actual is None or previous is None:
        return None

    change = actual - previous
    polarity = _FACTOR_POLARITY[code]
    weight = _FACTOR_WEIGHTS[code]

    # Normalisera förändringen till en rimlig skala per seriekategori så
    # att t.ex. NFP (förändras i tusental) inte får orimligt utslag jämfört
    # med räntor (förändras i procentenheter).
    scale = {
        "US10Y_REAL_YIELD": 0.5, "FED_FUNDS_RATE": 0.5, "US_CORE_CPI": 0.3,
        "US_CPI": 0.3, "US_CORE_PCE": 0.3, "US_NFP": 300.0,
        "US_UNEMPLOYMENT_RATE": 0.3, "US10Y_YIELD": 0.5,
        "US_INITIAL_JOBLESS_CLAIMS": 50000.0,
    }.get(code, 1.0)

    normalized = _clip(change / scale) if scale else 0.0
    raw_score = _clip(normalized * polarity)

    direction = "bullish" if raw_score > 0.1 else ("bearish" if raw_score < -0.1 else "neutral")
    direction_text = "steg" if change > 0 else ("sjönk" if change < 0 else "var oförändrad")
    effect = "stärker" if raw_score > 0 else ("försvagar" if raw_score < 0 else "påverkar knappt")

    template = _REASONING_TEMPLATES.get(code, "{event_code} förändrades ({change:+.2f}).")
    reasoning = template.format(direction_text=direction_text, change=change, effect=effect)

    return MacroFactorResult(
        event_code=code, direction=direction, score=raw_score, weight=weight, reasoning=reasoning,
    )


def score_macro_events(events: list[dict]) -> tuple[float, str, list[MacroFactorResult]]:
    """
    Kombinerar flera makrohändelser (senaste publiceringen av varje serie)
    till ett samlat macro_score (-1..+1) plus en läsbar sammanfattning.
    """
    results = [r for e in events if (r := score_single_event(e)) is not None]
    if not results:
        return 0.0, "Ingen relevant makrodata tillgänglig.", []

    total_weight = sum(r.weight for r in results)
    if total_weight == 0:
        return 0.0, "Ingen relevant makrodata tillgänglig.", []

    combined = sum(r.score * r.weight for r in results) / total_weight
    combined = _clip(combined)

    summary = " ".join(r.reasoning for r in sorted(results, key=lambda r: -r.weight)[:4])
    return combined, summary, results

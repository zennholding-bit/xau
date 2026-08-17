"""
Regelbaserad (deterministisk, ingen AI) tolkning av nyhetskategorier för
XAU/USD - motsvarande "AI-baserad fundamental analys" i specen, men med
transparenta regler istället för en språkmodell (v1-valet: regelbaserat
först, AI kan kopplas in senare utan att signal-motorn behöver ändras).

Varje kategori resonerar genom en känd transmissionskanal, exakt som specen
efterfrågade (exempel: geopolitisk eskalering -> safe haven-efterfrågan upp
-> potentiellt även olja upp -> inflationsförväntningar upp -> men USD kan
också stärkas -> konkurrerande effekter på guld).
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class NewsScoreResult:
    xau_direction: str        # "bullish" | "bearish" | "neutral"
    xau_score: float          # -1..+1
    risk_sentiment: str       # "risk_on" | "risk_off" | "mixed"
    reasoning_summary: str
    conflicting_factors: list[str] = field(default_factory=list)


# Kategori -> (bas-score för XAU, risk_sentiment, resonemang-mall)
# Positivt score = bullish guld, negativt = bearish.
_CATEGORY_RULES = {
    "geopolitics": {
        "score": 0.55, "risk_sentiment": "risk_off",
        "reasoning": "Geopolitisk händelse -> ökad efterfrågan på säkra tillgångar (safe haven) -> "
                     "stödjer guld. Motverkande faktor: kan även stärka USD som alternativ safe haven, "
                     "vilket delvis kan dämpa effekten.",
        "conflicts": ["USD kan också stärkas som konkurrerande safe haven"],
    },
    "central_bank": {
        "score": -0.15, "risk_sentiment": "mixed",
        "reasoning": "Uttalande från centralbank/Fed. Riktning beror på ton (hökaktig/duvaktig) - "
                     "utan djupare textanalys antas en svagt bearish bas-effekt (osäkerhet kring "
                     "räntebana tenderar att gynna USD kortsiktigt).",
        "conflicts": ["Faktisk effekt beror starkt på om budskapet är hökaktigt eller duvaktigt"],
    },
    "inflation": {
        "score": 0.25, "risk_sentiment": "mixed",
        "reasoning": "Inflationsrelaterad nyhet -> guld har historiskt fungerat som inflationsskydd, "
                     "vilket ger en svagt bullish bas-effekt. Motverkas ofta av samtidiga ränteförväntningar.",
        "conflicts": ["Högre inflationsförväntningar kan också driva upp räntor, vilket är bearish för guld"],
    },
    "employment": {
        "score": -0.10, "risk_sentiment": "mixed",
        "reasoning": "Arbetsmarknadsnyhet -> stark arbetsmarknad tenderar att stödja hökaktig "
                     "Fed-politik -> svagt bearish för guld.",
        "conflicts": [],
    },
    "energy": {
        "score": 0.15, "risk_sentiment": "mixed",
        "reasoning": "Energi/oljerelaterad nyhet -> högre energipriser kan driva inflationsförväntningar "
                     "uppåt -> svagt bullish för guld via inflationsskydds-kanalen.",
        "conflicts": [],
    },
    "trade": {
        "score": 0.20, "risk_sentiment": "risk_off",
        "reasoning": "Handelskonflikt/tullar -> ökad ekonomisk osäkerhet -> viss safe haven-efterfrågan "
                     "för guld.",
        "conflicts": [],
    },
    "financial_stability": {
        "score": 0.60, "risk_sentiment": "risk_off",
        "reasoning": "Finansiell stress/bankkris-relaterad nyhet -> stark safe haven-efterfrågan -> "
                     "tydligt bullish för guld.",
        "conflicts": [],
    },
    "gold_specific": {
        "score": 0.10, "risk_sentiment": "mixed",
        "reasoning": "Guld-specifik marknadsnyhet - riktning oftast redan inprisad, svag bas-effekt.",
        "conflicts": [],
    },
    "general": {
        "score": 0.0, "risk_sentiment": "mixed",
        "reasoning": "Allmän marknadsnyhet utan tydlig koppling till kända XAU/USD-transmissionskanaler.",
        "conflicts": [],
    },
}


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_article(categories: list[str], importance: float) -> NewsScoreResult:
    """
    Beräknar ett XAU-score för en enskild artikel baserat på dess kategorier.
    Om artikeln matchar flera kategorier kombineras deras effekter (viktat
    genom att mer specifika/starka kategorier dominerar).
    """
    if not categories:
        categories = ["general"]

    rules = [_CATEGORY_RULES.get(c, _CATEGORY_RULES["general"]) for c in categories]

    # Väg samman: starkare (absolutbelopp) kategorier får mer inflytande
    total_weight = sum(abs(r["score"]) + 0.1 for r in rules)  # +0.1 så "neutral" kategorier ändå räknas in lite
    combined_score = sum(r["score"] * (abs(r["score"]) + 0.1) for r in rules) / total_weight
    combined_score = _clip(combined_score * (importance / 100))  # dämpa med importance

    direction = "bullish" if combined_score > 0.1 else ("bearish" if combined_score < -0.1 else "neutral")

    risk_sentiments = [r["risk_sentiment"] for r in rules]
    if all(s == "risk_off" for s in risk_sentiments):
        risk_sentiment = "risk_off"
    elif all(s == "risk_on" for s in risk_sentiments):
        risk_sentiment = "risk_on"
    else:
        risk_sentiment = "mixed"

    reasoning_summary = " ".join(r["reasoning"] for r in rules[:2])
    conflicting_factors = [c for r in rules for c in r["conflicts"]]

    return NewsScoreResult(
        xau_direction=direction,
        xau_score=combined_score,
        risk_sentiment=risk_sentiment,
        reasoning_summary=reasoning_summary,
        conflicting_factors=conflicting_factors,
    )


def aggregate_news_scores(scored_articles: list[dict]) -> tuple[float, str]:
    """
    Kombinerar flera redan scorade artiklar (senaste tidsfönstret) till ett
    samlat news_score. Nyare och viktigare artiklar väger tyngre.
    """
    if not scored_articles:
        return 0.0, "Inga relevanta nyheter i tidsfönstret."

    total_weight = sum(a.get("importance_score", 50) for a in scored_articles)
    if total_weight == 0:
        return 0.0, "Inga relevanta nyheter i tidsfönstret."

    combined = sum(a["xau_score"] * a.get("importance_score", 50) for a in scored_articles) / total_weight
    combined = _clip(combined)

    top = sorted(scored_articles, key=lambda a: -a.get("importance_score", 0))[:3]
    summary = f"{len(scored_articles)} relevanta nyheter analyserade. " + " | ".join(
        a["headline"] for a in top if "headline" in a
    )
    return combined, summary

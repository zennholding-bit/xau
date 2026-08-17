"""
NewsProvider - hämtar nyheter från gratis, publikt tillgängliga RSS-flöden.

Flödena är medvetet valda bland KÄLLOR SOM ÄR BYGGDA FÖR MASKINELL LÄSNING
(RSS är designat för automatiserad konsumtion, till skillnad från t.ex.
Yahoo Finance/Stooq som är webbsidor vi tidigare försökte skrapa och som
blockerade oss). Det gör RSS betydligt mer pålitligt att köra från GitHub
Actions.

Om ett enskilt flöde skulle sluta fungera hoppar systemet bara över det
(loggat tydligt) - resten av insamlingen fortsätter opåverkad.
"""
from __future__ import annotations
import hashlib
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Källor valda för relevans mot spec: Fed, inflation, arbetsmarknad, räntor,
# geopolitik, olja/energi, generell marknadsoro.
RSS_FEEDS = {
    "Federal Reserve (pressmeddelanden)": "https://www.federalreserve.gov/feeds/press_all.xml",
    "Federal Reserve (penningpolitik)": "https://www.federalreserve.gov/feeds/press_monetary.xml",
    "Kitco News": "https://www.kitco.com/rss/KitcoNews.xml",
    "OilPrice.com": "https://oilprice.com/rss/main",
    "MarketWatch Top Stories": "https://www.marketwatch.com/rss/topstories",
    "MarketWatch Realtime": "https://www.marketwatch.com/rss/realtimeheadlines",
    "CNBC Markets": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "Investing.com Commodities": "https://www.investing.com/rss/commodities.rss",
}

# Kategorisering + relevans-nyckelord (svensk spec, engelska nyhetskällor)
CATEGORY_KEYWORDS = {
    "central_bank": ["federal reserve", "fed ", "fomc", "interest rate", "powell", "central bank",
                      "ecb", "bank of japan", "rate hike", "rate cut", "monetary policy"],
    "inflation": ["inflation", "cpi", "consumer price", "pce", "core inflation", "deflation"],
    "employment": ["nonfarm payroll", "unemployment", "jobless claims", "jobs report", "labor market"],
    "geopolitics": ["war", "conflict", "sanctions", "military", "invasion", "ceasefire",
                     "iran", "israel", "russia", "ukraine", "china", "taiwan", "middle east"],
    "energy": ["oil price", "crude oil", "opec", "oil production", "energy market", "natural gas"],
    "trade": ["tariff", "trade war", "trade deal", "export ban", "import duty"],
    "financial_stability": ["bank crisis", "bank failure", "credit crunch", "recession",
                              "financial stress", "liquidity crisis", "default"],
    "gold_specific": ["gold price", "gold market", "safe haven", "bullion", "precious metal"],
}

_COUNTRY_KEYWORDS = {
    "US": ["united states", "u.s.", "fed", "washington", "america"],
    "CN": ["china", "beijing", "chinese", "yuan"],
    "RU": ["russia", "russian", "moscow", "kremlin"],
    "IR": ["iran", "iranian", "tehran"],
    "IL": ["israel", "israeli"],
    "EU": ["european union", "eurozone", "ecb", "europe"],
    "JP": ["japan", "japanese", "yen", "boj"],
}


def _normalize_headline(headline: str) -> str:
    """Normaliserar en rubrik för dedup: gemener, tar bort skiljetecken/whitespace."""
    text = headline.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def compute_headline_hash(headline: str) -> str:
    normalized = _normalize_headline(headline)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def categorize(text: str) -> list[str]:
    text_lower = text.lower()
    categories = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            # Helordsmatchning (\b) för att undvika falska träffar som
            # "war" i "award" eller "china" i "chinatown".
            pattern = r"\b" + re.escape(kw) + r"\b"
            if re.search(pattern, text_lower):
                categories.append(category)
                break
    return categories or ["general"]


def extract_countries(text: str) -> list[str]:
    text_lower = text.lower()
    found = []
    for code, keywords in _COUNTRY_KEYWORDS.items():
        for kw in keywords:
            pattern = r"\b" + re.escape(kw) + r"\b"
            if re.search(pattern, text_lower):
                found.append(code)
                break
    return found


def compute_importance(categories: list[str], source: str) -> float:
    """
    Grov, transparent importance-scoring 0-100 baserat på kategori.
    Central bank/inflation/geopolitik väger tyngst för XAU/USD-relevans.
    """
    category_weights = {
        "central_bank": 90, "inflation": 85, "employment": 75, "geopolitics": 80,
        "financial_stability": 85, "energy": 60, "trade": 65, "gold_specific": 70,
        "general": 30,
    }
    if not categories:
        return 30.0
    return max(category_weights.get(c, 30) for c in categories)


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8), reraise=True)
def _fetch_feed(url: str) -> feedparser.FeedParserDict:
    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (compatible; XAU-NewsBot/1.0)"})
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"Kunde inte tolka RSS-flöde: {parsed.get('bozo_exception')}")
    return parsed


def _parse_published(entry) -> datetime:
    for field in ("published", "updated"):
        raw = entry.get(field)
        if raw:
            try:
                return parsedate_to_datetime(raw).astimezone(timezone.utc)
            except Exception:
                pass
    return datetime.now(timezone.utc)


def fetch_all_news(max_per_feed: int = 20) -> list[dict]:
    """
    Hämtar nyheter från alla konfigurerade RSS-flöden.
    Returnerar en lista redo att sparas i news_articles. Kraschar aldrig helt -
    varje flöde hanteras isolerat.
    """
    all_articles = []
    for source_name, url in RSS_FEEDS.items():
        try:
            parsed = _fetch_feed(url)
        except Exception as e:
            logger.error("Kunde inte hämta RSS-flöde %s (%s): %s", source_name, url, e)
            continue

        entries = parsed.entries[:max_per_feed]
        for entry in entries:
            headline = entry.get("title", "").strip()
            if not headline:
                continue
            summary = re.sub(r"<[^>]+>", "", entry.get("summary", "")).strip()[:500]
            link = entry.get("link", "")
            published_at = _parse_published(entry)
            full_text = f"{headline} {summary}"

            categories = categorize(full_text)
            countries = extract_countries(full_text)
            importance = compute_importance(categories, source_name)

            all_articles.append({
                "external_id": entry.get("id") or link or headline,
                "source": source_name,
                "headline": headline,
                "summary": summary,
                "url": link,
                "published_at": published_at.isoformat(),
                "category": categories[0],
                "mentioned_countries": countries,
                "mentioned_assets": ["XAU"] if "gold_specific" in categories else [],
                "raw_hash": compute_headline_hash(headline),
                "cluster_id": compute_headline_hash(headline),  # v1: hash = kluster (se dedup.py för utökning)
                "quality_score": 1.0,
            })

        logger.info("Hämtade %s artiklar från %s", len(entries), source_name)

    return all_articles

"""
Paper Trading Engine.

Öppnar simulerade trades från kvalificerade signaler, och stänger dem när
priset når SL eller TP baserat på efterföljande candles. INGA riktiga
broker-anrop görs - LiveBroker existerar inte i denna version (se
engine/paper_trading/broker_interface.py).
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
import pandas as pd

from engine.config.settings import settings
from engine.database.client import get_db, insert
from engine.risk_engine.risk_engine import calculate_required_margin, split_into_tp_legs

logger = logging.getLogger(__name__)


def get_account_balance() -> float:
    db = get_db()
    res = db.table("account_state").select("balance_sek").eq("id", 1).single().execute()
    return float(res.data["balance_sek"]) if res.data else settings.STARTING_BALANCE_SEK


def update_account_balance(new_balance: float) -> None:
    db = get_db()
    db.table("account_state").update({"balance_sek": new_balance, "updated_at": "now()"}).eq("id", 1).execute()


def get_open_trades(symbol: str | None = None) -> list[dict]:
    db = get_db()
    query = db.table("paper_trades").select("*").eq("outcome", "OPEN")
    if symbol:
        query = query.eq("symbol", symbol)
    res = query.execute()
    return res.data or []


def get_total_open_margin() -> float:
    """
    Summerar marginal_required över ALLA öppna trades, oavsett symbol -
    en riktig broker delar inte upp marginal per instrument, allt dras från
    samma konto. Används för att avgöra hur mycket marginal-utrymme som
    faktiskt finns kvar innan en ny trade öppnas.
    """
    db = get_db()
    res = db.table("paper_trades").select("margin_required").eq("outcome", "OPEN").execute()
    return sum(float(t["margin_required"] or 0) for t in (res.data or []))


def open_trade_from_signal(signal: dict) -> dict | None:
    """Öppnar en paper trade om signalen är kvalificerad (BUY/SELL + tillräcklig
    confidence + tillräckligt marginal-utrymme kvar på kontot totalt).

    min_confidence_to_trade läses per symbol från settings.SYMBOLS - INTE en
    global konstant längre, eftersom en hög generell gräns (tidigare 60%)
    tyst kunde blockera trades även när decide() redan sagt BUY/SELL.

    Total marginal-koll (2026-08-20): innan öppning summeras marginal_required
    för ALLA redan öppna trades (över alla symboler). Om den nya tradens
    marginal inte får plats inom TOTAL_MARGIN_CAP_PCT av kontosaldot - efter
    vad som redan är upptaget - skalas storleken ner, eller avvisas traden
    helt om det inte finns något utrymme kvar alls. Detta speglar hur en
    riktig broker fungerar: marginal är en delad, kontobred resurs, inte
    något varje trade får isolerat för sig själv."""
    if signal["decision"] == "NO_TRADE":
        return None
    cfg = settings.SYMBOLS.get(signal["symbol"], {})
    min_confidence = cfg.get("min_confidence_to_trade", 20.0)
    if signal["confidence"] < min_confidence:
        return None

    size = signal.get("position_size", 0.0)
    risk_amount_sek = signal.get("risk_amount_sek", 0.0)
    leverage = signal.get("leverage") or cfg.get("leverage", 1)
    margin_required = signal.get("margin_required")
    if margin_required is None:
        margin_required = calculate_required_margin(size, signal["entry"], leverage)

    account_balance = get_account_balance()
    existing_margin = get_total_open_margin()
    margin_budget = account_balance * settings.TOTAL_MARGIN_CAP_PCT
    remaining_budget = margin_budget - existing_margin

    if remaining_budget <= 0:
        logger.warning(
            "Trade avvisad (signal_id=%s, %s): ingen marginal kvar - %s SEK redan upptaget av öppna trades, budget %s SEK.",
            signal["id"], signal["symbol"], round(existing_margin, 2), round(margin_budget, 2),
        )
        return None

    scale = 1.0
    if margin_required > remaining_budget:
        scale = remaining_budget / margin_required
        size = size * scale
        risk_amount_sek = risk_amount_sek * scale
        margin_required = calculate_required_margin(size, signal["entry"], leverage)
        logger.info(
            "Trade nedskalad (signal_id=%s, %s): endast %s SEK marginal-utrymme kvar av %s SEK totalt, storlek skalad ner %.0f%%.",
            signal["id"], signal["symbol"], round(remaining_budget, 2), round(margin_budget, 2), scale * 100,
        )

    # Delvis vinsthemtagning (2026-08-21): signal["legs"] beräknades i
    # signal_engine.py FÖRE marginal-kollen ovan. Om marginalen skalade ner
    # storleken (scale < 1.0) måste benen räknas om från grunden med den
    # FAKTISKA, nedskalade lot-storleken - annars skulle benens totala
    # storlek inte stämma med vad marginal-budgeten faktiskt tillåter.
    legs = signal.get("legs") or [{"level_r": None, "take_profit": signal["take_profit"], "lots": signal.get("lots", 0.0)}]
    if scale < 1.0:
        legs = split_into_tp_legs(
            signal["entry"], signal["decision"], signal["stop_loss"],
            total_lots=signal.get("lots", 0.0) * scale,
            tp_legs=cfg.get("tp_legs", []),
            contract_size=cfg.get("contract_size", 100),
            lot_step=cfg.get("lot_step", 0.01),
            min_lot=cfg.get("min_lot", 0.01),
            fallback_take_profit=signal["take_profit"],
        )

    contract_size = cfg.get("contract_size", 100)
    entry_time = datetime.now(timezone.utc).isoformat()
    leg_count = len(legs)
    trades = []
    for i, leg in enumerate(legs, start=1):
        leg_size_units = leg["lots"] * contract_size
        leg_risk_per_unit = abs(signal["entry"] - signal["stop_loss"])
        trades.append({
            "signal_id": signal["id"],
            "symbol": signal["symbol"],
            "direction": signal["decision"],
            "entry_time": entry_time,
            "entry_price": signal["entry"],
            "stop_loss": signal["stop_loss"],
            "take_profit": leg["take_profit"],
            "position_size": round(leg_size_units, 6),
            "position_size_unit": signal.get("position_size_unit"),
            "lots": leg["lots"],
            "risk_amount_sek": round(leg_size_units * leg_risk_per_unit, 2),
            "leverage": leverage,
            "margin_required": round(calculate_required_margin(leg_size_units, signal["entry"], leverage), 2),
            "leg": i,
            "leg_count": leg_count,
            "outcome": "OPEN",
        })

    saved = insert("paper_trades", trades)
    if saved:
        insert("trade_events", [{
            "trade_id": t["id"],
            "event_type": "OPENED",
            "price": signal["entry"],
            "details": {
                "signal_id": signal["id"], "confidence": signal["confidence"],
                "margin_required": t["margin_required"], "leg": t.get("leg", 1), "leg_count": leg_count,
            },
        } for t in saved])
    return saved[0] if saved else None


def _check_sl_tp_hit(trade: dict, high: float, low: float) -> str | None:
    """Returnerar 'TP' eller 'SL' om candlens high/low-range träffar respektive nivå, annars None."""
    direction = trade["direction"]
    sl, tp = trade["stop_loss"], trade["take_profit"]
    if direction == "BUY":
        if low <= sl:
            return "SL"
        if high >= tp:
            return "TP"
    else:  # SELL
        if high >= sl:
            return "SL"
        if low <= tp:
            return "TP"
    return None


def close_trade(trade: dict, exit_price: float, outcome: str, mfe: float = 0.0, mae: float = 0.0) -> dict:
    direction = trade["direction"]
    entry = trade["entry_price"]
    size = trade["position_size"]

    raw_pnl = (exit_price - entry) if direction == "BUY" else (entry - exit_price)
    pnl_sek = raw_pnl * size
    pnl_pct = (raw_pnl / entry) * 100 if entry else 0.0

    risk_per_unit = abs(entry - trade["stop_loss"])
    r_multiple = (raw_pnl / risk_per_unit) if risk_per_unit else 0.0

    balance = get_account_balance()
    new_balance = balance + pnl_sek
    update_account_balance(new_balance)

    db = get_db()
    updated = db.table("paper_trades").update({
        "exit_time": datetime.now(timezone.utc).isoformat(),
        "exit_price": exit_price,
        "pnl_sek": round(pnl_sek, 2),
        "pnl_pct": round(pnl_pct, 4),
        "r_multiple": round(r_multiple, 3),
        "mfe": mfe,
        "mae": mae,
        "outcome": outcome,
        "account_balance_after": round(new_balance, 2),
    }).eq("id", trade["id"]).execute()

    insert("trade_events", [{
        "trade_id": trade["id"],
        "event_type": f"{outcome}_HIT" if outcome in ("WIN", "LOSS") else outcome,
        "price": exit_price,
        "details": {"pnl_sek": round(pnl_sek, 2), "r_multiple": round(r_multiple, 3)},
    }])

    return updated.data[0] if updated.data else trade


def _update_stop_loss(trade_id: int, new_sl: float) -> None:
    db = get_db()
    # BUGG FIXAD (2026-08-20): sparade tidigare bara stop_loss, aldrig
    # breakeven_moved=true - vilket gjorde att en trade som triggade
    # breakeven i en cykel men träffade sitt (flyttade) SL i en SENARE cykel
    # skulle läsas som breakeven_moved=false från databasen och riskera bli
    # felaktigt stämplad LOSS trots positivt pris. Hittills har inga trades
    # faktiskt blivit felmärkta (trigger+träff hann alltid ske inom samma
    # cykel), men det var en latent bugg som kunde slagit till när som helst.
    db.table("paper_trades").update({"stop_loss": round(new_sl, 5), "breakeven_moved": True}).eq("id", trade_id).execute()
    insert("trade_events", [{
        "trade_id": trade_id,
        "event_type": "BREAKEVEN_MOVED",
        "price": new_sl,
        "details": {"new_stop_loss": round(new_sl, 5)},
    }])


def _maybe_move_to_breakeven(trade: dict, high: float, low: float, cfg: dict) -> dict:
    """
    Breakeven-stop: om traden redan rört sig breakeven_trigger_r (i R-multiplar,
    t.ex. 0.5 = halvvägs till TP) i rätt riktning, flyttas SL till entry + en
    liten buffert (breakeven_buffer_r). Traden kan därefter inte längre
    vändas till förlust - bara till en liten vinst eller full TP.

    VIKTIGT: skyddar bara trades som REDAN gått i vinst tillräckligt mycket.
    En trade som går rakt till SL utan att först röra sig i rätt riktning
    påverkas inte alls av detta.

    Returnerar traden (ev. med uppdaterat stop_loss om flytten gjordes).
    """
    trigger_r = cfg.get("breakeven_trigger_r")
    buffer_r = cfg.get("breakeven_buffer_r", 0.0)
    if trigger_r is None or trade.get("breakeven_moved"):
        return trade

    entry = trade["entry_price"]
    original_sl = trade["stop_loss"]
    risk_per_unit = abs(entry - original_sl)
    if risk_per_unit <= 0:
        return trade

    direction = trade["direction"]
    best_price = high if direction == "BUY" else low
    favorable_move = (best_price - entry) if direction == "BUY" else (entry - best_price)
    favorable_r = favorable_move / risk_per_unit

    if favorable_r >= trigger_r:
        new_sl = entry + buffer_r * risk_per_unit if direction == "BUY" else entry - buffer_r * risk_per_unit
        _update_stop_loss(trade["id"], new_sl)
        trade = dict(trade)
        trade["stop_loss"] = new_sl
        trade["breakeven_moved"] = True
    return trade


def _protect_sibling_legs_after_tp1(trade: dict, cfg: dict) -> None:
    """
    När TP1 (första benet av en delad position) träffas: flytta SL på de
    KVARVARANDE benen (TP2/TP3) till breakeven omedelbart - oavsett om deras
    egen pris-baserade breakeven_trigger_r nåtts än. Det är poängen med
    "risk-free runner"-tekniken: så fort en del av vinsten är hemtagen, ska
    resten av positionen inte längre kunna bli en förlust.
    """
    if trade.get("leg_count", 1) <= 1 or trade.get("leg") != 1:
        return
    signal_id = trade.get("signal_id")
    if signal_id is None:
        return

    db = get_db()
    res = db.table("paper_trades").select("*").eq("signal_id", signal_id).eq("outcome", "OPEN").execute()
    buffer_r = cfg.get("breakeven_buffer_r", 0.0)
    for sibling in (res.data or []):
        entry = sibling["entry_price"]
        risk_per_unit = abs(entry - trade["stop_loss"])  # ursprungligt SL-avstånd (delat av alla ben)
        if risk_per_unit <= 0 or sibling.get("breakeven_moved"):
            continue
        direction = sibling["direction"]
        new_sl = entry + buffer_r * risk_per_unit if direction == "BUY" else entry - buffer_r * risk_per_unit
        _update_stop_loss(sibling["id"], new_sl)


def monitor_open_trades(latest_candle: dict, symbol: str) -> list[dict]:
    """
    Går igenom öppna paper trades FÖR GIVEN SYMBOL, i två steg per trade:
    1. Breakeven-stop: flytta SL till entry+buffert om traden redan gått
       tillräckligt i rätt riktning (se _maybe_move_to_breakeven).
    2. Kolla om candlens high/low träffar (det ev. uppdaterade) SL eller TP.

    Delvis vinsthemtagning (2026-08-21): om en trade har flera ben (leg_count
    > 1) och ben 1 (TP1) träffas, skyddas de kvarvarande benen automatiskt
    genom att deras SL flyttas till breakeven direkt (se
    _protect_sibling_legs_after_tp1) - oberoende av deras egen pris-baserade
    breakeven-trigger.

    INGEN tidsgräns längre (2026-08-20, borttagen på användarens begäran) -
    en trade förblir öppen tills SL eller TP faktiskt nås, precis som på ett
    riktigt broker-konto. En tidigare version tvångsstängde trades efter
    max_hold_minutes, men det speglade inte hur riktiga mäklare fungerar -
    de stänger aldrig en position bara för att tiden gått.

    symbol är obligatoriskt - annars skulle t.ex. BTCUSD:s candle kunna
    trigga SL/TP på en öppen XAUUSD-position (helt olika prisskalor).
    """
    cfg = settings.SYMBOLS.get(symbol, {})

    closed = []
    for trade in get_open_trades(symbol=symbol):
        trade = _maybe_move_to_breakeven(trade, latest_candle["high"], latest_candle["low"], cfg)

        hit = _check_sl_tp_hit(trade, latest_candle["high"], latest_candle["low"])
        if hit == "TP":
            closed.append(close_trade(trade, trade["take_profit"], "WIN"))
            _protect_sibling_legs_after_tp1(trade, cfg)
            continue
        if hit == "SL":
            # Efter breakeven-flytt är SL >= entry (BUY) eller <= entry (SELL),
            # så en "SL-träff" här är i praktiken en liten vinst, inte en förlust.
            outcome = "WIN" if trade.get("breakeven_moved") else "LOSS"
            closed.append(close_trade(trade, trade["stop_loss"], outcome))
    return closed

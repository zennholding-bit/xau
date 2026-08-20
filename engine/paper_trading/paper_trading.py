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
from engine.risk_engine.risk_engine import calculate_required_margin

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

    if margin_required > remaining_budget:
        scale = remaining_budget / margin_required
        size = size * scale
        risk_amount_sek = risk_amount_sek * scale
        margin_required = calculate_required_margin(size, signal["entry"], leverage)
        logger.info(
            "Trade nedskalad (signal_id=%s, %s): endast %s SEK marginal-utrymme kvar av %s SEK totalt, storlek skalad ner %.0f%%.",
            signal["id"], signal["symbol"], round(remaining_budget, 2), round(margin_budget, 2), scale * 100,
        )

    trade = {
        "signal_id": signal["id"],
        "symbol": signal["symbol"],
        "direction": signal["decision"],
        "entry_time": datetime.now(timezone.utc).isoformat(),
        "entry_price": signal["entry"],
        "stop_loss": signal["stop_loss"],
        "take_profit": signal["take_profit"],
        "position_size": round(size, 6),
        "position_size_unit": signal.get("position_size_unit"),
        "risk_amount_sek": round(risk_amount_sek, 2),
        "leverage": leverage,
        "margin_required": round(margin_required, 2),
        "outcome": "OPEN",
    }
    saved = insert("paper_trades", [trade])
    if saved:
        insert("trade_events", [{
            "trade_id": saved[0]["id"],
            "event_type": "OPENED",
            "price": signal["entry"],
            "details": {"signal_id": signal["id"], "confidence": signal["confidence"], "margin_required": round(margin_required, 2)},
        }])
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
    db.table("paper_trades").update({"stop_loss": round(new_sl, 5)}).eq("id", trade_id).execute()
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


def monitor_open_trades(latest_candle: dict, symbol: str) -> list[dict]:
    """
    Går igenom öppna paper trades FÖR GIVEN SYMBOL, i två steg per trade:
    1. Breakeven-stop: flytta SL till entry+buffert om traden redan gått
       tillräckligt i rätt riktning (se _maybe_move_to_breakeven).
    2. Kolla om candlens high/low träffar (det ev. uppdaterade) SL eller TP.

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
            continue
        if hit == "SL":
            # Efter breakeven-flytt är SL >= entry (BUY) eller <= entry (SELL),
            # så en "SL-träff" här är i praktiken en liten vinst, inte en förlust.
            outcome = "WIN" if trade.get("breakeven_moved") else "LOSS"
            closed.append(close_trade(trade, trade["stop_loss"], outcome))
    return closed

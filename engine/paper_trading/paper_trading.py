"""
Paper Trading Engine.

Öppnar simulerade trades från kvalificerade signaler, och stänger dem när
priset når SL eller TP baserat på efterföljande candles. INGA riktiga
broker-anrop görs - LiveBroker existerar inte i denna version (se
engine/paper_trading/broker_interface.py).
"""
from __future__ import annotations
from datetime import datetime, timezone
import pandas as pd

from engine.config.settings import settings
from engine.database.client import get_db, insert

MIN_CONFIDENCE_TO_TRADE = 60.0  # kvalificerad signal måste nå denna confidence


def get_account_balance() -> float:
    db = get_db()
    res = db.table("account_state").select("balance_sek").eq("id", 1).single().execute()
    return float(res.data["balance_sek"]) if res.data else settings.STARTING_BALANCE_SEK


def update_account_balance(new_balance: float) -> None:
    db = get_db()
    db.table("account_state").update({"balance_sek": new_balance, "updated_at": "now()"}).eq("id", 1).execute()


def get_open_trades() -> list[dict]:
    db = get_db()
    res = db.table("paper_trades").select("*").eq("outcome", "OPEN").execute()
    return res.data or []


def open_trade_from_signal(signal: dict) -> dict | None:
    """Öppnar en paper trade om signalen är kvalificerad (BUY/SELL + tillräcklig confidence)."""
    if signal["decision"] == "NO_TRADE":
        return None
    if signal["confidence"] < MIN_CONFIDENCE_TO_TRADE:
        return None

    trade = {
        "signal_id": signal["id"],
        "symbol": signal["symbol"],
        "direction": signal["decision"],
        "entry_time": datetime.now(timezone.utc).isoformat(),
        "entry_price": signal["entry"],
        "stop_loss": signal["stop_loss"],
        "take_profit": signal["take_profit"],
        "position_size": signal.get("position_size_oz", 0.0),
        "risk_amount_sek": signal.get("risk_amount_sek", 0.0),
        "outcome": "OPEN",
    }
    saved = insert("paper_trades", [trade])
    if saved:
        insert("trade_events", [{
            "trade_id": saved[0]["id"],
            "event_type": "OPENED",
            "price": signal["entry"],
            "details": {"signal_id": signal["id"], "confidence": signal["confidence"]},
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


def monitor_open_trades(latest_candle: dict) -> list[dict]:
    """
    Går igenom alla öppna paper trades och stänger de som träffat SL/TP
    baserat på den senaste candlens high/low. Körs varje gång ny marknadsdata kommer in.
    """
    closed = []
    for trade in get_open_trades():
        hit = _check_sl_tp_hit(trade, latest_candle["high"], latest_candle["low"])
        if hit == "TP":
            closed.append(close_trade(trade, trade["take_profit"], "WIN"))
        elif hit == "SL":
            closed.append(close_trade(trade, trade["stop_loss"], "LOSS"))
    return closed

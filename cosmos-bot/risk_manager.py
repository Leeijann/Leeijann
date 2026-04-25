"""
risk_manager.py
───────────────
Handles all risk controls for HERMES-7:
  - ATR-based stop loss and take profit calculation
  - Per-trade position sizing (risk % of account)
  - Trade cooldown (prevent overtrading)
  - Paper trading mode (simulated P&L, no real orders)
  - Trade journal (log every trade for review)
"""

import json
import logging
import datetime
import os
from config import (
    PAPER_TRADING, TRADE_COOLDOWN_MINUTES, RISK_TABLE,
    SL_ATR_MULTIPLIER, TP_RR_RATIO, TRADE_LOG_FILE
)

log = logging.getLogger(__name__)

# ─── RUNTIME STATE ───────────────────────────────────────────────────────────

# {product_id: last_trade_datetime}
_cooldown_tracker: dict = {}

# Paper trading virtual portfolio
_paper_portfolio: dict = {
    "cash_usd":  1000.0,   # starting virtual balance
    "positions": {},        # {product_id: {size, entry_price, side}}
    "trades":    [],
    "pnl_total": 0.0,
}


# ─── STOP LOSS & TAKE PROFIT ─────────────────────────────────────────────────

def calculate_sl_tp(entry_price: float, atr: float, direction: str,
                    signal_class: str) -> dict:
    """
    ATR-based stop loss. Take profit uses configurable R:R ratio.
    OMEGA trades get a wider TP (3R), others use standard TP (2R).
    """
    sl_distance = atr * SL_ATR_MULTIPLIER
    tp_multiplier = 3.0 if signal_class == "OMEGA" else TP_RR_RATIO

    if direction == "LONG":
        stop_loss   = round(entry_price - sl_distance, 6)
        take_profit = round(entry_price + (sl_distance * tp_multiplier), 6)
    elif direction == "SHORT":
        stop_loss   = round(entry_price + sl_distance, 6)
        take_profit = round(entry_price - (sl_distance * tp_multiplier), 6)
    else:
        stop_loss   = None
        take_profit = None

    risk_per_unit = sl_distance
    reward_per_unit = sl_distance * tp_multiplier if stop_loss else 0

    return {
        "entry":        round(entry_price, 6),
        "stop_loss":    stop_loss,
        "take_profit":  take_profit,
        "sl_distance":  round(sl_distance, 6),
        "rr_ratio":     tp_multiplier,
        "risk_per_unit": round(risk_per_unit, 6),
        "reward_per_unit": round(reward_per_unit, 6),
    }


# ─── POSITION SIZING ─────────────────────────────────────────────────────────

def calculate_position_size(account_balance: float, signal_class: str,
                             sl_distance: float, price: float) -> dict:
    """
    Risk a fixed % of account per trade (from RISK_TABLE).
    Position size = (balance * risk_pct) / sl_distance_in_usd
    Returns both USD amount and base currency amount.
    """
    risk_pct = RISK_TABLE.get(signal_class, 0.0)
    if risk_pct == 0 or sl_distance <= 0:
        return {"usd_amount": 0.0, "base_amount": 0.0, "risk_pct": 0.0}

    risk_usd    = account_balance * risk_pct
    # Units to buy = risk_usd / sl_distance_per_unit
    base_amount = risk_usd / sl_distance
    usd_amount  = base_amount * price

    return {
        "usd_amount":  round(usd_amount, 2),
        "base_amount": round(base_amount, 8),
        "risk_pct":    risk_pct,
        "risk_usd":    round(risk_usd, 2),
    }


# ─── COOLDOWN ────────────────────────────────────────────────────────────────

def is_on_cooldown(product_id: str) -> tuple:
    """
    Returns (True, minutes_remaining) if asset is on cooldown, else (False, 0).
    Prevents overtrading the same asset.
    """
    if product_id not in _cooldown_tracker:
        return False, 0
    last = _cooldown_tracker[product_id]
    elapsed = (datetime.datetime.utcnow() - last).total_seconds() / 60
    remaining = TRADE_COOLDOWN_MINUTES - elapsed
    if remaining > 0:
        return True, round(remaining, 1)
    return False, 0


def set_cooldown(product_id: str):
    _cooldown_tracker[product_id] = datetime.datetime.utcnow()
    log.info(f"Cooldown set for {product_id} — {TRADE_COOLDOWN_MINUTES} min")


# ─── PAPER TRADING ───────────────────────────────────────────────────────────

def paper_buy(product_id: str, usd_amount: float, price: float,
              stop_loss: float, take_profit: float) -> dict:
    global _paper_portfolio
    if _paper_portfolio["cash_usd"] < usd_amount:
        return {"error": "Insufficient paper balance"}

    base_amount = round(usd_amount / price, 8)
    _paper_portfolio["cash_usd"] -= usd_amount
    _paper_portfolio["positions"][product_id] = {
        "side":         "LONG",
        "entry_price":  price,
        "size":         base_amount,
        "usd_value":    usd_amount,
        "stop_loss":    stop_loss,
        "take_profit":  take_profit,
        "opened_at":    str(datetime.datetime.utcnow()),
    }

    result = {
        "mode":         "PAPER",
        "action":       "BUY",
        "product_id":   product_id,
        "price":        price,
        "usd_amount":   usd_amount,
        "base_amount":  base_amount,
        "stop_loss":    stop_loss,
        "take_profit":  take_profit,
        "cash_remaining": round(_paper_portfolio["cash_usd"], 2),
    }
    _log_trade({**result, "status": "OPEN"})
    return result


def paper_sell(product_id: str, price: float, reason: str = "MANUAL") -> dict:
    global _paper_portfolio
    pos = _paper_portfolio["positions"].get(product_id)
    if not pos:
        return {"error": f"No open paper position for {product_id}"}

    pnl = (price - pos["entry_price"]) * pos["size"]
    pnl_pct = ((price - pos["entry_price"]) / pos["entry_price"]) * 100
    usd_returned = pos["usd_value"] + pnl

    _paper_portfolio["cash_usd"] += usd_returned
    _paper_portfolio["pnl_total"] += pnl
    del _paper_portfolio["positions"][product_id]

    result = {
        "mode":         "PAPER",
        "action":       "SELL",
        "product_id":   product_id,
        "entry_price":  pos["entry_price"],
        "exit_price":   price,
        "pnl_usd":      round(pnl, 2),
        "pnl_pct":      round(pnl_pct, 2),
        "reason":       reason,
        "cash_balance": round(_paper_portfolio["cash_usd"], 2),
        "total_pnl":    round(_paper_portfolio["pnl_total"], 2),
    }
    _log_trade({**result, "status": "CLOSED"})
    return result


def check_paper_exits(current_prices: dict) -> list:
    """
    Check all open paper positions against SL/TP.
    Call this on each price update.
    Returns list of closed trade results.
    """
    closed = []
    for product_id, pos in list(_paper_portfolio["positions"].items()):
        price = current_prices.get(product_id)
        if not price:
            continue
        if pos["side"] == "LONG":
            if pos["stop_loss"] and price <= pos["stop_loss"]:
                closed.append(paper_sell(product_id, price, "STOP_LOSS"))
            elif pos["take_profit"] and price >= pos["take_profit"]:
                closed.append(paper_sell(product_id, price, "TAKE_PROFIT"))
    return closed


def get_paper_status() -> dict:
    positions = _paper_portfolio["positions"]
    return {
        "mode":          "PAPER TRADING",
        "cash_usd":      round(_paper_portfolio["cash_usd"], 2),
        "open_positions": len(positions),
        "positions":     positions,
        "total_pnl":     round(_paper_portfolio["pnl_total"], 2),
        "trades_logged": len(_paper_portfolio["trades"]),
    }


# ─── TRADE JOURNAL ───────────────────────────────────────────────────────────

def _log_trade(trade: dict):
    """Append a trade to the JSON log file and in-memory list."""
    trade["logged_at"] = str(datetime.datetime.utcnow())
    _paper_portfolio["trades"].append(trade)
    try:
        existing = []
        if os.path.exists(TRADE_LOG_FILE):
            with open(TRADE_LOG_FILE, "r") as f:
                existing = json.load(f)
        existing.append(trade)
        with open(TRADE_LOG_FILE, "w") as f:
            json.dump(existing, f, indent=2)
    except Exception as e:
        log.error(f"Trade log write error: {e}")


def log_live_trade(action: str, product_id: str, price: float,
                   usd_amount: float, signal_class: str,
                   stop_loss: float = None, take_profit: float = None,
                   result: dict = None):
    """Log a real (live) trade to the trade journal."""
    trade = {
        "mode":         "LIVE",
        "action":       action,
        "product_id":   product_id,
        "price":        price,
        "usd_amount":   usd_amount,
        "signal_class": signal_class,
        "stop_loss":    stop_loss,
        "take_profit":  take_profit,
        "result":       result,
        "status":       "EXECUTED",
    }
    _log_trade(trade)


def get_trade_log(last_n: int = 10) -> list:
    """Return the last N trades from the log file."""
    try:
        if os.path.exists(TRADE_LOG_FILE):
            with open(TRADE_LOG_FILE, "r") as f:
                trades = json.load(f)
            return trades[-last_n:]
    except Exception as e:
        log.error(f"Trade log read error: {e}")
    return []


def format_trade_log_message(trades: list) -> str:
    if not trades:
        return "No trades logged yet."
    lines = ["=== TRADE JOURNAL (Last 10) ==="]
    for t in trades:
        lines.append(
            f"{t.get('logged_at','?')[:16]} | "
            f"{t.get('mode','?')} | "
            f"{t.get('action','?')} {t.get('product_id','?')} | "
            f"${t.get('usd_amount', t.get('pnl_usd','?'))} | "
            f"{t.get('status','?')}"
        )
    return "\n".join(lines)

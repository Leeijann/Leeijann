"""
telegram_handler.py
───────────────────
All Telegram bot commands and message routing.
Commands:
  /start        — Welcome message
  /status       — Cosmic snapshot for today
  /signal       — Full confluence signal (default BTC-USD)
  /signal ETH   — Signal for any coin
  /balance      — Coinbase account balances
  /price        — Current price
  /buy          — Market buy (e.g. /buy BTC-USD 50)
  /sell         — Market sell (e.g. /sell BTC-USD 50)
  /orders       — List open orders
  /paper        — Paper trading status and P&L
  /journal      — Last 10 trades from trade log
  /cooldown     — Show active cooldown timers
  /pause        — Disable auto-trading
  /resume       — Enable auto-trading
  /help         — Command list
"""

import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)
from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    DEFAULT_CRYPTO,
    AUTO_TRADE,
    PAPER_TRADING,
)
from coinbase_client import CoinbaseClient
from signal_generator import generate_signal, format_signal_message
from cosmos_engine import full_cosmic_report
from risk_manager import (
    get_paper_status, paper_buy, paper_sell,
    is_on_cooldown, set_cooldown,
    get_trade_log, format_trade_log_message,
    log_live_trade,
)

log = logging.getLogger(__name__)

# Mutable runtime flags
state = {"auto_trade": AUTO_TRADE, "paper_trading": PAPER_TRADING}


# ─── GUARD: only respond to the configured chat ──────────────────────────────

def _authorized(update: Update) -> bool:
    return str(update.effective_chat.id) == str(TELEGRAM_CHAT_ID)


async def _deny(update: Update):
    await update.message.reply_text("Unauthorized.")


# ─── /start ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return await _deny(update)
    mode = "PAPER TRADING" if state["paper_trading"] else "LIVE TRADING"
    await update.message.reply_text(
        f"HERMES-7 COSMOS TRADING BOT ONLINE\n"
        f"Mode: {mode}\n\n"
        "Commands:\n"
        "/status        — Cosmic + time snapshot\n"
        "/signal        — Full confluence signal (BTC default)\n"
        "/signal ETH-USD — Signal for any asset\n"
        "/balance       — Coinbase balances\n"
        "/price         — Current price\n"
        "/buy BTC-USD 50 — Buy $50\n"
        "/sell BTC-USD 50 — Sell $50\n"
        "/orders        — Open orders\n"
        "/paper         — Paper trading P&L\n"
        "/journal       — Last 10 trades\n"
        "/cooldown      — Active cooldowns\n"
        "/pause         — Stop auto-trading\n"
        "/resume        — Start auto-trading\n"
        "/help          — This list"
    )


# ─── /help ───────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)


# ─── /status ─────────────────────────────────────────────────────────────────

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return await _deny(update)

    await update.message.reply_text("Scanning the cosmos...")

    try:
        report = full_cosmic_report()
        moon   = report["moon"]
        retro  = "YES — Mercury Retrograde, trade carefully" if report["mercury_retrograde"] else "No"
        caution = f"YES — {report['eclipse_proximity_days']} days from eclipse" if report["eclipse_caution"] else "Clear"

        top_aspects = "\n".join(
            f"  {a['planets']} {a['aspect']} score={a['score']}"
            for a in report["active_aspects"][:5]
        ) or "  None"

        planet_pos = "\n".join(
            f"  {k:10s}: {v:.1f}°"
            for k, v in report["planet_positions"].items()
        )

        msg = (
            f"=== COSMIC SNAPSHOT ===\n"
            f"Date       : {report['date']}\n"
            f"Aspect Score: {report['aspect_score']} ({report['cosmic_bias']})\n"
            f"Moon Phase : {moon['phase']} (day {moon['day_in_cycle']})\n"
            f"Moon Bias  : {moon['bias']}\n"
            f"Mercury    : {retro}\n"
            f"Eclipse    : {caution}\n"
            f"Sun Sign   : {report['sun_sign']['sign']} — {report['sun_sign']['sector']}\n"
            f"\nTop Aspects:\n{top_aspects}\n"
            f"\nPlanet Longitudes:\n{planet_pos}"
        )
        await update.message.reply_text(msg)

    except Exception as e:
        log.error(f"cmd_status error: {e}")
        await update.message.reply_text(f"Error fetching cosmic data: {e}")


# ─── /signal ─────────────────────────────────────────────────────────────────

async def cmd_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return await _deny(update)

    product_id = context.args[0].upper() if context.args else DEFAULT_CRYPTO
    # Normalize: BTC -> BTC-USD
    if "-" not in product_id:
        product_id = f"{product_id}-USD"

    await update.message.reply_text(f"Generating COSMOS signal for {product_id}...")

    try:
        sig = generate_signal(product_id)
        msg = format_signal_message(sig)
        await update.message.reply_text(msg)

        if not state["auto_trade"]:
            return
        if sig.get("signal_class") not in ("OMEGA", "ALPHA"):
            return
        if sig["direction"] != "LONG":
            return

        # Check cooldown
        on_cd, mins_left = is_on_cooldown(product_id)
        if on_cd:
            await update.message.reply_text(
                f"Cooldown active for {product_id} — {mins_left} min remaining. Skipping."
            )
            return

        cb        = CoinbaseClient()
        usd_bal   = cb.get_balance("USD") if not state["paper_trading"] else 1000.0
        trade_amt = round(usd_bal * sig["risk_pct"], 2)
        sl        = sig.get("stop_loss")
        tp        = sig.get("take_profit")

        if trade_amt < 1.0:
            await update.message.reply_text("Trade amount too small (< $1). Skipping.")
            return

        if state["paper_trading"]:
            result = paper_buy(product_id, trade_amt, sig["current_price"], sl, tp)
            await update.message.reply_text(
                f"[PAPER] AUTO-BUY {product_id}\n"
                f"Amount : ${trade_amt}\n"
                f"Price  : ${sig['current_price']:,.4f}\n"
                f"SL     : ${sl:,.4f}\n" if sl else ""
                f"TP     : ${tp:,.4f}\n" if tp else ""
                f"Cash left: ${result.get('cash_remaining','?')}"
            )
        else:
            result = cb.execute_full_trade(product_id, trade_amt, sl, tp)
            log_live_trade("BUY", product_id, sig["current_price"],
                           trade_amt, sig["signal_class"], sl, tp, result)
            await update.message.reply_text(
                f"[LIVE] AUTO-BUY {product_id}\n"
                f"Amount    : ${trade_amt}\n"
                f"Stop Loss : ${sl:,.4f}\n" if sl else ""
                f"Take Profit: ${tp:,.4f}\n" if tp else ""
                f"Result: {result.get('buy', {}).get('success', '?')}"
            )

        set_cooldown(product_id)

    except Exception as e:
        log.error(f"cmd_signal error: {e}")
        await update.message.reply_text(f"Signal error: {e}")


# ─── /balance ────────────────────────────────────────────────────────────────

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return await _deny(update)
    try:
        cb = CoinbaseClient()
        accounts = cb.get_accounts()
        if not accounts:
            await update.message.reply_text("No balances found or API error.")
            return
        lines = ["=== COINBASE BALANCES ==="]
        for a in accounts:
            lines.append(f"  {a['currency']:10s}: {a['balance']}")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        log.error(f"cmd_balance error: {e}")
        await update.message.reply_text(f"Balance error: {e}")


# ─── /price ──────────────────────────────────────────────────────────────────

async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return await _deny(update)
    product_id = context.args[0].upper() if context.args else DEFAULT_CRYPTO
    if "-" not in product_id:
        product_id = f"{product_id}-USD"
    try:
        cb = CoinbaseClient()
        p = cb.get_price(product_id)
        if p:
            await update.message.reply_text(
                f"{product_id}\n"
                f"  Bid : ${p['bid']:,.2f}\n"
                f"  Ask : ${p['ask']:,.2f}\n"
                f"  Mid : ${p['mid']:,.2f}"
            )
        else:
            await update.message.reply_text(f"Could not fetch price for {product_id}.")
    except Exception as e:
        log.error(f"cmd_price error: {e}")
        await update.message.reply_text(f"Price error: {e}")


# ─── /buy ────────────────────────────────────────────────────────────────────

async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return await _deny(update)
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /buy BTC-USD 50")
        return
    product_id = context.args[0].upper()
    if "-" not in product_id:
        product_id = f"{product_id}-USD"
    try:
        amount = float(context.args[1])
    except ValueError:
        await update.message.reply_text("Amount must be a number. Example: /buy BTC-USD 50")
        return
    try:
        cb = CoinbaseClient()
        result = cb.market_buy(product_id, amount)
        await update.message.reply_text(
            f"BUY ORDER PLACED\n"
            f"Asset : {product_id}\n"
            f"Amount: ${amount}\n"
            f"Result: {result}"
        )
    except Exception as e:
        log.error(f"cmd_buy error: {e}")
        await update.message.reply_text(f"Buy error: {e}")


# ─── /sell ───────────────────────────────────────────────────────────────────

async def cmd_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return await _deny(update)
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /sell BTC-USD 50")
        return
    product_id = context.args[0].upper()
    if "-" not in product_id:
        product_id = f"{product_id}-USD"
    try:
        amount = float(context.args[1])
    except ValueError:
        await update.message.reply_text("Amount must be a number. Example: /sell BTC-USD 50")
        return
    try:
        cb = CoinbaseClient()
        result = cb.market_sell(product_id, amount)
        await update.message.reply_text(
            f"SELL ORDER PLACED\n"
            f"Asset : {product_id}\n"
            f"Amount: ~${amount}\n"
            f"Result: {result}"
        )
    except Exception as e:
        log.error(f"cmd_sell error: {e}")
        await update.message.reply_text(f"Sell error: {e}")


# ─── /orders ─────────────────────────────────────────────────────────────────

async def cmd_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return await _deny(update)
    try:
        cb = CoinbaseClient()
        orders = cb.list_open_orders()
        if not orders:
            await update.message.reply_text("No open orders.")
            return
        lines = ["=== OPEN ORDERS ==="]
        for o in orders:
            lines.append(
                f"  {o.get('product_id')} {o.get('side')} "
                f"${o.get('order_configuration', {}).get('market_market_ioc', {}).get('quote_size', '?')} "
                f"status={o.get('status')}"
            )
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        log.error(f"cmd_orders error: {e}")
        await update.message.reply_text(f"Orders error: {e}")


# ─── /paper ──────────────────────────────────────────────────────────────────

async def cmd_paper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return await _deny(update)
    status = get_paper_status()
    lines = [
        "=== PAPER TRADING STATUS ===",
        f"Cash Balance  : ${status['cash_usd']:,.2f}",
        f"Total P&L     : ${status['total_pnl']:,.2f}",
        f"Open Positions: {status['open_positions']}",
        f"Trades Logged : {status['trades_logged']}",
    ]
    if status["positions"]:
        lines.append("\nOpen Positions:")
        for pid, pos in status["positions"].items():
            lines.append(
                f"  {pid}: {pos['side']} {pos['size']} @ ${pos['entry_price']:,.4f}"
                f" | SL: ${pos.get('stop_loss','?')} | TP: ${pos.get('take_profit','?')}"
            )
    await update.message.reply_text("\n".join(lines))


# ─── /journal ────────────────────────────────────────────────────────────────

async def cmd_journal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return await _deny(update)
    trades = get_trade_log(10)
    msg = format_trade_log_message(trades)
    await update.message.reply_text(msg)


# ─── /cooldown ───────────────────────────────────────────────────────────────

async def cmd_cooldown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return await _deny(update)
    from risk_manager import _cooldown_tracker
    import datetime
    if not _cooldown_tracker:
        await update.message.reply_text("No active cooldowns.")
        return
    from config import TRADE_COOLDOWN_MINUTES
    lines = ["=== ACTIVE COOLDOWNS ==="]
    for pid, last in _cooldown_tracker.items():
        elapsed = (datetime.datetime.utcnow() - last).total_seconds() / 60
        remaining = TRADE_COOLDOWN_MINUTES - elapsed
        if remaining > 0:
            lines.append(f"  {pid}: {remaining:.1f} min remaining")
    if len(lines) == 1:
        lines.append("  All cooldowns expired.")
    await update.message.reply_text("\n".join(lines))


# ─── /pause / /resume ────────────────────────────────────────────────────────

async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return await _deny(update)
    state["auto_trade"] = False
    await update.message.reply_text("Auto-trading PAUSED. No automatic orders will be placed.")


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return await _deny(update)
    state["auto_trade"] = True
    mode = "PAPER" if state["paper_trading"] else "LIVE"
    await update.message.reply_text(
        f"Auto-trading RESUMED in {mode} mode.\n"
        "OMEGA and ALPHA signals will trigger orders."
    )


# ─── BOT BUILDER ─────────────────────────────────────────────────────────────

def build_application():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CommandHandler("status",   cmd_status))
    app.add_handler(CommandHandler("signal",   cmd_signal))
    app.add_handler(CommandHandler("balance",  cmd_balance))
    app.add_handler(CommandHandler("price",    cmd_price))
    app.add_handler(CommandHandler("buy",      cmd_buy))
    app.add_handler(CommandHandler("sell",     cmd_sell))
    app.add_handler(CommandHandler("orders",   cmd_orders))
    app.add_handler(CommandHandler("paper",    cmd_paper))
    app.add_handler(CommandHandler("journal",  cmd_journal))
    app.add_handler(CommandHandler("cooldown", cmd_cooldown))
    app.add_handler(CommandHandler("pause",    cmd_pause))
    app.add_handler(CommandHandler("resume",   cmd_resume))

    return app

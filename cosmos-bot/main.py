"""
main.py
───────
Entry point for HERMES-7 Cosmos Trading Bot.

Run:  python main.py

The bot starts a Telegram polling loop and a background scheduler
that fires a cosmic signal check every 4 hours automatically.
"""

import logging
import threading
import time
import schedule
from telegram.ext import Application
from telegram_handler import build_application
from signal_generator import generate_signal, format_signal_message
from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    DEFAULT_CRYPTO,
    LOG_LEVEL,
)

# ─── LOGGING ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=getattr(logging, LOG_LEVEL, logging.INFO),
)
log = logging.getLogger("HERMES-7")


# ─── STARTUP VALIDATION ──────────────────────────────────────────────────────

def validate_config():
    missing = []
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_telegram_bot_token_here":
        missing.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "your_telegram_chat_id_here":
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        raise SystemExit(
            f"\nMissing required .env variables: {', '.join(missing)}\n"
            "Copy .env.template to .env and fill in your keys.\n"
        )
    log.info("Config validated.")


# ─── SCHEDULED SIGNAL BROADCAST ──────────────────────────────────────────────

_app_ref: Application = None


def scheduled_signal_job():
    """Runs on schedule — generates a signal and sends it to Telegram."""
    if _app_ref is None:
        return
    try:
        log.info(f"Scheduled signal check for {DEFAULT_CRYPTO}")
        sig = generate_signal(DEFAULT_CRYPTO)
        msg = f"[SCHEDULED SCAN]\n\n{format_signal_message(sig)}"

        # Use the bot's send_message directly (sync call via run_coroutine)
        import asyncio
        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            _app_ref.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
        )
        loop.close()
    except Exception as e:
        log.error(f"Scheduled signal error: {e}")


def run_scheduler():
    """Background thread running the schedule loop."""
    # Fire at market-relevant times (every 4 hours)
    schedule.every(4).hours.do(scheduled_signal_job)
    # Also fire once at startup after a short delay
    schedule.every(10).seconds.do(scheduled_signal_job).tag("startup")

    log.info("Scheduler started — signal checks every 4 hours.")
    while True:
        schedule.run_pending()
        # Remove the one-time startup job after first run
        if not schedule.get_jobs("startup"):
            pass
        else:
            jobs = schedule.get_jobs("startup")
            for j in jobs:
                if j.last_run:
                    schedule.cancel_job(j)
        time.sleep(30)


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    global _app_ref

    validate_config()

    log.info("Building Telegram application...")
    app = build_application()
    _app_ref = app

    # Start the scheduler in a background thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    log.info("HERMES-7 is ONLINE. Listening for Telegram commands...")
    log.info(f"Send /start to your bot to begin.")

    # Start the Telegram polling loop (blocking)
    app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()

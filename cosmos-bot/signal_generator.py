"""
signal_generator.py
───────────────────
Fuses cosmic data + price data into a classified trade signal.
Signal classes: OMEGA / ALPHA / BETA / GAMMA / VOID
"""

import logging
from cosmos_engine import (
    full_cosmic_report,
    calculate_fibonacci_levels,
    nearest_fibonacci_level,
    gann_square_of_9,
)
from coinbase_client import CoinbaseClient
from config import (
    OMEGA_THRESHOLD, ALPHA_THRESHOLD, BETA_THRESHOLD, VOID_THRESHOLD, RISK_TABLE
)

log = logging.getLogger(__name__)


def classify_signal(score: int, criteria_met: int, mercury_retro: bool,
                    eclipse_caution: bool) -> str:
    """
    Classify signal based on cosmic score, criteria count, and caution flags.
    """
    # VOID condition — stand aside completely
    if mercury_retro and eclipse_caution and score <= VOID_THRESHOLD:
        return "VOID"

    if score >= OMEGA_THRESHOLD and criteria_met >= 3:
        return "OMEGA"
    elif score >= ALPHA_THRESHOLD and criteria_met >= 2:
        return "ALPHA"
    elif score >= BETA_THRESHOLD and criteria_met >= 1:
        return "BETA"
    else:
        return "GAMMA"


def generate_signal(product_id="BTC-USD", date=None):
    """
    Master signal generation function.
    Returns a full signal dict ready for Telegram formatting.
    """
    cb = CoinbaseClient()

    # 1. Cosmic report
    report = full_cosmic_report(date)
    score = report["aspect_score"]
    moon = report["moon"]
    retro = report["mercury_retrograde"]
    eclipse_caution = report["eclipse_caution"]

    # 2. Price data
    price_data = cb.get_price(product_id)
    if not price_data:
        return {"error": f"Could not fetch price for {product_id}"}
    current_price = price_data["mid"]

    # 3. Swing high/low (50 candles)
    swing_low, swing_high = cb.get_swing_high_low(product_id)
    fib_label, fib_level, fib_dist_pct = None, None, None
    fib_levels = {}
    near_fib = False

    if swing_low and swing_high:
        fib_label, fib_level, fib_dist_pct = nearest_fibonacci_level(
            current_price, swing_low, swing_high
        )
        fib_levels = calculate_fibonacci_levels(swing_low, swing_high)
        near_fib = fib_dist_pct <= 0.5  # within 0.5% of a Fib level

    # 4. Gann Square of 9 levels
    gann_levels = gann_square_of_9(current_price)

    # 5. Count criteria met
    criteria_met = 0
    criteria_detail = []

    # Criterion A: Cosmic score directional
    if score >= ALPHA_THRESHOLD or score <= VOID_THRESHOLD:
        criteria_met += 1
        criteria_detail.append(f"Cosmic score {score} ({report['cosmic_bias']})")

    # Criterion B: Near Fibonacci level
    if near_fib:
        criteria_met += 1
        criteria_detail.append(f"Price near Fib {fib_label} ({fib_dist_pct}% away)")

    # Criterion C: Moon phase supports direction
    moon_phase = moon["phase"]
    bullish_phases = ["New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous"]
    bearish_phases = ["Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent"]
    moon_aligned = (
        (moon_phase in bullish_phases and score > 0) or
        (moon_phase in bearish_phases and score < 0)
    )
    if moon_aligned:
        criteria_met += 1
        criteria_detail.append(f"Moon phase aligned ({moon_phase})")

    # Criterion D: Not in eclipse caution window
    if not eclipse_caution:
        criteria_met += 1
        criteria_detail.append("No eclipse proximity")

    # 6. Classify
    signal_class = classify_signal(score, criteria_met, retro, eclipse_caution)
    risk_pct = RISK_TABLE[signal_class]

    # 7. Suggested direction
    if score > 0 and moon_phase in bullish_phases:
        direction = "LONG"
    elif score < 0 and moon_phase in bearish_phases:
        direction = "SHORT"
    else:
        direction = "NEUTRAL"

    return {
        "product_id":        product_id,
        "signal_class":      signal_class,
        "direction":         direction,
        "risk_pct":          risk_pct,
        "current_price":     current_price,
        "cosmic_score":      score,
        "cosmic_bias":       report["cosmic_bias"],
        "moon_phase":        moon_phase,
        "moon_bias":         moon["bias"],
        "mercury_retrograde": retro,
        "eclipse_caution":   eclipse_caution,
        "eclipse_days":      report["eclipse_proximity_days"],
        "criteria_met":      criteria_met,
        "criteria_detail":   criteria_detail,
        "active_aspects":    report["active_aspects"][:5],  # top 5 aspects
        "sun_sign":          report["sun_sign"],
        "swing_low":         swing_low,
        "swing_high":        swing_high,
        "nearest_fib":       {"label": fib_label, "level": fib_level, "dist_pct": fib_dist_pct},
        "gann_levels":       gann_levels,
        "fib_levels":        fib_levels,
    }


def format_signal_message(sig: dict) -> str:
    """Format a signal dict into a clean Telegram message."""
    if "error" in sig:
        return f"ERROR: {sig['error']}"

    cls = sig["signal_class"]
    emoji_map = {
        "OMEGA": "OMEGA",
        "ALPHA": "ALPHA",
        "BETA":  "BETA",
        "GAMMA": "GAMMA",
        "VOID":  "VOID",
    }

    lines = [
        f"=== COSMOS SIGNAL REPORT ===",
        f"Asset     : {sig['product_id']}",
        f"Class     : {emoji_map.get(cls, cls)}",
        f"Direction : {sig['direction']}",
        f"Risk      : {sig['risk_pct'] * 100:.2f}% of account",
        f"Price     : ${sig['current_price']:,.2f}",
        "",
        f"--- COSMIC DATA ---",
        f"Aspect Score : {sig['cosmic_score']} ({sig['cosmic_bias']})",
        f"Moon Phase   : {sig['moon_phase']} — {sig['moon_bias']}",
        f"Mercury Retro: {'YES — CAUTION' if sig['mercury_retrograde'] else 'No'}",
        f"Eclipse Caution: {'YES ({:.1f} days)'.format(sig['eclipse_days']) if sig['eclipse_caution'] else 'Clear'}",
        f"Sun in       : {sig['sun_sign']['sign']} ({sig['sun_sign']['sector']})",
        "",
        f"--- CRITERIA MET: {sig['criteria_met']}/4 ---",
    ]

    for c in sig["criteria_detail"]:
        lines.append(f"  + {c}")

    if sig["nearest_fib"]["label"]:
        lines.append("")
        lines.append(f"--- FIBONACCI ---")
        lines.append(f"Nearest Level : {sig['nearest_fib']['label']}")
        lines.append(f"Level Price   : ${sig['nearest_fib']['level']:,.2f}")
        lines.append(f"Distance      : {sig['nearest_fib']['dist_pct']}%")

    lines.append("")
    lines.append(f"--- GANN SQUARE OF 9 ---")
    for label, val in sorted(sig["gann_levels"].items()):
        lines.append(f"  {label:12s}: ${val:,.2f}")

    if sig["active_aspects"]:
        lines.append("")
        lines.append(f"--- TOP ASPECTS ---")
        for a in sig["active_aspects"]:
            lines.append(f"  {a['planets']} — {a['aspect']} ({a['angle']}°) score={a['score']}")

    if cls == "VOID":
        lines.append("")
        lines.append("!!! VOID — NO TRADE. STAND ASIDE !!!")

    return "\n".join(lines)

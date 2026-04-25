"""
signal_generator.py
───────────────────
Fuses COSMIC score + TECHNICAL score + TIME BRAIN into a unified signal.

Entry requires CONFLUENCE across all three layers:
  1. Cosmic score (planetary aspects + temporal brain)
  2. Technical score (RSI + MACD + Bollinger + EMA + Volume)
  3. Direction agreement (both layers pointing the same way)

Signal classes: OMEGA / ALPHA / BETA / GAMMA / VOID
"""

import logging
from cosmos_engine import (
    full_cosmic_report,
    calculate_fibonacci_levels,
    nearest_fibonacci_level,
    gann_square_of_9,
)
from technical_analysis import candles_to_dataframe, score_technicals
from coinbase_client import CoinbaseClient
from config import (
    OMEGA_THRESHOLD, ALPHA_THRESHOLD, BETA_THRESHOLD,
    VOID_THRESHOLD, RISK_TABLE, TA_MIN_SCORE,
    TA_CANDLE_GRANULARITY, TA_CANDLE_LIMIT,
)

log = logging.getLogger(__name__)


# ─── SIGNAL CLASSIFICATION ───────────────────────────────────────────────────

def classify_signal(combined_score: int, ta_score: int, criteria_met: int,
                    mercury_retro: bool, eclipse_caution: bool,
                    directions_agree: bool) -> str:
    """
    VOID  — Mercury retro + eclipse + score <= threshold OR TA says opposite
    OMEGA — Combined score >= 15, TA score >= 4, criteria >= 3, agree
    ALPHA — Combined score >= 8,  TA score >= 2, criteria >= 2, agree
    BETA  — Combined score >= 2,  TA score >= 1, criteria >= 1
    GAMMA — Everything else (analysis only, no trade)
    """
    if mercury_retro and eclipse_caution and combined_score <= VOID_THRESHOLD:
        return "VOID"

    if not directions_agree:
        return "GAMMA"

    if combined_score >= OMEGA_THRESHOLD and ta_score >= 4 and criteria_met >= 3:
        return "OMEGA"
    elif combined_score >= ALPHA_THRESHOLD and ta_score >= TA_MIN_SCORE and criteria_met >= 2:
        return "ALPHA"
    elif combined_score >= BETA_THRESHOLD and ta_score >= 1 and criteria_met >= 1:
        return "BETA"
    return "GAMMA"


# ─── MAIN SIGNAL GENERATOR ───────────────────────────────────────────────────

def generate_signal(product_id="BTC-USD", date=None) -> dict:
    """
    Full confluence signal: cosmic + technical + time brain.
    Returns a structured dict ready for Telegram formatting and trade execution.
    """
    cb = CoinbaseClient()

    # ── 1. COSMIC REPORT ─────────────────────────────────────────────────────
    report = full_cosmic_report(date)
    cosmic_score    = report["aspect_score"]
    temporal_score  = report["temporal_score"]
    combined_score  = report["combined_score"]
    moon            = report["moon"]
    retro           = report["mercury_retrograde"]
    eclipse_caution = report["eclipse_caution"]
    brain           = report["brain"]

    # ── 2. PRICE DATA ────────────────────────────────────────────────────────
    price_data = cb.get_price(product_id)
    if not price_data:
        return {"error": f"Could not fetch price for {product_id}"}
    current_price = price_data["mid"]

    # ── 3. TECHNICAL ANALYSIS ────────────────────────────────────────────────
    candles = cb.get_candles(product_id, TA_CANDLE_GRANULARITY, TA_CANDLE_LIMIT)
    ta = {}
    if candles:
        df  = candles_to_dataframe(candles)
        ta  = score_technicals(df)
    ta_score     = ta.get("ta_score", 0)
    ta_direction = ta.get("direction", "NEUTRAL")
    ta_regime    = ta.get("regime", "UNKNOWN")
    atr_val      = ta.get("atr", 0.0)

    # ── 4. SWING HIGH / LOW (Fibonacci) ──────────────────────────────────────
    swing_low, swing_high = cb.get_swing_high_low(product_id)
    fib_label, fib_level, fib_dist_pct = None, None, None
    fib_levels = {}
    near_fib   = False

    if swing_low and swing_high:
        fib_label, fib_level, fib_dist_pct = nearest_fibonacci_level(
            current_price, swing_low, swing_high
        )
        fib_levels = calculate_fibonacci_levels(swing_low, swing_high)
        near_fib   = fib_dist_pct <= 0.5

    # ── 5. GANN SQUARE OF 9 ──────────────────────────────────────────────────
    gann_levels = gann_square_of_9(current_price)

    # ── 6. DIRECTION LOGIC ───────────────────────────────────────────────────
    moon_phase    = moon["phase"]
    bullish_phases = ["New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous"]
    bearish_phases = ["Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent"]

    cosmic_direction = (
        "LONG"  if combined_score > 0 and moon_phase in bullish_phases else
        "SHORT" if combined_score < 0 and moon_phase in bearish_phases else
        "NEUTRAL"
    )

    # Directions agree when both cosmic and TA point the same way
    directions_agree = (
        cosmic_direction == ta_direction and
        cosmic_direction != "NEUTRAL"
    )

    final_direction = cosmic_direction if directions_agree else "NEUTRAL"

    # ── 7. CRITERIA COUNT ────────────────────────────────────────────────────
    criteria_met    = 0
    criteria_detail = []

    if combined_score >= ALPHA_THRESHOLD or combined_score <= VOID_THRESHOLD:
        criteria_met += 1
        criteria_detail.append(f"Cosmic combined score {combined_score} ({report['cosmic_bias']})")

    if near_fib:
        criteria_met += 1
        criteria_detail.append(f"Price near Fibonacci {fib_label} ({fib_dist_pct}% away)")

    if moon_phase in bullish_phases and combined_score > 0:
        criteria_met += 1
        criteria_detail.append(f"Moon phase aligned bullish ({moon_phase})")
    elif moon_phase in bearish_phases and combined_score < 0:
        criteria_met += 1
        criteria_detail.append(f"Moon phase aligned bearish ({moon_phase})")

    if not eclipse_caution:
        criteria_met += 1
        criteria_detail.append("No eclipse proximity — clear window")

    if ta_score >= TA_MIN_SCORE and ta_direction != "NEUTRAL":
        criteria_detail.append(f"TA confirms: score={ta_score} direction={ta_direction}")

    # ── 8. CLASSIFY ──────────────────────────────────────────────────────────
    signal_class = classify_signal(
        combined_score, ta_score, criteria_met,
        retro, eclipse_caution, directions_agree
    )
    risk_pct = RISK_TABLE[signal_class]

    # ── 9. STOP LOSS / TAKE PROFIT ───────────────────────────────────────────
    from risk_manager import calculate_sl_tp
    sl_tp = calculate_sl_tp(current_price, atr_val, final_direction, signal_class)

    return {
        # Core
        "product_id":     product_id,
        "signal_class":   signal_class,
        "direction":      final_direction,
        "risk_pct":       risk_pct,
        "current_price":  current_price,
        # Scores
        "cosmic_score":      cosmic_score,
        "temporal_score":    temporal_score,
        "combined_score":    combined_score,
        "ta_score":          ta_score,
        "cosmic_bias":       report["cosmic_bias"],
        "directions_agree":  directions_agree,
        # Moon
        "moon_phase":        moon_phase,
        "moon_bias":         moon["bias"],
        "moon_illumination": brain["moon"]["illumination_pct"],
        "moon_symbol":       brain["moon"]["symbol"],
        # Retrograde & eclipse
        "mercury_retrograde":  retro,
        "retrograde_planets":  report["retrograde_planets"],
        "eclipse_caution":     eclipse_caution,
        "eclipse_days":        report["eclipse_proximity_days"],
        # Criteria
        "criteria_met":    criteria_met,
        "criteria_detail": criteria_detail,
        # Aspects
        "active_aspects":  report["active_aspects"][:5],
        "sun_sign":        report["sun_sign"],
        # Fibonacci & Gann
        "swing_low":   swing_low,
        "swing_high":  swing_high,
        "nearest_fib": {"label": fib_label, "level": fib_level, "dist_pct": fib_dist_pct},
        "gann_levels": gann_levels,
        "fib_levels":  fib_levels,
        # Technical analysis
        "ta": ta,
        "ta_regime":     ta_regime,
        # Stop loss / take profit
        "stop_loss":     sl_tp["stop_loss"],
        "take_profit":   sl_tp["take_profit"],
        "sl_distance":   sl_tp["sl_distance"],
        "rr_ratio":      sl_tp["rr_ratio"],
        "atr":           atr_val,
        # Time brain
        "time_of_day":        brain["time_of_day"]["segment"],
        "market_energy":      brain["time_of_day"]["market_energy"],
        "season":             brain["season"]["season"],
        "season_tendency":    brain["season"]["market_tendency"],
        "solar_term":         brain["solar_term"]["solar_term"],
        "solar_term_meaning": brain["solar_term"]["meaning"],
        "day_ruler":          brain["day_ruler"]["ruler"],
        "planetary_hour":     brain["planetary_hour"]["ruling_planet"],
        "market_session":     brain["market_session"]["active_sessions"],
        "liquidity":          brain["market_session"]["liquidity"],
        "moonrise_utc":       brain["moon"]["moonrise_utc"],
        "moonset_utc":        brain["moon"]["moonset_utc"],
        "sunrise_utc":        brain["time_of_day"]["sunrise_utc"],
        "sunset_utc":         brain["time_of_day"]["sunset_utc"],
    }


# ─── TELEGRAM MESSAGE FORMATTER ──────────────────────────────────────────────

def format_signal_message(sig: dict) -> str:
    if "error" in sig:
        return f"ERROR: {sig['error']}"

    cls    = sig["signal_class"]
    ta     = sig.get("ta", {})
    retros = ", ".join(sig.get("retrograde_planets", [])) or "None"

    agree_str = "YES — Both layers aligned" if sig["directions_agree"] else "NO — Conflicting signals"

    lines = [
        f"=== HERMES-7 SIGNAL REPORT ===",
        f"Asset      : {sig['product_id']}",
        f"Class      : {cls}",
        f"Direction  : {sig['direction']}",
        f"Confluence : {agree_str}",
        f"Risk       : {sig['risk_pct'] * 100:.2f}% of account",
        f"Price      : ${sig['current_price']:,.4f}",
        "",
        f"--- SCORES ---",
        f"Cosmic Aspects : {sig['cosmic_score']}",
        f"Temporal Brain : {sig['temporal_score']}",
        f"Combined Cosmic: {sig['combined_score']} ({sig['cosmic_bias']})",
        f"Technical (TA) : {sig['ta_score']} ({ta.get('strength','?')}) — {ta.get('direction','?')}",
        f"Market Regime  : {sig['ta_regime']}",
        "",
        f"--- TECHNICAL INDICATORS ---",
        f"RSI        : {ta.get('rsi','?')}",
        f"MACD Cross : {ta.get('macd_cross','?')}",
        f"MACD Hist  : {ta.get('macd_hist','?')}",
        f"BB Upper   : ${ta.get('bb_upper',0):,.4f}",
        f"BB Mid     : ${ta.get('bb_mid',0):,.4f}",
        f"BB Lower   : ${ta.get('bb_lower',0):,.4f}",
        f"EMA 8/21/55: {ta.get('ema8',0):,.2f} / {ta.get('ema21',0):,.2f} / {ta.get('ema55',0):,.2f}",
        f"ADX        : {ta.get('adx','?')}",
        f"ATR        : {sig.get('atr',0):.4f}",
        f"Volume OK  : {'Yes' if ta.get('volume_ok') else 'No'}",
    ]

    if ta.get("signals"):
        lines.append("")
        lines.append("TA Signals:")
        for s in ta["signals"]:
            lines.append(f"  • {s}")

    lines += [
        "",
        f"--- STOP LOSS / TAKE PROFIT ---",
        f"Stop Loss  : ${sig.get('stop_loss',0):,.4f}" if sig.get('stop_loss') else "Stop Loss  : N/A",
        f"Take Profit: ${sig.get('take_profit',0):,.4f}" if sig.get('take_profit') else "Take Profit: N/A",
        f"R:R Ratio  : 1:{sig.get('rr_ratio',0):.1f}",
        "",
        f"--- MOON & TIME ---",
        f"Moon       : {sig['moon_phase']} [{sig.get('moon_symbol','?')}] {sig.get('moon_illumination',0):.1f}%",
        f"Moon Bias  : {sig['moon_bias']}",
        f"Moonrise   : {sig.get('moonrise_utc','N/A')} UTC  |  Moonset: {sig.get('moonset_utc','N/A')} UTC",
        f"Time       : {sig.get('time_of_day','?')}  |  Session: {', '.join(sig.get('market_session',['?']))}",
        f"Liquidity  : {sig.get('liquidity','?')}",
        f"Season     : {sig.get('season','?')} — {sig.get('season_tendency','')}",
        f"Solar Term : {sig.get('solar_term','?')}",
        f"Day Ruler  : {sig.get('day_ruler','?')}  |  Hour Ruler: {sig.get('planetary_hour','?')}",
        f"Retrograde : {retros}",
        f"Eclipse    : {'CAUTION — {:.1f}d'.format(sig['eclipse_days']) if sig['eclipse_caution'] else 'Clear'}",
        f"Sun in     : {sig['sun_sign']['sign']} ({sig['sun_sign']['sector']})",
        "",
        f"--- CRITERIA MET: {sig['criteria_met']}/4 ---",
    ]

    for c in sig["criteria_detail"]:
        lines.append(f"  + {c}")

    if sig["nearest_fib"]["label"]:
        lines += [
            "",
            f"--- FIBONACCI ---",
            f"Nearest: {sig['nearest_fib']['label']} @ ${sig['nearest_fib']['level']:,.4f}  ({sig['nearest_fib']['dist_pct']}% away)",
        ]

    lines += ["", "--- GANN SQUARE OF 9 ---"]
    for label, val in sorted(sig["gann_levels"].items()):
        lines.append(f"  {label:12s}: ${val:,.2f}")

    if sig["active_aspects"]:
        lines += ["", "--- TOP ASPECTS ---"]
        for a in sig["active_aspects"]:
            lines.append(f"  {a['planets']} — {a['aspect']} ({a['angle']}°) score={a['score']}")

    if cls == "VOID":
        lines += ["", "!!! VOID — NO TRADE. STAND ASIDE !!!"]

    return "\n".join(lines)

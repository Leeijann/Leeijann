"""
technical_analysis.py
─────────────────────
Computes RSI, MACD, Bollinger Bands, EMA stack, ATR, ADX and Volume
from Coinbase candle data. Returns a structured TA signal that the
signal_generator fuses with the cosmic score for high-confluence entries.

Indicator logic (Gate.io 2026 analysis — 77% win rate):
  LONG  when: RSI < 50 rising + MACD bullish cross + price near/below lower BB
  SHORT when: RSI > 50 falling + MACD bearish cross + price near/above upper BB
  Regime: ADX > 25 = trending (use MACD/EMA), ADX < 20 = ranging (use RSI/BB)
"""

import logging
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator, ADXIndicator
from ta.volatility import BollingerBands, AverageTrueRange

log = logging.getLogger(__name__)


# ─── CANDLE PARSER ───────────────────────────────────────────────────────────

def candles_to_dataframe(candles: list) -> pd.DataFrame:
    """
    Convert Coinbase candle list to a pandas DataFrame sorted oldest-first.
    Coinbase returns candles newest-first.
    """
    rows = []
    for c in candles:
        rows.append({
            "open":   float(c["open"]),
            "high":   float(c["high"]),
            "low":    float(c["low"]),
            "close":  float(c["close"]),
            "volume": float(c["volume"]),
        })
    df = pd.DataFrame(rows)
    df = df.iloc[::-1].reset_index(drop=True)  # oldest first
    return df


# ─── INDICATORS ──────────────────────────────────────────────────────────────

def compute_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return RSIIndicator(close=df["close"], window=period).rsi()


def compute_macd(df: pd.DataFrame):
    """Returns (macd_line, signal_line, histogram) series."""
    m = MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
    return m.macd(), m.macd_signal(), m.macd_diff()


def compute_bollinger(df: pd.DataFrame, period: int = 20, std: float = 2.0):
    """Returns (upper, middle, lower) band series."""
    bb = BollingerBands(close=df["close"], window=period, window_dev=std)
    return bb.bollinger_hband(), bb.bollinger_mavg(), bb.bollinger_lband()


def compute_ema_stack(df: pd.DataFrame):
    """Returns (ema8, ema21, ema55) — Gann/cosmic harmonic periods."""
    ema8  = EMAIndicator(close=df["close"], window=8).ema_indicator()
    ema21 = EMAIndicator(close=df["close"], window=21).ema_indicator()
    ema55 = EMAIndicator(close=df["close"], window=55).ema_indicator()
    return ema8, ema21, ema55


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range — used for dynamic stop loss sizing."""
    return AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"], window=period
    ).average_true_range()


def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ADX — market regime detector. >25 = trending, <20 = ranging."""
    return ADXIndicator(
        high=df["high"], low=df["low"], close=df["close"], window=period
    ).adx()


# ─── VOLUME ANALYSIS ─────────────────────────────────────────────────────────

def volume_confirms(df: pd.DataFrame, lookback: int = 10) -> bool:
    """True if current volume is above its recent average — confirms moves."""
    if len(df) < lookback + 1:
        return False
    avg_vol = df["volume"].iloc[-(lookback + 1):-1].mean()
    return df["volume"].iloc[-1] > avg_vol


# ─── MARKET REGIME ───────────────────────────────────────────────────────────

def get_market_regime(adx_val: float) -> str:
    if adx_val > 25:
        return "TRENDING"
    elif adx_val < 20:
        return "RANGING"
    return "TRANSITIONING"


# ─── CONFLUENCE SCORING ──────────────────────────────────────────────────────

def score_technicals(df: pd.DataFrame) -> dict:
    """
    Compute all indicators and return a structured dict with:
      - individual indicator values
      - a directional score (-6 to +6)
      - a signal direction: LONG / SHORT / NEUTRAL
      - ATR value for stop loss calculation
      - market regime
    """
    if len(df) < 60:
        return {"error": "Not enough candle data (need 60+)"}

    try:
        price     = df["close"].iloc[-1]
        rsi       = compute_rsi(df)
        macd_line, macd_sig, macd_hist = compute_macd(df)
        bb_upper, bb_mid, bb_lower    = compute_bollinger(df)
        ema8, ema21, ema55            = compute_ema_stack(df)
        atr_series = compute_atr(df)
        adx_series = compute_adx(df)

        rsi_val   = rsi.iloc[-1]
        rsi_prev  = rsi.iloc[-2]
        macd_val  = macd_line.iloc[-1]
        macd_prev = macd_line.iloc[-2]
        sig_val   = macd_sig.iloc[-1]
        sig_prev  = macd_sig.iloc[-2]
        hist_val  = macd_hist.iloc[-1]
        bb_u      = bb_upper.iloc[-1]
        bb_m      = bb_mid.iloc[-1]
        bb_l      = bb_lower.iloc[-1]
        e8        = ema8.iloc[-1]
        e21       = ema21.iloc[-1]
        e55       = ema55.iloc[-1]
        atr_val   = atr_series.iloc[-1]
        adx_val   = adx_series.iloc[-1]
        vol_ok    = volume_confirms(df)
        regime    = get_market_regime(adx_val)

        score = 0
        signals = []

        # ── RSI ──────────────────────────────────────────────────────────────
        if rsi_val < 30:
            score += 2
            signals.append(f"RSI {rsi_val:.1f} OVERSOLD +2")
        elif rsi_val < 50 and rsi_val > rsi_prev:
            score += 1
            signals.append(f"RSI {rsi_val:.1f} rising through 50 +1")
        elif rsi_val > 70:
            score -= 2
            signals.append(f"RSI {rsi_val:.1f} OVERBOUGHT -2")
        elif rsi_val > 50 and rsi_val < rsi_prev:
            score -= 1
            signals.append(f"RSI {rsi_val:.1f} falling through 50 -1")

        # ── MACD ─────────────────────────────────────────────────────────────
        macd_bull_cross = macd_val > sig_val and macd_prev <= sig_prev
        macd_bear_cross = macd_val < sig_val and macd_prev >= sig_prev

        if macd_bull_cross:
            score += 2
            signals.append("MACD bullish crossover +2")
        elif hist_val > 0 and hist_val > macd_hist.iloc[-2]:
            score += 1
            signals.append("MACD histogram expanding bullish +1")
        elif macd_bear_cross:
            score -= 2
            signals.append("MACD bearish crossover -2")
        elif hist_val < 0 and hist_val < macd_hist.iloc[-2]:
            score -= 1
            signals.append("MACD histogram expanding bearish -1")

        # ── BOLLINGER BANDS ───────────────────────────────────────────────────
        bb_width = (bb_u - bb_l) / bb_m
        if price <= bb_l:
            score += 2
            signals.append(f"Price AT/BELOW lower BB ${bb_l:,.2f} +2")
        elif price < bb_m:
            score += 1
            signals.append(f"Price below BB midline +1")
        elif price >= bb_u:
            score -= 2
            signals.append(f"Price AT/ABOVE upper BB ${bb_u:,.2f} -2")
        elif price > bb_m:
            score -= 1
            signals.append(f"Price above BB midline -1")

        # ── EMA STACK ─────────────────────────────────────────────────────────
        if e8 > e21 > e55 and price > e8:
            score += 1
            signals.append("EMA stack bullish (8>21>55) +1")
        elif e8 < e21 < e55 and price < e8:
            score -= 1
            signals.append("EMA stack bearish (8<21<55) -1")

        # ── VOLUME ────────────────────────────────────────────────────────────
        if vol_ok and score > 0:
            score += 1
            signals.append("Volume confirms move +1")
        elif vol_ok and score < 0:
            score -= 1
            signals.append("Volume confirms move -1")

        # ── DIRECTION ─────────────────────────────────────────────────────────
        if score >= 3:
            direction = "LONG"
        elif score <= -3:
            direction = "SHORT"
        else:
            direction = "NEUTRAL"

        # ── STRENGTH LABEL ────────────────────────────────────────────────────
        abs_score = abs(score)
        if abs_score >= 6:
            strength = "STRONG"
        elif abs_score >= 4:
            strength = "MODERATE"
        elif abs_score >= 2:
            strength = "WEAK"
        else:
            strength = "NONE"

        return {
            "price":          round(price, 4),
            "rsi":            round(rsi_val, 2),
            "macd":           round(macd_val, 4),
            "macd_signal":    round(sig_val, 4),
            "macd_hist":      round(hist_val, 4),
            "macd_cross":     "BULL" if macd_bull_cross else ("BEAR" if macd_bear_cross else "NONE"),
            "bb_upper":       round(bb_u, 4),
            "bb_mid":         round(bb_m, 4),
            "bb_lower":       round(bb_l, 4),
            "bb_width":       round(bb_width, 4),
            "ema8":           round(e8, 4),
            "ema21":          round(e21, 4),
            "ema55":          round(e55, 4),
            "atr":            round(atr_val, 4),
            "adx":            round(adx_val, 2),
            "volume_ok":      vol_ok,
            "regime":         regime,
            "ta_score":       score,
            "direction":      direction,
            "strength":       strength,
            "signals":        signals,
        }

    except Exception as e:
        log.error(f"Technical analysis error: {e}")
        return {"error": str(e)}

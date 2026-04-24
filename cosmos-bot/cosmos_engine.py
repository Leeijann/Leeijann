"""
cosmos_engine.py
────────────────
Planetary aspect scoring, moon phase detection, Fibonacci levels,
Gann Square of 9 harmonics, and eclipse proximity checks.
Uses the `ephem` library — runs 100% offline on your local PC.
"""

import math
import datetime
import ephem
from config import FIBONACCI_LEVELS, PLANET_ASPECTS, GANN_ANGLES


# ─── PLANETS ────────────────────────────────────────────────────────────────

PLANETS = {
    "Sun":     ephem.Sun,
    "Moon":    ephem.Moon,
    "Mercury": ephem.Mercury,
    "Venus":   ephem.Venus,
    "Mars":    ephem.Mars,
    "Jupiter": ephem.Jupiter,
    "Saturn":  ephem.Saturn,
    "Uranus":  ephem.Uranus,
    "Neptune": ephem.Neptune,
}


def get_planet_positions(date=None):
    """Return ecliptic longitude (degrees) for each planet."""
    d = ephem.Date(date) if date else ephem.now()
    positions = {}
    for name, planet_class in PLANETS.items():
        body = planet_class()
        body.compute(d, epoch=d)
        ecl = ephem.Ecliptic(body, epoch=d)
        positions[name] = math.degrees(ecl.lon) % 360
    return positions


# ─── ASPECT SCORING ──────────────────────────────────────────────────────────

def calculate_aspect_score(date=None):
    """
    Score all planet-to-planet aspects.
    Returns (total_score, list of active aspects).
    """
    positions = get_planet_positions(date)
    names = list(positions.keys())
    total_score = 0
    active_aspects = []

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            p1, p2 = names[i], names[j]
            angle = abs(positions[p1] - positions[p2]) % 360
            if angle > 180:
                angle = 360 - angle

            for aspect_name, (target, orb, score) in PLANET_ASPECTS.items():
                if abs(angle - target) <= orb:
                    total_score += score
                    active_aspects.append({
                        "planets": f"{p1} / {p2}",
                        "aspect":  aspect_name,
                        "angle":   round(angle, 2),
                        "score":   score,
                    })

    return total_score, active_aspects


# ─── MOON PHASE ──────────────────────────────────────────────────────────────

def get_moon_phase(date=None):
    """
    Returns moon phase name and day in cycle (0-29).
    Phase names: New Moon, Waxing Crescent, First Quarter,
                 Waxing Gibbous, Full Moon, Waning Gibbous,
                 Last Quarter, Waning Crescent
    """
    d = ephem.Date(date) if date else ephem.now()
    prev_new = ephem.previous_new_moon(d)
    days_since_new = d - prev_new

    phase_day = int(days_since_new)

    if phase_day <= 1:
        phase_name = "New Moon"
        bias = "ACCUMULATION — favor longs"
    elif phase_day <= 6:
        phase_name = "Waxing Crescent"
        bias = "BUILDING — early long entries"
    elif phase_day <= 8:
        phase_name = "First Quarter"
        bias = "MOMENTUM — trend following"
    elif phase_day <= 13:
        phase_name = "Waxing Gibbous"
        bias = "EXPANSION — ride the trend"
    elif phase_day <= 15:
        phase_name = "Full Moon"
        bias = "CAUTION — reversal risk high, tighten stops"
    elif phase_day <= 21:
        phase_name = "Waning Gibbous"
        bias = "DISTRIBUTION — consider partial exits"
    elif phase_day <= 23:
        phase_name = "Last Quarter"
        bias = "CONTRACTION — favor shorts or cash"
    else:
        phase_name = "Waning Crescent"
        bias = "RESET — wait for next New Moon"

    return {
        "phase": phase_name,
        "day_in_cycle": phase_day,
        "bias": bias,
    }


# ─── MERCURY RETROGRADE ───────────────────────────────────────────────────────

def is_mercury_retrograde(date=None):
    """Check if Mercury is currently retrograde."""
    d = ephem.Date(date) if date else ephem.now()
    mercury = ephem.Mercury()

    mercury.compute(ephem.Date(d - 1))
    prev_lon = math.degrees(ephem.Ecliptic(mercury, epoch=d).lon)

    mercury.compute(d)
    curr_lon = math.degrees(ephem.Ecliptic(mercury, epoch=d).lon)

    diff = (curr_lon - prev_lon + 360) % 360
    return diff > 180  # retrograde if moving backward


# ─── ECLIPSE PROXIMITY ───────────────────────────────────────────────────────

def eclipse_proximity_days(date=None):
    """
    Returns days until or since nearest solar/lunar eclipse window.
    Eclipse = new moon or full moon within 18.5° of a node.
    Approximated by checking proximity of new/full moon dates.
    """
    d = ephem.Date(date) if date else ephem.now()

    next_new  = ephem.next_new_moon(d)
    next_full = ephem.next_full_moon(d)
    prev_new  = ephem.previous_new_moon(d)
    prev_full = ephem.previous_full_moon(d)

    candidates = [
        abs(d - next_new),
        abs(d - next_full),
        abs(d - prev_new),
        abs(d - prev_full),
    ]
    return min(candidates)  # days as float


# ─── FIBONACCI LEVELS ────────────────────────────────────────────────────────

def calculate_fibonacci_levels(swing_low: float, swing_high: float):
    """
    Returns retracement and extension levels from a swing.
    """
    diff = swing_high - swing_low
    levels = {}
    for ratio in FIBONACCI_LEVELS:
        if ratio <= 1.0:
            levels[f"retracement_{ratio}"] = round(swing_high - diff * ratio, 6)
        else:
            levels[f"extension_{ratio}"]   = round(swing_low + diff * ratio, 6)
    return levels


def nearest_fibonacci_level(price: float, swing_low: float, swing_high: float):
    """
    Find the closest Fibonacci level to the current price.
    Returns (label, level_price, distance_pct).
    """
    levels = calculate_fibonacci_levels(swing_low, swing_high)
    closest = min(levels.items(), key=lambda x: abs(x[1] - price))
    distance_pct = abs(closest[1] - price) / price * 100
    return closest[0], closest[1], round(distance_pct, 4)


# ─── GANN SQUARE OF 9 ────────────────────────────────────────────────────────

def gann_square_of_9(price: float):
    """
    Calculate key Gann Square of 9 harmonic price levels.
    Uses the formula: level = (sqrt(price) ± n/4)^2
    where n = 1..4 (90°, 180°, 270°, 360°)
    """
    sqrt_p = math.sqrt(price)
    levels = {}
    increments = {90: 1/4, 180: 2/4, 270: 3/4, 360: 4/4}
    for angle, inc in increments.items():
        levels[f"above_{angle}"] = round((sqrt_p + inc) ** 2, 4)
        levels[f"below_{angle}"] = round((sqrt_p - inc) ** 2, 4)
    return levels


# ─── ZODIAC SIGN ─────────────────────────────────────────────────────────────

ZODIAC_SIGNS = [
    (30,  "Aries",       "Metals, energy, military"),
    (60,  "Taurus",      "Finance, real estate, agriculture"),
    (90,  "Gemini",      "Technology, communications, transport"),
    (120, "Cancer",      "Real estate, food, domestic markets"),
    (150, "Leo",         "Gold, entertainment, luxury"),
    (180, "Virgo",       "Healthcare, analytics, agriculture"),
    (210, "Libra",       "Legal, diplomacy, luxury goods"),
    (240, "Scorpio",     "Debt, derivatives, crypto"),
    (270, "Sagittarius", "International trade, expansion"),
    (300, "Capricorn",   "Institutions, government, long bonds"),
    (330, "Aquarius",    "Tech disruption, crypto, networks"),
    (360, "Pisces",      "Oil, pharma, collective sentiment"),
]


def get_zodiac(longitude: float):
    for cutoff, sign, sector in ZODIAC_SIGNS:
        if longitude < cutoff:
            return sign, sector
    return "Pisces", "Oil, pharma, collective sentiment"


def get_sun_sign(date=None):
    positions = get_planet_positions(date)
    sign, sector = get_zodiac(positions["Sun"])
    return {"sign": sign, "sector": sector, "longitude": round(positions["Sun"], 2)}


# ─── FULL COSMIC REPORT ──────────────────────────────────────────────────────

def full_cosmic_report(date=None):
    """
    Master function — returns a complete cosmic snapshot.
    """
    aspect_score, aspects = calculate_aspect_score(date)
    moon = get_moon_phase(date)
    retro = is_mercury_retrograde(date)
    eclipse_days = eclipse_proximity_days(date)
    sun_sign = get_sun_sign(date)
    positions = get_planet_positions(date)

    # Determine directional bias
    if aspect_score >= 15:
        cosmic_bias = "BULLISH"
    elif aspect_score <= -10:
        cosmic_bias = "BEARISH"
    else:
        cosmic_bias = "NEUTRAL"

    # Eclipse caution flag
    eclipse_caution = eclipse_days <= 7

    report = {
        "date": str(ephem.Date(date) if date else ephem.now()),
        "aspect_score": aspect_score,
        "cosmic_bias": cosmic_bias,
        "active_aspects": aspects,
        "moon": moon,
        "mercury_retrograde": retro,
        "eclipse_proximity_days": round(eclipse_days, 1),
        "eclipse_caution": eclipse_caution,
        "sun_sign": sun_sign,
        "planet_positions": {k: round(v, 2) for k, v in positions.items()},
    }
    return report

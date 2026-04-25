"""
cosmos_engine.py
────────────────
Planetary aspect scoring, moon phase detection, Fibonacci levels,
Gann Square of 9 harmonics, and eclipse proximity checks.

Upgraded to Swiss Ephemeris (pyswisseph) — professional-grade precision.
Uses Moshier built-in ephemeris: NO external data files or API keys needed.
Adds: Pluto, Lunar Nodes, Chiron, retrograde speed detection.
"""

import math
import datetime
import swisseph as swe
from config import FIBONACCI_LEVELS, PLANET_ASPECTS, GANN_ANGLES
from time_brain import get_brain_state

# Use Moshier built-in ephemeris — no files needed, runs fully offline
swe.set_ephe_path(None)

_FLAG = swe.FLG_MOSEPH | swe.FLG_SPEED


# ─── PLANETS ────────────────────────────────────────────────────────────────

PLANETS = {
    "Sun":      swe.SUN,
    "Moon":     swe.MOON,
    "Mercury":  swe.MERCURY,
    "Venus":    swe.VENUS,
    "Mars":     swe.MARS,
    "Jupiter":  swe.JUPITER,
    "Saturn":   swe.SATURN,
    "Uranus":   swe.URANUS,
    "Neptune":  swe.NEPTUNE,
    "Pluto":    swe.PLUTO,
    "TrueNode": swe.TRUE_NODE,
    "Chiron":   swe.CHIRON,
}


def _jd(dt=None) -> float:
    """Convert a datetime (or now) to a Julian Day number."""
    if dt is None:
        dt = datetime.datetime.utcnow()
    if isinstance(dt, (int, float)):
        return float(dt)
    return swe.julday(
        dt.year, dt.month, dt.day,
        dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    )


# ─── PLANET POSITIONS ────────────────────────────────────────────────────────

def get_planet_positions(date=None) -> dict:
    """Return ecliptic longitude (degrees 0–360) for each tracked body."""
    jd = _jd(date)
    positions = {}
    for name, planet_id in PLANETS.items():
        try:
            result, _ = swe.calc_ut(jd, planet_id, _FLAG)
            positions[name] = round(result[0] % 360, 4)
        except Exception:
            pass
    return positions


def get_planet_speeds(date=None) -> dict:
    """Return daily speed in longitude for each body (negative = retrograde)."""
    jd = _jd(date)
    speeds = {}
    for name, planet_id in PLANETS.items():
        try:
            result, _ = swe.calc_ut(jd, planet_id, _FLAG)
            speeds[name] = round(result[3], 6)  # index 3 = speed in longitude
        except Exception:
            pass
    return speeds


# ─── RETROGRADE DETECTION ────────────────────────────────────────────────────

def get_retrograde_planets(date=None) -> list:
    """Return list of planet names currently retrograde (speed < 0)."""
    speeds = get_planet_speeds(date)
    # Sun and Moon never retrograde
    skip = {"Sun", "Moon", "TrueNode"}
    return [name for name, speed in speeds.items()
            if speed < 0 and name not in skip]


def is_mercury_retrograde(date=None) -> bool:
    jd = _jd(date)
    try:
        result, _ = swe.calc_ut(jd, swe.MERCURY, _FLAG)
        return result[3] < 0
    except Exception:
        return False


# ─── ASPECT SCORING ──────────────────────────────────────────────────────────

def calculate_aspect_score(date=None):
    """
    Score all planet-to-planet aspects using Swiss Ephemeris positions.
    Returns (total_score, list of active aspect dicts).
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

    # Sort by absolute score strength, strongest first
    active_aspects.sort(key=lambda x: abs(x["score"]), reverse=True)
    return total_score, active_aspects


# ─── MOON PHASE ──────────────────────────────────────────────────────────────

def get_moon_phase(date=None) -> dict:
    """
    Calculate moon phase from Sun-Moon elongation angle.
    Swiss Ephemeris gives precise elongation directly.
    """
    jd = _jd(date)
    try:
        sun,  _ = swe.calc_ut(jd, swe.SUN,  _FLAG)
        moon, _ = swe.calc_ut(jd, swe.MOON, _FLAG)
        elongation = (moon[0] - sun[0]) % 360
    except Exception:
        elongation = 0.0

    if elongation < 45:
        phase_name, bias = "New Moon",       "ACCUMULATION — favor longs"
    elif elongation < 90:
        phase_name, bias = "Waxing Crescent","BUILDING — early long entries"
    elif elongation < 135:
        phase_name, bias = "First Quarter",  "MOMENTUM — trend following"
    elif elongation < 180:
        phase_name, bias = "Waxing Gibbous", "EXPANSION — ride the trend"
    elif elongation < 225:
        phase_name, bias = "Full Moon",      "CAUTION — reversal risk high, tighten stops"
    elif elongation < 270:
        phase_name, bias = "Waning Gibbous", "DISTRIBUTION — consider partial exits"
    elif elongation < 315:
        phase_name, bias = "Last Quarter",   "CONTRACTION — favor shorts or cash"
    else:
        phase_name, bias = "Waning Crescent","RESET — wait for next New Moon"

    return {
        "phase":      phase_name,
        "elongation": round(elongation, 2),
        "bias":       bias,
    }


# ─── ECLIPSE PROXIMITY ───────────────────────────────────────────────────────

def eclipse_proximity_days(date=None) -> float:
    """
    Find the nearest solar or lunar eclipse (past or future).
    Returns number of days to/from closest eclipse.
    """
    jd = _jd(date)
    candidates = []

    try:
        _, sol_tret = swe.sol_eclipse_when_glob(jd, swe.FLG_MOSEPH)
        if sol_tret and sol_tret[0]:
            candidates.append(abs(jd - sol_tret[0]))
    except Exception:
        pass

    try:
        _, lun_tret = swe.lun_eclipse_when(jd, swe.FLG_MOSEPH)
        if lun_tret and lun_tret[0]:
            candidates.append(abs(jd - lun_tret[0]))
    except Exception:
        pass

    return min(candidates) if candidates else 99.0


# ─── FIBONACCI LEVELS ────────────────────────────────────────────────────────

def calculate_fibonacci_levels(swing_low: float, swing_high: float) -> dict:
    diff = swing_high - swing_low
    levels = {}
    for ratio in FIBONACCI_LEVELS:
        if ratio <= 1.0:
            levels[f"retracement_{ratio}"] = round(swing_high - diff * ratio, 6)
        else:
            levels[f"extension_{ratio}"]   = round(swing_low + diff * ratio, 6)
    return levels


def nearest_fibonacci_level(price: float, swing_low: float, swing_high: float):
    levels = calculate_fibonacci_levels(swing_low, swing_high)
    closest = min(levels.items(), key=lambda x: abs(x[1] - price))
    distance_pct = abs(closest[1] - price) / price * 100
    return closest[0], closest[1], round(distance_pct, 4)


# ─── GANN SQUARE OF 9 ────────────────────────────────────────────────────────

def gann_square_of_9(price: float) -> dict:
    """Calculate Gann Square of 9 harmonic price levels (90°/180°/270°/360°)."""
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


def get_sun_sign(date=None) -> dict:
    positions = get_planet_positions(date)
    lon = positions.get("Sun", 0.0)
    sign, sector = get_zodiac(lon)
    return {"sign": sign, "sector": sector, "longitude": round(lon, 2)}


# ─── CHIRON & LUNAR NODE CONTEXT ─────────────────────────────────────────────

def get_chiron_node_context(date=None) -> dict:
    """Return Chiron and True Node sign — useful for deeper cycle context."""
    positions = get_planet_positions(date)
    chiron_lon   = positions.get("Chiron", 0.0)
    node_lon     = positions.get("TrueNode", 0.0)
    chiron_sign, _ = get_zodiac(chiron_lon)
    node_sign, _   = get_zodiac(node_lon)
    return {
        "chiron_sign":    chiron_sign,
        "chiron_lon":     chiron_lon,
        "true_node_sign": node_sign,
        "true_node_lon":  node_lon,
    }


# ─── FULL COSMIC REPORT ──────────────────────────────────────────────────────

def full_cosmic_report(date=None) -> dict:
    """Master function — returns a complete cosmic + temporal snapshot."""
    aspect_score, aspects = calculate_aspect_score(date)
    moon          = get_moon_phase(date)
    retro_planets = get_retrograde_planets(date)
    retro         = "Mercury" in retro_planets
    eclipse_days  = eclipse_proximity_days(date)
    sun_sign      = get_sun_sign(date)
    positions     = get_planet_positions(date)
    cn_context    = get_chiron_node_context(date)
    brain         = get_brain_state()

    if aspect_score >= 15:
        cosmic_bias = "BULLISH"
    elif aspect_score <= -10:
        cosmic_bias = "BEARISH"
    else:
        cosmic_bias = "NEUTRAL"

    # Blend cosmic aspect score with temporal brain score for a unified signal
    combined_score = aspect_score + brain["temporal_score"]

    return {
        "date":                   str(datetime.datetime.utcnow()),
        "aspect_score":           aspect_score,
        "temporal_score":         brain["temporal_score"],
        "combined_score":         combined_score,
        "cosmic_bias":            cosmic_bias,
        "active_aspects":         aspects,
        "moon":                   moon,
        "mercury_retrograde":     retro,
        "retrograde_planets":     retro_planets,
        "eclipse_proximity_days": round(eclipse_days, 1),
        "eclipse_caution":        eclipse_days <= 7,
        "sun_sign":               sun_sign,
        "chiron_node":            cn_context,
        "planet_positions":       {k: round(v, 2) for k, v in positions.items()},
        "brain":                  brain,
    }

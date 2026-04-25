"""
time_brain.py
─────────────
The temporal consciousness of HERMES-7.

Knows:
  - Exact UTC time and local time context
  - Time of day segment (dawn, morning, midday, dusk, night, etc.)
  - Day of week + its planetary ruler
  - Current season from Sun's ecliptic position
  - Precise moon illumination % and phase name
  - Moon rise / set times
  - Sunrise / sunset times at your configured location
  - Planetary hour ruler (each hour ruled by a planet, ancient system)
  - Market session (Asian / London / New York / Dead Zone)
  - 24 Solar Terms (Chinese astronomical calendar — granular season markers)
  - Full synthesis: a single "brain state" dict the bot reasons from
"""

import math
import datetime
import swisseph as swe
from config import GEO_LAT, GEO_LON

swe.set_ephe_path(None)
_FLAG = swe.FLG_MOSEPH | swe.FLG_SPEED


# ─── JULIAN DAY HELPER ───────────────────────────────────────────────────────

def _jd(dt=None) -> float:
    if dt is None:
        dt = datetime.datetime.utcnow()
    return swe.julday(
        dt.year, dt.month, dt.day,
        dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    )


# ─── TIME OF DAY ─────────────────────────────────────────────────────────────

def get_time_of_day(dt=None) -> dict:
    """
    Classify time into cosmic segments based on sunrise/sunset at configured location.
    Falls back to UTC hour if rise/set calculation fails.
    """
    if dt is None:
        dt = datetime.datetime.utcnow()
    jd = _jd(dt)

    try:
        # Sunrise
        _, trise = swe.rise_trans(
            jd - 0.5, swe.SUN, b"", swe.FLG_MOSEPH,
            swe.CALC_RISE, [GEO_LON, GEO_LAT, 0]
        )
        # Sunset
        _, tset = swe.rise_trans(
            jd - 0.5, swe.SUN, b"", swe.FLG_MOSEPH,
            swe.CALC_SET, [GEO_LON, GEO_LAT, 0]
        )
        sunrise_jd = trise[1]
        sunset_jd  = tset[1]

        # Convert JD offsets to UTC hours
        def jd_to_hour(j):
            y, mo, d, h = swe.revjul(j)
            return h

        sunrise_h = jd_to_hour(sunrise_jd)
        sunset_h  = jd_to_hour(sunset_jd)
        current_h = dt.hour + dt.minute / 60.0

        dawn_h    = sunrise_h - 1.0
        dusk_h    = sunset_h  + 1.0
        midnight_h = 0.0

        if current_h < dawn_h:
            segment = "Deep Night"
            market_energy = "Lowest energy. Markets thin. Rest cycle."
        elif current_h < sunrise_h:
            segment = "Dawn"
            market_energy = "Pre-market awakening. Asian session closing."
        elif current_h < sunrise_h + 3:
            segment = "Morning"
            market_energy = "Rising energy. London session active."
        elif current_h < 12:
            segment = "Late Morning"
            market_energy = "Peak focus window. New York pre-market."
        elif current_h < 14:
            segment = "Midday"
            market_energy = "NY session open. Highest liquidity."
        elif current_h < sunset_h - 1:
            segment = "Afternoon"
            market_energy = "NY session mid. Trend continuation phase."
        elif current_h < sunset_h:
            segment = "Late Afternoon"
            market_energy = "NY session closing. Volatility spike risk."
        elif current_h < dusk_h:
            segment = "Dusk"
            market_energy = "Post-market. Energy winding down."
        elif current_h < 22:
            segment = "Evening"
            market_energy = "Crypto active. Low traditional volume."
        else:
            segment = "Night"
            market_energy = "Asian session beginning. Quiet period."

        return {
            "segment":      segment,
            "market_energy": market_energy,
            "sunrise_utc":  f"{int(sunrise_h):02d}:{int((sunrise_h % 1)*60):02d}",
            "sunset_utc":   f"{int(sunset_h):02d}:{int((sunset_h % 1)*60):02d}",
            "current_utc":  dt.strftime("%H:%M"),
            "is_daytime":   sunrise_h <= current_h <= sunset_h,
        }

    except Exception:
        # Fallback: UTC hour only
        h = dt.hour
        if 5 <= h < 8:
            segment, energy = "Dawn", "Pre-market awakening."
        elif 8 <= h < 12:
            segment, energy = "Morning", "London session."
        elif 12 <= h < 17:
            segment, energy = "Midday/Afternoon", "NY session — peak liquidity."
        elif 17 <= h < 20:
            segment, energy = "Evening", "Post-market wind-down."
        else:
            segment, energy = "Night", "Crypto active. Thin volume."
        return {
            "segment": segment, "market_energy": energy,
            "sunrise_utc": "N/A", "sunset_utc": "N/A",
            "current_utc": dt.strftime("%H:%M"), "is_daytime": 6 <= h <= 20,
        }


# ─── SEASON ──────────────────────────────────────────────────────────────────

def get_season(date=None) -> dict:
    """
    Derive season from the Sun's ecliptic longitude.
    Works for both hemispheres via GEO_LAT sign.
    Northern Hemisphere:
      0°–89°   = Spring   (Aries → Gemini)
      90°–179° = Summer   (Cancer → Virgo)
      180°–269°= Autumn   (Libra → Sagittarius)
      270°–359°= Winter   (Capricorn → Pisces)
    """
    jd = _jd(date)
    result, _ = swe.calc_ut(jd, swe.SUN, swe.FLG_MOSEPH)
    sun_lon = result[0] % 360

    if sun_lon < 90:
        season = "Spring"
        market_tendency = "Renewal — new trends emerging, energy building"
        element = "Fire / Air"
    elif sun_lon < 180:
        season = "Summer"
        market_tendency = "Expansion — peak growth phase, momentum high"
        element = "Fire / Earth"
    elif sun_lon < 270:
        season = "Autumn"
        market_tendency = "Harvest — take profits, distribution phase"
        element = "Air / Water"
    else:
        season = "Winter"
        market_tendency = "Contraction — accumulation, patience required"
        element = "Water / Earth"

    # Flip for Southern Hemisphere
    if GEO_LAT < 0:
        flip = {"Spring": "Autumn", "Summer": "Winter",
                "Autumn": "Spring", "Winter": "Summer"}
        season = flip[season]

    return {
        "season":           season,
        "sun_longitude":    round(sun_lon, 2),
        "market_tendency":  market_tendency,
        "element":          element,
    }


# ─── SOLAR TERMS (24 Chinese Astronomical Markers) ───────────────────────────

SOLAR_TERMS = [
    (0,   "Vernal Equinox",    "Spring begins — Yang energy rising"),
    (15,  "Clear and Bright",  "Energy clarifying — new entries favored"),
    (30,  "Grain Rain",        "Growth accelerating — momentum building"),
    (45,  "Start of Summer",   "Heat rising — volatility increases"),
    (60,  "Grain Fills",       "Markets filling out — trend maturity"),
    (75,  "Grain in Ear",      "Peak growth — watch for exhaustion"),
    (90,  "Summer Solstice",   "Maximum Yang — climax point, reversal risk"),
    (105, "Minor Heat",        "Cooling begins — distribution phase"),
    (120, "Major Heat",        "Peak heat — high volatility window"),
    (135, "Start of Autumn",   "Yin rising — trend shifts possible"),
    (150, "End of Heat",       "Cooling confirmed — bear awareness"),
    (165, "White Dew",         "Condensation — energy consolidating"),
    (180, "Autumnal Equinox",  "Balance point — reversal zone"),
    (195, "Cold Dew",          "Yin deepening — defensive posture"),
    (210, "Frost's Descent",   "Freeze warning — stop losses tight"),
    (225, "Start of Winter",   "Hibernation — reduce exposure"),
    (240, "Minor Snow",        "Contraction — accumulate quietly"),
    (255, "Major Snow",        "Deep contraction — long-term base forming"),
    (270, "Winter Solstice",   "Maximum Yin — capitulation / bottom zone"),
    (285, "Minor Cold",        "Stirring beneath — watch for reversal"),
    (300, "Major Cold",        "Final cold — darkest before dawn"),
    (315, "Start of Spring",   "Yang returning — early accumulation"),
    (330, "Rain Water",        "Thaw beginning — cautious longs"),
    (345, "Awakening Insects", "Life returning — momentum building"),
]


def get_solar_term(date=None) -> dict:
    jd = _jd(date)
    result, _ = swe.calc_ut(jd, swe.SUN, swe.FLG_MOSEPH)
    sun_lon = result[0] % 360

    current_term = SOLAR_TERMS[0]
    for lon, name, meaning in SOLAR_TERMS:
        if sun_lon >= lon:
            current_term = (lon, name, meaning)

    degrees_into_term = sun_lon - current_term[0]
    return {
        "solar_term":        current_term[1],
        "meaning":           current_term[2],
        "degrees_into_term": round(degrees_into_term, 2),
    }


# ─── MOON ILLUMINATION ───────────────────────────────────────────────────────

def get_moon_illumination(date=None) -> dict:
    """
    Returns precise moon illumination % and detailed phase name.
    Uses Swiss Ephemeris pheno_ut for exact illuminated fraction.
    """
    jd = _jd(date)

    try:
        _, attr = swe.pheno_ut(jd, swe.MOON, swe.FLG_MOSEPH)
        illumination_pct = round(attr[1] * 100, 1)
    except Exception:
        illumination_pct = 0.0

    # Sun-Moon elongation for phase direction
    try:
        sun,  _ = swe.calc_ut(jd, swe.SUN,  swe.FLG_MOSEPH)
        moon, _ = swe.calc_ut(jd, swe.MOON, swe.FLG_MOSEPH)
        elongation = (moon[0] - sun[0]) % 360
    except Exception:
        elongation = 0.0

    waxing = elongation < 180

    if illumination_pct < 2:
        phase_name = "New Moon"
        symbol = "NEW"
    elif illumination_pct < 25:
        phase_name = "Waxing Crescent" if waxing else "Waning Crescent"
        symbol = "CRESCENT"
    elif illumination_pct < 60:
        phase_name = "First Quarter" if waxing else "Last Quarter"
        symbol = "HALF"
    elif illumination_pct < 95:
        phase_name = "Waxing Gibbous" if waxing else "Waning Gibbous"
        symbol = "GIBBOUS"
    else:
        phase_name = "Full Moon"
        symbol = "FULL"

    # Trading bias
    bias_map = {
        "New Moon":       "Accumulation — seeds planted now grow",
        "Waxing Crescent": "Early momentum — build positions",
        "First Quarter":  "Push through resistance — trend entries",
        "Waxing Gibbous": "Full expansion — ride the trend",
        "Full Moon":      "Peak illumination — reversal risk, tighten stops",
        "Waning Gibbous": "Distribution — partial exits",
        "Last Quarter":   "Contraction — reduce longs",
        "Waning Crescent": "Release — clear positions, prepare for reset",
    }

    return {
        "phase_name":       phase_name,
        "symbol":           symbol,
        "illumination_pct": illumination_pct,
        "waxing":           waxing,
        "elongation":       round(elongation, 2),
        "trading_bias":     bias_map.get(phase_name, "Neutral"),
    }


# ─── MOON RISE / SET ─────────────────────────────────────────────────────────

def get_moon_rise_set(date=None) -> dict:
    """Return moon rise and set times (UTC) for the configured location."""
    if date is None:
        date = datetime.datetime.utcnow()
    jd = _jd(date)

    def jd_to_hhmm(j):
        _, _, _, h = swe.revjul(j)
        hh = int(h)
        mm = int((h - hh) * 60)
        return f"{hh:02d}:{mm:02d}"

    try:
        _, trise = swe.rise_trans(
            jd - 0.5, swe.MOON, b"", swe.FLG_MOSEPH,
            swe.CALC_RISE, [GEO_LON, GEO_LAT, 0]
        )
        moonrise = jd_to_hhmm(trise[1])
    except Exception:
        moonrise = "N/A"

    try:
        _, tset = swe.rise_trans(
            jd - 0.5, swe.MOON, b"", swe.FLG_MOSEPH,
            swe.CALC_SET, [GEO_LON, GEO_LAT, 0]
        )
        moonset = jd_to_hhmm(tset[1])
    except Exception:
        moonset = "N/A"

    return {"moonrise_utc": moonrise, "moonset_utc": moonset}


# ─── DAY OF WEEK + PLANETARY RULER ───────────────────────────────────────────

DAY_RULERS = {
    0: ("Monday",    "Moon",    "Emotions, intuition, public sentiment"),
    1: ("Tuesday",   "Mars",    "Aggression, momentum, energy"),
    2: ("Wednesday", "Mercury", "Communication, data, quick moves"),
    3: ("Thursday",  "Jupiter", "Expansion, opportunity, optimism"),
    4: ("Friday",    "Venus",   "Value, beauty, financial harmony"),
    5: ("Saturday",  "Saturn",  "Discipline, restriction, patience"),
    6: ("Sunday",    "Sun",     "Vitality, leadership, gold"),
}


def get_day_ruler(dt=None) -> dict:
    if dt is None:
        dt = datetime.datetime.utcnow()
    weekday = dt.weekday()
    day, ruler, meaning = DAY_RULERS[weekday]
    return {"day": day, "ruler": ruler, "meaning": meaning}


# ─── PLANETARY HOURS ─────────────────────────────────────────────────────────

# Chaldean order — the ancient sequence of planetary hours
CHALDEAN_ORDER = ["Saturn", "Jupiter", "Mars", "Sun", "Venus", "Mercury", "Moon"]

# Day-hour sequence starts with the day ruler
DAY_HOUR_START = {
    "Sun":     0,   # Sunday   — Sun rules hour 1
    "Moon":    3,   # Monday   — Moon rules hour 1
    "Mars":    2,   # Tuesday
    "Mercury": 6,   # Wednesday
    "Jupiter": 1,   # Thursday
    "Venus":   4,   # Friday
    "Saturn":  5,   # Saturday
}


def get_planetary_hour(dt=None) -> dict:
    """
    Calculate the current planetary hour using sunrise-based division.
    Daytime = 12 equal hours from sunrise to sunset.
    Nighttime = 12 equal hours from sunset to next sunrise.
    """
    if dt is None:
        dt = datetime.datetime.utcnow()
    jd = _jd(dt)

    day_ruler = get_day_ruler(dt)["ruler"]
    start_idx = DAY_HOUR_START.get(day_ruler, 0)

    try:
        _, trise = swe.rise_trans(
            jd - 0.5, swe.SUN, b"", swe.FLG_MOSEPH,
            swe.CALC_RISE, [GEO_LON, GEO_LAT, 0]
        )
        _, tset = swe.rise_trans(
            jd - 0.5, swe.SUN, b"", swe.FLG_MOSEPH,
            swe.CALC_SET, [GEO_LON, GEO_LAT, 0]
        )
        sunrise_jd = trise[1]
        sunset_jd  = tset[1]
        day_len    = sunset_jd - sunrise_jd
        night_len  = 1.0 - day_len

        if sunrise_jd <= jd <= sunset_jd:
            hour_len   = day_len / 12.0
            hour_num   = int((jd - sunrise_jd) / hour_len)
            is_day     = True
        else:
            hour_len = night_len / 12.0
            if jd > sunset_jd:
                hour_num = int((jd - sunset_jd) / hour_len)
            else:
                hour_num = int((jd - (sunrise_jd - 1.0)) / hour_len)
            is_day = False
            hour_num += 12  # night hours offset

        planet_idx   = (start_idx + hour_num) % 7
        ruling_planet = CHALDEAN_ORDER[planet_idx]

    except Exception:
        ruling_planet = day_ruler
        is_day = 6 <= dt.hour <= 20

    planet_meanings = {
        "Sun":     "Gold, leadership, vitality — bold moves favored",
        "Moon":    "Intuition, public sentiment — emotional volatility",
        "Mercury": "Speed, data, communication — quick scalps",
        "Venus":   "Harmony, value — buy the dip",
        "Mars":    "Aggression, momentum — breakout entries",
        "Jupiter": "Expansion, luck — swing trade opportunities",
        "Saturn":  "Caution, discipline — hold or reduce risk",
    }

    return {
        "ruling_planet": ruling_planet,
        "meaning":       planet_meanings.get(ruling_planet, ""),
        "is_daytime":    is_day,
    }


# ─── MARKET SESSION ──────────────────────────────────────────────────────────

def get_market_session(dt=None) -> dict:
    """
    Identify the active traditional market session based on UTC time.
    Crypto trades 24/7 but liquidity peaks during these windows.
    """
    if dt is None:
        dt = datetime.datetime.utcnow()
    h = dt.hour + dt.minute / 60.0

    sessions = []
    # Sydney:   21:00 – 06:00 UTC
    # Tokyo:    00:00 – 09:00 UTC
    # London:   07:00 – 16:00 UTC
    # New York: 13:00 – 22:00 UTC

    if 21 <= h or h < 6:
        sessions.append("Sydney")
    if 0 <= h < 9:
        sessions.append("Tokyo")
    if 7 <= h < 16:
        sessions.append("London")
    if 13 <= h < 22:
        sessions.append("New York")

    if not sessions:
        sessions = ["Dead Zone"]
        liquidity = "Very low — avoid entries"
    elif len(sessions) == 1:
        liquidity = "Moderate"
    else:
        liquidity = "HIGH — overlapping sessions, maximum liquidity"

    return {
        "active_sessions": sessions,
        "liquidity":       liquidity,
    }


# ─── MASTER BRAIN STATE ──────────────────────────────────────────────────────

def get_brain_state(date=None) -> dict:
    """
    The full temporal consciousness of HERMES-7.
    Synthesizes all time-aware data into one brain state dict.
    """
    dt = date if isinstance(date, datetime.datetime) else datetime.datetime.utcnow()

    time_of_day   = get_time_of_day(dt)
    season        = get_season(dt)
    solar_term    = get_solar_term(dt)
    moon_illum    = get_moon_illumination(dt)
    moon_rise_set = get_moon_rise_set(dt)
    day_ruler     = get_day_ruler(dt)
    planet_hour   = get_planetary_hour(dt)
    market_session= get_market_session(dt)

    # Overall temporal bias score (-10 to +10)
    temporal_score = 0

    # Moon: waxing = bullish, waning = bearish
    if moon_illum["waxing"]:
        temporal_score += min(int(moon_illum["illumination_pct"] / 20), 3)
    else:
        temporal_score -= min(int(moon_illum["illumination_pct"] / 20), 3)

    # Season
    season_scores = {"Spring": 2, "Summer": 3, "Autumn": -1, "Winter": -2}
    temporal_score += season_scores.get(season["season"], 0)

    # Market session
    if "New York" in market_session["active_sessions"] and \
       "London" in market_session["active_sessions"]:
        temporal_score += 2  # Overlap = peak opportunity
    elif market_session["active_sessions"] == ["Dead Zone"]:
        temporal_score -= 2

    # Planetary hour
    hour_scores = {
        "Jupiter": 2, "Venus": 2, "Sun": 1,
        "Mercury": 0, "Moon": 0,
        "Mars": -1, "Saturn": -2
    }
    temporal_score += hour_scores.get(planet_hour["ruling_planet"], 0)

    return {
        "timestamp_utc":   dt.strftime("%Y-%m-%d %H:%M UTC"),
        "time_of_day":     time_of_day,
        "season":          season,
        "solar_term":      solar_term,
        "moon":            {**moon_illum, **moon_rise_set},
        "day_ruler":       day_ruler,
        "planetary_hour":  planet_hour,
        "market_session":  market_session,
        "temporal_score":  temporal_score,
    }

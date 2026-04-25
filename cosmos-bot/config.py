import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Coinbase
COINBASE_API_KEY = os.getenv("COINBASE_API_KEY")
COINBASE_API_SECRET = os.getenv("COINBASE_API_SECRET")

# Geographic location (for sunrise/sunset/moon rise — set to your city)
# Defaults to New York. Change in .env to your actual coordinates.
GEO_LAT = float(os.getenv("GEO_LAT", "40.7128"))   # positive = North
GEO_LON = float(os.getenv("GEO_LON", "-74.0060"))  # negative = West

# Bot behavior
DEFAULT_CURRENCY = os.getenv("DEFAULT_CURRENCY", "USD")
DEFAULT_CRYPTO = os.getenv("DEFAULT_CRYPTO", "BTC-USD")
MAX_TRADE_AMOUNT = float(os.getenv("MAX_TRADE_AMOUNT", "100"))
AUTO_TRADE = os.getenv("AUTO_TRADE", "false").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Paper trading — simulate all trades, no real orders placed
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"

# Risk management
SL_ATR_MULTIPLIER    = float(os.getenv("SL_ATR_MULTIPLIER", "1.5"))  # stop loss = 1.5x ATR
TP_RR_RATIO          = float(os.getenv("TP_RR_RATIO", "2.0"))        # take profit = 2x risk
TRADE_COOLDOWN_MINUTES = int(os.getenv("TRADE_COOLDOWN_MINUTES", "60"))  # 1 hour between trades

# Technical analysis candle settings
TA_CANDLE_GRANULARITY = os.getenv("TA_CANDLE_GRANULARITY", "ONE_HOUR")
TA_CANDLE_LIMIT       = int(os.getenv("TA_CANDLE_LIMIT", "100"))

# Minimum TA score required to confirm a cosmic signal
TA_MIN_SCORE = int(os.getenv("TA_MIN_SCORE", "2"))

# Trade journal file path
TRADE_LOG_FILE = os.getenv("TRADE_LOG_FILE", "trade_journal.json")

# Fibonacci levels used for analysis
FIBONACCI_LEVELS = [0.236, 0.382, 0.500, 0.618, 0.786, 1.000, 1.272, 1.618, 2.618]

# Gann Square of 9 angular increments (degrees)
GANN_ANGLES = [90, 180, 270, 360]

# Aspect scoring table: aspect_name -> (degrees, tolerance, score)
PLANET_ASPECTS = {
    "conjunction": (0,   8,  7),
    "sextile":     (60,  6,  4),
    "square":      (90,  8, -6),
    "trine":       (120, 8,  8),
    "opposition":  (180, 8, -8),
    "quincunx":    (150, 3, -2),
}

# Signal thresholds
OMEGA_THRESHOLD  = 15
ALPHA_THRESHOLD  = 8
BETA_THRESHOLD   = 2
VOID_THRESHOLD   = -10

# Risk per signal class (as fraction of account)
RISK_TABLE = {
    "OMEGA": 0.02,
    "ALPHA": 0.015,
    "BETA":  0.0075,
    "GAMMA": 0.0,
    "VOID":  0.0,
}

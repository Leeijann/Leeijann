import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Coinbase
COINBASE_API_KEY = os.getenv("COINBASE_API_KEY")
COINBASE_API_SECRET = os.getenv("COINBASE_API_SECRET")

# Bot behavior
DEFAULT_CURRENCY = os.getenv("DEFAULT_CURRENCY", "USD")
DEFAULT_CRYPTO = os.getenv("DEFAULT_CRYPTO", "BTC-USD")
MAX_TRADE_AMOUNT = float(os.getenv("MAX_TRADE_AMOUNT", "100"))
AUTO_TRADE = os.getenv("AUTO_TRADE", "false").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

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

import os
from dotenv import load_dotenv

# --- Load .env file ---
project_root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
dotenv_path = os.path.join(project_root_dir, '.env')

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
else:
    print(f"WARNING: .env file not found at: {dotenv_path}. Using default values.")

# --- Determine Trading Mode ---
TRADING_MODE = os.getenv("TRADING_MODE", "TESTNET").upper()
if TRADING_MODE not in ["TESTNET", "LIVE"]:
    print(f"WARNING: Invalid TRADING_MODE '{TRADING_MODE}'. Defaulting to 'TESTNET'.")
    TRADING_MODE = "TESTNET"

# --- API Credentials & URLs ---
BINANCE_API_KEY = None
BINANCE_API_SECRET = None
BINANCE_FUTURES_BASE_URL = None

if TRADING_MODE == "TESTNET":
    BINANCE_API_KEY = os.getenv("BINANCE_TESTNET_API_KEY")
    BINANCE_API_SECRET = os.getenv("BINANCE_TESTNET_API_SECRET")
    BINANCE_FUTURES_BASE_URL = "https://testnet.binancefuture.com"
elif TRADING_MODE == "LIVE":
    BINANCE_API_KEY = os.getenv("BINANCE_LIVE_API_KEY")
    BINANCE_API_SECRET = os.getenv("BINANCE_LIVE_API_SECRET")
    BINANCE_FUTURES_BASE_URL = "https://fapi.binance.com" 

# --- Trading Engine Parameters ---
ENGINE_LOOP_INTERVAL_SECONDS = int(os.getenv("ENGINE_LOOP_INTERVAL_SECONDS", 300))
SCAN_TOP_N_SYMBOLS = int(os.getenv("SCAN_TOP_N_SYMBOLS", 20))
default_min_volume = 10000 if TRADING_MODE == "TESTNET" else 50000000
MIN_24H_QUOTE_VOLUME = float(os.getenv("MIN_24H_QUOTE_VOLUME", default_min_volume))
MAX_CONCURRENT_POSITIONS = int(os.getenv("MAX_CONCURRENT_POSITIONS", 1))
POSITION_SIZE_USDT = float(os.getenv("POSITION_SIZE_USDT", 500.0)) # Default set to 500 as you requested
LEVERAGE = int(os.getenv("TRADING_LEVERAGE", 10))

ATR_PERIOD = int(os.getenv("ATR_PERIOD", 14))
ATR_SL_MULTIPLIER = float(os.getenv("ATR_SL_MULTIPLIER", 1.5))
ATR_TP_MULTIPLIER = float(os.getenv("ATR_TP_MULTIPLIER", 3.0))

# --- Strategy Parameters (Loaded from .env) ---
STRATEGY_KLINE_INTERVAL = os.getenv("STRATEGY_KLINE_INTERVAL", "15m")
STRATEGY_KLINE_LIMIT = int(os.getenv("STRATEGY_KLINE_LIMIT", 200))
# Multi-Timeframe Analysis (MTA)
MTA_KLINE_INTERVAL = os.getenv("MTA_KLINE_INTERVAL", "1h")
MTA_SHORT_EMA_PERIOD = int(os.getenv("MTA_SHORT_EMA_PERIOD", 20))
MTA_LONG_EMA_PERIOD = int(os.getenv("MTA_LONG_EMA_PERIOD", 50))
# Stochastic RSI
STOCH_RSI_PERIOD = int(os.getenv("STOCH_RSI_PERIOD", 14))
STOCH_RSI_K = int(os.getenv("STOCH_RSI_K", 3))
STOCH_RSI_D = int(os.getenv("STOCH_RSI_D", 3))
STOCH_RSI_OVERSOLD = int(os.getenv("STOCH_RSI_OVERSOLD", 25))
STOCH_RSI_OVERBOUGHT = int(os.getenv("STOCH_RSI_OVERBOUGHT", 75))
# Bollinger Bands
STRATEGY_BOLLINGER_PERIOD = int(os.getenv("STRATEGY_BOLLINGER_PERIOD", 20))
STRATEGY_BOLLINGER_STD_DEV = int(os.getenv("STRATEGY_BOLLINGER_STD_DEV", 2))
# ATR Risk Management
ATR_PERIOD = int(os.getenv("ATR_PERIOD", 14))
ATR_SL_MULTIPLIER = float(os.getenv("ATR_SL_MULTIPLIER", 1.5))
ATR_TP_MULTIPLIER = float(os.getenv("ATR_TP_MULTIPLIER", 2.5))

# --- Logging Configuration ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG").upper()


# --- Data and Log File Paths ---
# Define absolute paths for data and log directories within the project root.
DATA_DIR = os.path.join(project_root_dir, "data")
LOG_DIR = os.path.join(project_root_dir, "logs")

TRADE_HISTORY_CSV_PATH = os.path.join(DATA_DIR, "trade_history.csv")
LOG_FILE_PATH = os.path.join(LOG_DIR, f"trading_bot_{TRADING_MODE.lower()}.log")

STATE_FILE_PATH = os.path.join(DATA_DIR, "open_positions.json")

# --- Logging Configuration ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG").upper()

# --- Telegram Notification Settings ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- Startup Configuration Printout ---
# This part can be removed or commented out later, but it's useful for debugging.
print("--- Trading Bot Configuration Loaded ---")
print(f"INFO: Trading Mode: {TRADING_MODE}")
# ... (and so on for other important parameters if you wish)
print("----------------------------------------")
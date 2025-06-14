# trading_bot/config/settings.py
import os
from dotenv import load_dotenv

# --- Load .env file ---
# This block finds the .env file at the project root directory
# (assuming this settings.py file is in a subdirectory like trading_bot/config/)
# and loads its variables into the environment.
project_root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
dotenv_path = os.path.join(project_root_dir, '.env')

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    # print(f"DEBUG: .env file loaded from: {dotenv_path}") # Optional: for debugging
else:
    # Use print here because logger is not configured yet.
    print(f"WARNING: .env file not found at: {dotenv_path}. Using default values.")

# --- Determine Trading Mode (This should be read first as other settings may depend on it) ---
# Read TRADING_MODE from .env, default to "TESTNET" if not set or invalid.
TRADING_MODE = os.getenv("TRADING_MODE", "TESTNET").upper()
if TRADING_MODE not in ["TESTNET", "LIVE"]:
    print(f"WARNING: Invalid TRADING_MODE '{TRADING_MODE}' in .env. Defaulting to 'TESTNET'.")
    TRADING_MODE = "TESTNET"


# --- API Credentials & URLs (selected based on TRADING_MODE) ---
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


# --- Centralized Trading & Engine Parameters ---
# Read from .env, provide a default value, and cast to the correct type.
# This makes the rest of the application cleaner.

# General Trading Parameters
LEVERAGE = int(os.getenv("TRADING_LEVERAGE", 10))
DEFAULT_SYMBOL = os.getenv("DEFAULT_TRADING_SYMBOL", "BTCUSDT")

# Market Scanner Parameters
SCAN_TOP_N_SYMBOLS = int(os.getenv("SCAN_TOP_N_SYMBOLS", 20))
# Use a different default min volume for TESTNET vs LIVE
default_min_volume = 10000 if TRADING_MODE == "TESTNET" else 50000000
MIN_24H_QUOTE_VOLUME = float(os.getenv("MIN_24H_QUOTE_VOLUME", default_min_volume))

# Trading Engine Parameters
ENGINE_LOOP_INTERVAL_SECONDS = int(os.getenv("ENGINE_LOOP_INTERVAL_SECONDS", 300)) # 5 minutes
MAX_CONCURRENT_POSITIONS = int(os.getenv("MAX_CONCURRENT_POSITIONS", 1))
POSITION_SIZE_USDT = float(os.getenv("POSITION_SIZE_USDT", 1000.0))
STOP_LOSS_PERCENTAGE = float(os.getenv("STOP_LOSS_PERCENTAGE", 0.01)) # 1%
TAKE_PROFIT_PERCENTAGE = float(os.getenv("TAKE_PROFIT_PERCENTAGE", 0.02)) # 2%


# --- Logging Configuration ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG").upper()
# Log file name can be dynamic based on the trading mode.
LOG_FILE = os.getenv("LOG_FILE", f"trading_bot_{TRADING_MODE.lower()}.log")

# --- Strategy Parameters (Loaded from .env) ---
STRATEGY_KLINE_INTERVAL = os.getenv("STRATEGY_KLINE_INTERVAL", "5m")
STRATEGY_KLINE_LIMIT = int(os.getenv("STRATEGY_KLINE_LIMIT", 100))
STRATEGY_SHORT_EMA_PERIOD = int(os.getenv("STRATEGY_SHORT_EMA_PERIOD", 12))
STRATEGY_LONG_EMA_PERIOD = int(os.getenv("STRATEGY_LONG_EMA_PERIOD", 26))


# --- Startup Configuration Printout ---
# This block prints the loaded configuration when the bot starts.
# It's useful for verifying that settings from the .env file are loaded correctly.
print("--- Trading Bot Configuration Loaded ---")
print(f"INFO: Trading Mode: {TRADING_MODE}")
print(f"INFO: API Key Loaded: {'Yes' if BINANCE_API_KEY and not BINANCE_API_KEY.startswith('YOUR_') else 'No or Placeholder'}")
print(f"INFO: Base URL: {BINANCE_FUTURES_BASE_URL}")
print(f"INFO: Default Symbol: {DEFAULT_SYMBOL}")
print(f"INFO: Leverage: {LEVERAGE}x")
print(f"INFO: Scan Top N Symbols: {SCAN_TOP_N_SYMBOLS}")
print(f"INFO: Min 24h Volume: {MIN_24H_QUOTE_VOLUME:,.0f} USDT")
print(f"INFO: Max Concurrent Positions: {MAX_CONCURRENT_POSITIONS}")
print(f"INFO: Position Size: {POSITION_SIZE_USDT} USDT (nominal)")
print(f"INFO: Stop-Loss: {STOP_LOSS_PERCENTAGE*100}%")
print(f"INFO: Take-Profit: {TAKE_PROFIT_PERCENTAGE*100}%")
print(f"INFO: Log Level: {LOG_LEVEL}")
print(f"INFO: Log File: {LOG_FILE}")
print("----------------------------------------")
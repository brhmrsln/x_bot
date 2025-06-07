# trading_bot/config/settings.py
import os
from dotenv import load_dotenv

# --- Load .env file ---
# Construct the absolute path to the project root directory
# Assumes settings.py is in 'algo_trading_project/trading_bot/config/'
# and .env is in 'algo_trading_project/'
project_root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
dotenv_path = os.path.join(project_root_dir, '.env')

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    # print(f"INFO: .env file loaded from: {dotenv_path}") # Optional: for debugging
else:
    print(f"WARNING: .env file not found at: {dotenv_path}. Ensure it exists and is correctly placed.")

# --- Determine Trading Mode ---
# Read TRADING_MODE from .env, default to "TESTNET" if not set or invalid
TRADING_MODE = os.getenv("TRADING_MODE", "TESTNET").upper()
if TRADING_MODE not in ["TESTNET", "LIVE"]:
    print(f"WARNING: Invalid TRADING_MODE ('{TRADING_MODE}') in .env file. Defaulting to 'TESTNET'.")
    TRADING_MODE = "TESTNET"

print(f"--- Selected Trading Mode: {TRADING_MODE} ---")

# --- API Credentials & URLs ---
BINANCE_API_KEY = None
BINANCE_API_SECRET = None
BINANCE_FUTURES_BASE_URL = None  # For USDT-M Futures

# Set API keys and base URL based on the selected trading mode
if TRADING_MODE == "TESTNET":
    BINANCE_API_KEY = os.getenv("BINANCE_TESTNET_API_KEY")
    BINANCE_API_SECRET = os.getenv("BINANCE_TESTNET_API_SECRET")
    BINANCE_FUTURES_BASE_URL = "https://testnet.binancefuture.com"  # Testnet USDT-M Futures URL
    print("INFO: Using TESTNET configuration.")
elif TRADING_MODE == "LIVE":
    BINANCE_API_KEY = os.getenv("BINANCE_LIVE_API_KEY")
    BINANCE_API_SECRET = os.getenv("BINANCE_LIVE_API_SECRET")
    BINANCE_FUTURES_BASE_URL = "https://fapi.binance.com"  # Production USDT-M Futures URL
    print("WARNING: Using LIVE (REAL MONEY) configuration!")

# Validate that API keys for the selected mode are loaded and not empty
if not BINANCE_API_KEY:
    error_message = f"CRITICAL: BINANCE_{TRADING_MODE}_API_KEY is not found or is empty in .env for the selected mode ({TRADING_MODE})."
    print(error_message)
    raise ValueError(error_message)
if not BINANCE_API_SECRET:
    error_message = f"CRITICAL: BINANCE_{TRADING_MODE}_API_SECRET is not found or is empty in .env for the selected mode ({TRADING_MODE})."
    print(error_message)
    raise ValueError(error_message)

# --- Common Trading Parameters ---
# These can also be made mode-specific by reading from .env like TRADING_LEVERAGE_<MODE>
DEFAULT_LEVERAGE_TESTNET = 10
DEFAULT_LEVERAGE_LIVE = 10 # Be cautious with live leverage

# Read leverage for the current mode from .env, or use mode-specific defaults
LEVERAGE_KEY_IN_ENV = f"TRADING_LEVERAGE_{TRADING_MODE}"
DEFAULT_LEVERAGE_FOR_MODE = DEFAULT_LEVERAGE_LIVE if TRADING_MODE == "LIVE" else DEFAULT_LEVERAGE_TESTNET
LEVERAGE = int(os.getenv(LEVERAGE_KEY_IN_ENV, DEFAULT_LEVERAGE_FOR_MODE))

DEFAULT_SYMBOL = os.getenv("DEFAULT_TRADING_SYMBOL", "BTCUSDT")

MIN_24H_QUOTE_VOLUME = os.getenv("MIN_24H_QUOTE_VOLUME") 

# --- Logging Configuration ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper() # Ensure log level is uppercase
LOG_FILE = os.getenv("LOG_FILE", f"trading_bot_{TRADING_MODE.lower()}.log") # Mode-specific log file name

# --- Print loaded configuration for verification ---
print(f"INFO: API Key (first 5 chars): {str(BINANCE_API_KEY)[:5] if BINANCE_API_KEY else 'Not set!'}")
print(f"INFO: API Secret (first 5 chars): {str(BINANCE_API_SECRET)[:5] if BINANCE_API_SECRET else 'Not set!'}")
print(f"INFO: Futures Base URL: {BINANCE_FUTURES_BASE_URL}")
print(f"INFO: Leverage: {LEVERAGE}")
print(f"INFO: Default Symbol: {DEFAULT_SYMBOL}")
print(f"INFO: Log Level: {LOG_LEVEL}")
print(f"INFO: Log File: {LOG_FILE}")
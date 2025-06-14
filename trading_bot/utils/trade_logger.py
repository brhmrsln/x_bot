# trading_bot/utils/trade_logger.py
import os
import csv
import logging
from datetime import datetime

# Import the central settings module to get the configured file path
try:
    from trading_bot.config import settings
except ImportError:
    # This fallback is mainly for isolated tests or if the script is run in a strange way.
    # In our main application flow (via main.py), settings will always be available.
    print("WARNING: Could not import 'settings' in trade_logger.py. Using a default file path 'trade_history.csv'.")
    class MockSettings:
        TRADE_HISTORY_CSV_PATH = "trade_history.csv"
    settings = MockSettings()

# Get the main logger instance to log potential errors related to this module
logger = logging.getLogger("trading_bot")

# --- Configuration ---
# The path is now centrally managed and pulled from settings.py
TRADE_LOG_FILE_PATH = settings.TRADE_HISTORY_CSV_PATH 
CSV_HEADERS = [
    'timestamp_utc', 
    'symbol', 
    'side', 
    'quantity', 
    'entry_price', 
    'exit_price', 
    'pnl_usdt',         # Net PnL (already includes commission deduction from API)
    'pnl_percentage', 
    'entry_commission', # Commission for the entry trade
    'exit_commission',  # Commission for the closing trade (SL or TP)
    'total_commission', # Sum of entry and exit commissions
    'entry_reason', 
    'exit_reason'
]

def setup_trade_log_file():
    """
    Ensures the trade log directory and the CSV file with headers exist.
    This function is called automatically by log_trade before writing.
    """
    try:
        # Get the directory part from the full file path (e.g., 'data/')
        log_dir = os.path.dirname(TRADE_LOG_FILE_PATH)
        
        # Create the directory if it doesn't already exist
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
            logger.info(f"Data directory created: {log_dir}")
        
        # Check if the file exists and is empty to decide whether to write headers
        file_exists = os.path.isfile(TRADE_LOG_FILE_PATH)
        is_empty = os.path.getsize(TRADE_LOG_FILE_PATH) == 0 if file_exists else True
        
    except FileNotFoundError:
        is_empty = True # File doesn't exist, so it's "empty" and headers should be written
    except Exception as e:
        logger.error(f"Error checking or creating trade log file/directory '{TRADE_LOG_FILE_PATH}': {e}", exc_info=True)
        return # Do not proceed if we can't check/create the file/dir

    if is_empty:
        try:
            with open(TRADE_LOG_FILE_PATH, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(CSV_HEADERS)
                logger.info(f"Trade log file '{TRADE_LOG_FILE_PATH}' created with headers.")
        except Exception as e:
            logger.error(f"Failed to create and write headers to trade log file '{TRADE_LOG_FILE_PATH}': {e}", exc_info=True)

def log_trade(trade_data: dict):
    """
    Appends a completed trade's details to the CSV log file.
    
    :param trade_data: A dictionary containing all relevant details of the closed trade.
    """
    setup_trade_log_file() # Ensure file and headers exist before writing

    # Prepare the row data in the correct order as defined in CSV_HEADERS
    row_to_write = [
        datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        trade_data.get('symbol', 'N/A'),
        trade_data.get('side', 'N/A'),
        trade_data.get('quantity', 0.0),
        f"{trade_data.get('entry_price', 0.0):.8f}".rstrip('0').rstrip('.'),
        f"{trade_data.get('exit_price', 0.0):.8f}".rstrip('0').rstrip('.'),
        f"{trade_data.get('pnl_usdt', 0.0):.8f}".rstrip('0').rstrip('.'),
        f"{trade_data.get('pnl_percentage', 0.0) * 100:.4f}%",
        f"{trade_data.get('entry_commission', 0.0):.8f}".rstrip('0').rstrip('.'),
        f"{trade_data.get('exit_commission', 0.0):.8f}".rstrip('0').rstrip('.'),
        f"{trade_data.get('total_commission', 0.0):.8f}".rstrip('0').rstrip('.'),
        trade_data.get('entry_reason', 'N/A'),
        trade_data.get('exit_reason', 'N/A')
    ]

    try:
        # Open the file in append mode ('a') to add a new row
        with open(TRADE_LOG_FILE_PATH, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(row_to_write)
            logger.info(f"Successfully logged completed trade for {trade_data.get('symbol')} to '{TRADE_LOG_FILE_PATH}'.")
    except Exception as e:
        # Fallback to the main logger if file writing fails for any reason
        logger.error(f"CRITICAL: Failed to write completed trade to log file '{TRADE_LOG_FILE_PATH}': {e}", exc_info=True)
        logger.info(f"Failed trade log data was: {row_to_write}")
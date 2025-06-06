# trading_bot/utils/trade_logger.py
import os
import csv
import logging
from datetime import datetime

# Get the main logger instance to log potential errors with this module itself
logger = logging.getLogger("trading_bot")

# --- Configuration ---
# You can move this path to settings.py later to make it more configurable
TRADE_LOG_FILE_PATH = "trade_history.csv" 
# Define the headers for our trade log CSV file
CSV_HEADERS = [
    'timestamp_utc', 
    'symbol', 
    'side', 
    'quantity', 
    'entry_price', 
    'exit_price', 
    'pnl_usdt', 
    'pnl_percentage', 
    'entry_reason', 
    'exit_reason'
]

def setup_trade_log_file():
    """
    Creates the trade log CSV file with headers if it doesn't exist.
    This function is called automatically by log_trade before writing.
    """
    try:
        # Check if file exists and is empty to avoid writing headers repeatedly
        file_exists = os.path.isfile(TRADE_LOG_FILE_PATH)
        # Check size to determine if it's a new/empty file
        is_empty = os.path.getsize(TRADE_LOG_FILE_PATH) == 0 if file_exists else True
    except FileNotFoundError:
        is_empty = True # File doesn't exist, so it's "empty"
    except Exception as e:
        logger.error(f"Error checking trade log file '{TRADE_LOG_FILE_PATH}': {e}", exc_info=True)
        return # Do not proceed if we can't check the file status

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
                       Example: {
                           'symbol': 'BTCUSDT', 
                           'side': 'LONG', 
                           'quantity': 0.01,
                           'entry_price': 50000.0, 
                           'exit_price': 50500.0,
                           'pnl_usdt': 5.0, 
                           'pnl_percentage': 0.01, # e.g., 1% as a float 0.01
                           'entry_reason': 'EMA_CROSSOVER_BUY', 
                           'exit_reason': 'TAKE_PROFIT'
                       }
    """
    setup_trade_log_file() # Ensure file and headers exist before writing

    # Prepare the row data in the correct order as defined in CSV_HEADERS
    row_to_write = [
        datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), # Current timestamp in UTC
        trade_data.get('symbol', 'N/A'),
        trade_data.get('side', 'N/A'),
        trade_data.get('quantity', 0.0),
        trade_data.get('entry_price', 0.0),
        trade_data.get('exit_price', 0.0),
        f"{trade_data.get('pnl_usdt', 0.0):.4f}", # Format PnL for cleaner output
        f"{trade_data.get('pnl_percentage', 0.0) * 100:.2f}%", # Format percentage nicely
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
        logger.info(f"Failed trade log data was: {trade_data}")
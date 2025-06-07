# trading_bot/utils/trade_logger.py
import os
import csv
import logging
from datetime import datetime

logger = logging.getLogger("trading_bot")

TRADE_LOG_FILE_PATH = "trade_history.csv" 
# Add new columns for commission
CSV_HEADERS = [
    'timestamp_utc', 'symbol', 'side', 'quantity', 'entry_price', 
    'exit_price', 'pnl_usdt', 'pnl_percentage', 
    'entry_commission', 'exit_commission', 'total_commission', # YENİ SÜTUNLAR
    'entry_reason', 'exit_reason'
]

def setup_trade_log_file():
    """Creates the trade log CSV file with headers if it doesn't exist."""
    try:
        file_exists = os.path.isfile(TRADE_LOG_FILE_PATH)
        is_empty = os.path.getsize(TRADE_LOG_FILE_PATH) == 0 if file_exists else True
    except FileNotFoundError:
        is_empty = True
    except Exception as e:
        logger.error(f"Error checking trade log file '{TRADE_LOG_FILE_PATH}': {e}")
        return

    if is_empty:
        try:
            with open(TRADE_LOG_FILE_PATH, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(CSV_HEADERS)
                logger.info(f"Trade log file '{TRADE_LOG_FILE_PATH}' created with headers.")
        except Exception as e:
            logger.error(f"Failed to create and write headers to trade log file '{TRADE_LOG_FILE_PATH}': {e}")

def log_trade(trade_data: dict):
    """Appends a completed trade's details to the CSV log file."""
    setup_trade_log_file() # Ensure file and headers exist

    # Prepare the row data in the correct order, including new commission fields
    row_to_write = [
        datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        trade_data.get('symbol', 'N/A'),
        trade_data.get('side', 'N/A'),
        trade_data.get('quantity', 0.0),
        trade_data.get('entry_price', 0.0),
        trade_data.get('exit_price', 0.0),
        f"{trade_data.get('pnl_usdt', 0.0):.4f}",
        f"{trade_data.get('pnl_percentage', 0.0) * 100:.2f}%",
        # New commission data
        f"{trade_data.get('entry_commission', 0.0):.6f}",
        f"{trade_data.get('exit_commission', 0.0):.6f}",
        f"{trade_data.get('total_commission', 0.0):.6f}",
        trade_data.get('entry_reason', 'N/A'),
        trade_data.get('exit_reason', 'N/A')
    ]

    try:
        with open(TRADE_LOG_FILE_PATH, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(row_to_write)
            logger.info(f"Successfully logged completed trade for {trade_data.get('symbol')} with commissions.")
    except Exception as e:
        logger.error(f"CRITICAL: Failed to write completed trade to log file '{TRADE_LOG_FILE_PATH}': {e}", exc_info=True)
        logger.info(f"Failed trade log data was: {trade_data}")
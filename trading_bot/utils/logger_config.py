# trading_bot/utils/logger_config.py
import logging
import sys
import os
import colorlog
from logging.handlers import RotatingFileHandler 
from colorlog import ColoredFormatter # Import ColoredFormatter

try:
    from trading_bot.config import settings
except ImportError:
    # Fallback logic as before... (omitted for brevity in this example, but keep it in your actual file)
    print("DEBUG: Could not import 'from trading_bot.config import settings'. Attempting relative path adjustment for settings.")
    current_dir = os.path.dirname(os.path.abspath(__file__))
    trading_bot_dir = os.path.dirname(current_dir)
    project_root_dir = os.path.dirname(trading_bot_dir)
    if project_root_dir not in sys.path:
        sys.path.insert(0, project_root_dir)
    from trading_bot.config import settings


def setup_logger(name="trading_bot"):
    """
    Sets up a logger with console and rotating file handlers.

    The logger will output to both the console with colored messages
    and to a log file specified in the settings.

    :param name: The name of the logger to configure.
    :return: The configured logger instance.
    """
    # 1. Get Log Level from settings
    log_level_str = settings.LOG_LEVEL.upper()
    numeric_level = getattr(logging, log_level_str, logging.INFO)

    # 2. Get Logger and remove existing handlers to prevent duplicates
    logger = logging.getLogger(name)
    logger.setLevel(numeric_level)
    
    # Check if handlers already exist and clear them
    if logger.hasHandlers():
        logger.handlers.clear()

    # 3. Console Handler (with colors)
    console_handler = colorlog.StreamHandler()
    console_formatter = colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s - %(name)s - %(levelname)-8s - %(message)s',
        log_colors={
            'DEBUG':    'cyan',
            'INFO':     'green',
            'WARNING':  'yellow',
            'ERROR':    'red',
            'CRITICAL': 'red,bg_white',
        }
    )
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(numeric_level)
    logger.addHandler(console_handler)

    # 4. File Handler (with rotation)
    log_file_path = settings.LOG_FILE_PATH # Get the full, absolute path from settings

    # Ensure the log directory exists before creating the file handler
    try:
        log_dir = os.path.dirname(log_file_path)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            logger.info(f"Log directory created: {log_dir}")
    except OSError as e:
        # If we can't create the log directory, disable file logging and warn
        logger.error(f"Could not create log directory '{log_dir}'. File logging will be disabled. Error: {e}")
        log_file_path = None

    if log_file_path:
        # Use RotatingFileHandler to prevent log files from growing indefinitely.
        # This will create up to 5 backup files of 5MB each.
        file_handler = RotatingFileHandler(
            log_file_path, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8'
        )
        # File handler should use a standard, non-colored formatter
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)-8s - %(message)s')
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(numeric_level)
        logger.addHandler(file_handler)

    # Prevent messages from propagating to the root logger's handlers
    logger.propagate = False
    
    logger.info(f"Logging initialized. Level: {log_level_str}. Console: Colored. Log file: {log_file_path if log_file_path else 'Disabled'}")

    return logger
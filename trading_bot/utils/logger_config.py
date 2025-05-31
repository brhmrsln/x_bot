# trading_bot/utils/logger_config.py
import logging
import sys
import os
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
    Configures and returns a logger instance for the application.
    Logs to console with colors and to a file specified in settings.
    """
    log_level_str = getattr(settings, 'LOG_LEVEL', 'INFO').upper()
    numeric_level = getattr(logging, log_level_str, logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(numeric_level)

    if logger.hasHandlers():
        logger.handlers.clear()

    # --- Console Handler with Colors ---
    # Define log colors for different levels
    log_colors_config = {
        'DEBUG':    'cyan',
        'INFO':     'green',
        'WARNING':  'yellow',
        'ERROR':    'red',
        'CRITICAL': 'bold_red',
    }
    # Define the format for console, incorporating colors
    console_log_format = (
        '%(log_color)s%(asctime)s - %(name)s - %(levelname)-8s - %(message)s' # -8s for levelname alignment
    )
    console_formatter = ColoredFormatter(
        fmt=console_log_format,
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors=log_colors_config
    )
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(console_formatter) # Use ColoredFormatter for console
    logger.addHandler(console_handler)

    # --- File Handler (without colors) ---
    # Standard formatter for the file, as ANSI color codes are not ideal in files.
    file_log_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)-8s - %(message)s', # -8s for levelname alignment
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    log_file_path_str = getattr(settings, 'LOG_FILE', None)
    if log_file_path_str:
        try:
            log_file_dir = os.path.dirname(os.path.abspath(log_file_path_str))
            if log_file_dir and not os.path.exists(log_file_dir):
                os.makedirs(log_file_dir, exist_ok=True)

            file_handler = logging.FileHandler(log_file_path_str, mode='a')
            file_handler.setLevel(numeric_level)
            file_handler.setFormatter(file_log_formatter) # Use standard Formatter for file
            logger.addHandler(file_handler)
        except Exception as e:
            # Log error to console (which is already set up with ColoredFormatter)
            logger.error(f"Failed to initialize file logging to {log_file_path_str}: {e}", exc_info=False)
            log_file_path_str = None 
    
    if log_file_path_str:
        logger.info(f"Logging initialized. Level: {log_level_str}. Console: Colored. Log file: {log_file_path_str}")
    else:
        logger.info(f"Logging initialized (console only, colored). Level: {log_level_str}. No log file specified or accessible.")

    # Optional: Set levels for other verbose loggers
    # logging.getLogger("binance").setLevel(logging.WARNING)
    # logging.getLogger("httpx").setLevel(logging.WARNING)
        
    logger.propagate = False
    
    return logger
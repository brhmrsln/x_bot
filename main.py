# main.py - The main entry point for the trading bot application.

import logging
import time
import sys

# --- Imports from our project structure ---
# Using a try-except block for imports is a good practice if the script could
# be run from different locations, but with a clear entry point, it's often cleaner
# to ensure the environment (PYTHONPATH) is set up correctly.
# If you run `python main.py` from the project root, these imports should work.
try:
    from trading_bot.utils.logger_config import setup_logger
    from trading_bot.config import settings
    from trading_bot.exchange.binance_client import BinanceFuturesClient
    from trading_bot.core.strategy import Strategy
    from trading_bot.core.trading_engine import TradingEngine
except ImportError as e:
    # This might happen if the script is not run from the project's root directory.
    # We add the project root to sys.path to resolve this.
    import os
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
        print(f"DEBUG: Added project root to sys.path: {project_root}")
    # Retry imports
    from trading_bot.utils.logger_config import setup_logger
    from trading_bot.config import settings
    from trading_bot.exchange.binance_client import BinanceFuturesClient
    from trading_bot.core.strategy import Strategy
    from trading_bot.core.trading_engine import TradingEngine

# --- Main Application Logic ---

def main():
    """
    The main function to initialize and run the trading bot.
    """
    # 1. Setup the logger as the very first step
    # The logger instance will be available globally via logging.getLogger("trading_bot")
    logger = setup_logger(name="trading_bot")
    logger.info("=====================================================")
    logger.info("              STARTING ALGO TRADING BOT              ")
    logger.info("=====================================================")
    logger.info(f"Running in {settings.TRADING_MODE} mode.")

    # 2. Initialize the Binance Futures Client
    try:
        client = BinanceFuturesClient()
        logger.info("Binance Futures Client initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize Binance Futures Client: {e}", exc_info=True)
        logger.critical("Bot cannot start without a working client. Exiting.")
        return # Exit the application if client fails to initialize

    # 3. Initialize the Trading Strategy
    # Strategy parameters can be defined here or loaded from a config file
    strategy_params = {
        "symbol": settings.DEFAULT_SYMBOL, 
        "kline_interval": settings.STRATEGY_KLINE_INTERVAL, 
        "kline_limit": settings.STRATEGY_KLINE_LIMIT,
        "short_ema_period": settings.STRATEGY_SHORT_EMA_PERIOD,
        "long_ema_period": settings.STRATEGY_LONG_EMA_PERIOD
    }
    strategy = Strategy(client=client, strategy_params=strategy_params)
    logger.info("Trading Strategy initialized successfully with configurable parameters.")

    # 4. Initialize and run the Trading Engine
    # The engine is the core that brings the client and strategy together.
    engine = TradingEngine(client=client, strategy=strategy)
    logger.info("Trading Engine initialized successfully.")
    
    # This will start the main loop of the bot
    engine.run()
    
    # The code will block here inside engine.run() until it's stopped.
    logger.info("Trading Engine has been stopped. Main application exiting.")


if __name__ == "__main__":
    # This is the official entry point of the application
    try:
        main()
    except KeyboardInterrupt:
        print("\nINFO: KeyboardInterrupt received. Shutting down gracefully...")
        # The engine's run loop should handle this to set its running flag to False,
        # but we can also log a final message here.
    except Exception as e:
        # Log any uncaught exceptions from the main function
        # A logger might not be available if setup_logger failed, so we print as a fallback.
        print(f"CRITICAL: An unhandled exception occurred in main: {e}")
        # If logger is available, use it
        if logging.getLogger("trading_bot").hasHandlers():
            logging.getLogger("trading_bot").critical(f"An unhandled exception occurred in main: {e}", exc_info=True)
    finally:
        if logging.getLogger("trading_bot").hasHandlers():
            logging.getLogger("trading_bot").info("Bot shutdown complete.")
        else:
            print("INFO: Bot shutdown complete.")
        
        logging.shutdown()
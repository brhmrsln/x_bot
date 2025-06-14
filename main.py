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
except ImportError:
    import os
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
        print(f"DEBUG: Added project root to sys.path: {project_root}")
    from trading_bot.utils.logger_config import setup_logger
    from trading_bot.config import settings
    from trading_bot.exchange.binance_client import BinanceFuturesClient
    from trading_bot.core.strategy import Strategy
    from trading_bot.core.trading_engine import TradingEngine

# --- Main Application Logic ---
def main():
    """The main function to initialize and run the trading bot."""
    logger = setup_logger(name="trading_bot")
    logger.info("=====================================================")
    logger.info("              STARTING ALGO TRADING BOT              ")
    logger.info("=====================================================")
    
    try:
        # 1. Initialize the Binance Futures Client
        client = BinanceFuturesClient()
        logger.info("Binance Futures Client initialized successfully.")

        # 2. Initialize the Trading Strategy with parameters from settings
        strategy_params = {
            "kline_interval": settings.STRATEGY_KLINE_INTERVAL,
            "kline_limit": settings.STRATEGY_KLINE_LIMIT,
            "mta_kline_interval": settings.MTA_KLINE_INTERVAL,
            "mta_ema_period": settings.MTA_EMA_PERIOD,
            "short_ema_period": settings.STRATEGY_SHORT_EMA_PERIOD,
            "long_ema_period": settings.STRATEGY_LONG_EMA_PERIOD,
            "rsi_period": settings.STRATEGY_RSI_PERIOD,
            "rsi_overbought": settings.STRATEGY_RSI_OVERBOUGHT,
            "rsi_oversold": settings.STRATEGY_RSI_OVERSOLD,
            "bollinger_period": settings.STRATEGY_BOLLINGER_PERIOD,
            "bollinger_std_dev": settings.STRATEGY_BOLLINGER_STD_DEV,
        }
        strategy = Strategy(client=client, strategy_params=strategy_params)
        logger.info("Trading Strategy initialized successfully.")

        # 3. Initialize and run the Trading Engine
        engine = TradingEngine(client=client, strategy=strategy)
        logger.info("Trading Engine initialized successfully.")
        
        engine.run()
        
        logger.info("Trading Engine has been stopped. Main application exiting.")

    except Exception as e:
        # Catch exceptions during initialization phase
        if 'logger' in locals():
            logger.critical(f"A critical error occurred during bot initialization: {e}", exc_info=True)
            logger.critical("Bot will exit.")
        else:
            print(f"CRITICAL: A critical error occurred during bot initialization: {e}")
        return # Exit if initialization fails


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # The engine's own loop handles the shutdown message, so we can just print a final exit message.
        print("\nINFO: KeyboardInterrupt received. Bot shutting down.")
    finally:
        if logging.getLogger("trading_bot").hasHandlers():
            logging.getLogger("trading_bot").info("Bot shutdown complete.")
        else:
            print("INFO: Bot shutdown complete.")
        logging.shutdown()
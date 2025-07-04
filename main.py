# main.py - The main entry point for the trading bot application.

import logging
import time
import sys
import os

try:
    from trading_bot.utils.logger_config import setup_logger
    from trading_bot.config import settings
    from trading_bot.exchange.binance_client import BinanceFuturesClient
    from trading_bot.core.trading_engine import TradingEngine
    from trading_bot.utils.notifier import send_telegram_message
    from trading_bot.core.strategy_factory import StrategyFactory
except ImportError as e:
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from trading_bot.utils.logger_config import setup_logger
    from trading_bot.config import settings
    from trading_bot.exchange.binance_client import BinanceFuturesClient
    from trading_bot.core.trading_engine import TradingEngine
    from trading_bot.utils.notifier import send_telegram_message
    from trading_bot.core.strategy_factory import StrategyFactory

def main():
    """The main function to initialize and run the trading bot."""
    logger = setup_logger(name="trading_bot")
    logger.info("=====================================================")
    logger.info("              STARTING ALGO TRADING BOT              ")
    logger.info(f"       Strategy: {settings.STRATEGY_NAME.upper()}   ")
    logger.info("=====================================================")

    send_telegram_message(f"✅ **X_bot STARTED** ✅\nStrategy: `{settings.STRATEGY_NAME}`")
    
    try:
        client = BinanceFuturesClient()
        logger.info("Binance Futures Client initialized successfully.")

        # 1. Get the strategy CLASS from the factory
        strategy_name = settings.STRATEGY_NAME
        logger.info(f"Loading strategy '{strategy_name}'...")
        strategy_class = StrategyFactory(strategy_name)

        # 2. Get required parameters from the class itself (static method)
        required_params_map = strategy_class.get_required_parameters()
        
        # 3. Dynamically build the parameters dictionary from settings
        strategy_params = {}
        for key, setting_name in required_params_map.items():
            if hasattr(settings, setting_name):
                strategy_params[key] = getattr(settings, setting_name)
            else:
                logger.error(f"Setting '{setting_name}' not found in settings.py!")
                raise ValueError(f"Missing required setting in settings.py: {setting_name}")
        
        logger.info(f"Strategy Parameters Loaded: {strategy_params}")
        
        # 4. Create the final strategy INSTANCE with the parameters
        strategy = strategy_class(strategy_params)
        
        logger.info(f"Strategy '{strategy_name}' initialized successfully.")

        # 5. Initialize and run the Trading Engine
        engine = TradingEngine(client=client, strategy=strategy)
        # engine.run() is called from main script, not here anymore
        
    except Exception as e:
        logger.critical(f"A critical error occurred during bot initialization: {e}", exc_info=True)
        logger.critical("Bot will exit.")
        send_telegram_message(f"❌ **CRITICAL ERROR** ❌\nBot failed to start!\n`{e}`")
        return

    # This part should be outside the try block if engine.run() is the main loop
    try:
        if 'engine' in locals():
            engine.run()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received in main. Stopping engine.")
        if 'engine' in locals():
            engine.stop()
    finally:
        logger.info("Main function finished.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Final catch-all for any exceptions that might slip through
        logging.getLogger("trading_bot").critical(f"Unhandled exception at the top level: {e}", exc_info=True)
    finally:
        shutdown_message = "🛑 **X_bot SHUTDOWN** 🛑"
        send_telegram_message(shutdown_message)
        
        logger = logging.getLogger("trading_bot")
        if logger.hasHandlers():
            logger.info("Bot shutdown complete.")
        else:
            print("INFO: Bot shutdown complete.")
        
        logging.shutdown()
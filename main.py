# main.py
import logging # Standard library
# from trading_bot.config import settings # Import settings if you need to access them directly
from trading_bot.utils.logger_config import setup_logger

# --- Initialize the logger as early as possible ---
# The setup_logger() function configures and returns the logger instance.
# Any subsequent calls to logging.getLogger("trading_bot") in other modules
# will get this configured logger instance.

logger = setup_logger(name="trading_bot") # Using "trading_bot" as the main logger name

# --- Import other necessary modules after logger setup if they also use logging ---
# from trading_bot.exchange.binance_client import BinanceFuturesClient
# from trading_bot.core.trading_engine import TradingEngine # Example

def main_application_logic():
    """
    Contains the main logic of the trading bot.
    """
    logger.info("Starting the Algo Trading Bot application...")
    
    # Access settings through the already imported settings module within other modules,
    # or if needed here: from trading_bot.config import settings
    # logger.info(f"Running in {settings.TRADING_MODE} mode.") # Example of using settings

    # --- Example: Initialize Binance Client (ensure it uses the same logger name or gets it) ---
    # try:
    #     logger.info("Initializing Binance Futures Client...")
    #     # client = BinanceFuturesClient() # Assuming BinanceFuturesClient uses logging.getLogger("trading_bot")
    #     # server_time = client.get_server_time()
    #     # if server_time:
    #     #     logger.info(f"Binance Server Time (epoch ms): {server_time.get('serverTime')}")
    #     logger.info("Binance Futures Client initialization placeholder successful.")
    # except Exception as e:
    #     logger.error(f"Failed to initialize Binance Futures Client: {e}", exc_info=True)
    #     return # Critical component failed, might need to exit

    # --- Example: Initialize Trading Engine ---
    # logger.info("Initializing Trading Engine...")
    # # engine = TradingEngine(client=client)
    # logger.info("Trading Engine initialization placeholder successful.")

    # --- Example: Start Trading Engine ---
    # logger.info("Starting Trading Engine main loop...")
    # # engine.run() # This would be a blocking call or start a new thread/process

    logger.info("Main application logic has completed its setup phase.")
    # Keep the bot running or perform periodic tasks
    # For a real bot, this might involve an infinite loop or a scheduler.
    # For now, we'll just simulate some activity.
    logger.debug("This is a debug message from main_application_logic.")
    logger.warning("This is a sample warning message.")


if __name__ == "__main__":
    try:
        main_application_logic()
        # If main_application_logic is a setup and then something else runs (e.g. a loop in TradingEngine),
        # this might be reached after that loop finishes or if setup is all it does.
        logger.info("Algo Trading Bot application has finished or is shutting down gracefully.")
    except KeyboardInterrupt:
        logger.warning("Bot stopped manually by user (KeyboardInterrupt).")
    except Exception as e:
        # Log any unhandled exceptions from the main application logic
        logger.critical(f"An unhandled critical error occurred in the application: {e}", exc_info=True)
    finally:
        # This ensures that all log messages are flushed and handlers are closed.
        logging.shutdown()
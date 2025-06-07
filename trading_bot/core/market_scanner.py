# trading_bot/core/market_scanner.py
import logging
# from trading_bot.exchange.binance_client import BinanceFuturesClient # For type hinting if needed in other contexts

logger = logging.getLogger("trading_bot")

def get_top_volume_usdt_futures_symbols(client, count=20, min_quote_volume=50000000):
    """
    Fetches USDT-margined PERPETUAL futures symbols, filters them by trading status
    and minimum 24h quote volume, and returns the top 'count' symbols ranked by volume.

    :param client: Instance of BinanceFuturesClient.
    :param count: Number of top symbols to return.
    :param min_quote_volume: Minimum 24h quote volume in USDT to consider a symbol.
    :return: List of symbol strings (e.g., ["BTCUSDT", "ETHUSDT"]), or an empty list.
    """
    logger.info(f"Attempting to fetch top {count} USDT-M PERPETUAL symbols by volume "
                f"(min 24h quote_volume: {min_quote_volume} USDT)...")
    
    # 1. Get a set of symbols that are USDT-M Perpetual and currently trading.
    # This is a much more robust filter than just checking if symbol.endswith("USDT").
    try:
        exchange_info = client._get_exchange_info()
        if not exchange_info:
            logger.error("Could not get exchange info to filter symbols.")
            return []
        
        # Create a set of eligible symbols for fast lookups later.
        eligible_symbols_set = {
            s['symbol'] for s in exchange_info['symbols'] 
            if s.get('status') == 'TRADING' 
            and s.get('contractType') == 'PERPETUAL'
            and s.get('quoteAsset') == 'USDT'
        }
        logger.debug(f"Found {len(eligible_symbols_set)} active, USDT-margined, perpetual symbols.")

    except Exception as e:
        logger.error(f"Error while getting/processing exchange_info for symbol filtering: {e}", exc_info=True)
        return []

    # 2. Get 24hr ticker data for all symbols
    all_tickers_data = client.get_all_tickers_24hr()
    if not all_tickers_data:
        logger.warning("Could not retrieve 24hr ticker data from client to rank symbols.")
        return []

    # 3. Filter tickers by our eligible set and by volume
    volume_filtered_symbols = []
    for ticker in all_tickers_data:
        symbol = ticker.get('symbol')
        
        # --- NEW, MORE ROBUST FILTER ---
        # Check if the symbol from the ticker data is in our set of eligible symbols.
        if symbol not in eligible_symbols_set:
            continue
        # -------------------------------

        try:
            quote_volume = float(ticker.get('quoteVolume', 0))
            if quote_volume >= min_quote_volume:
                volume_filtered_symbols.append({'symbol': symbol, 'quoteVolume': quote_volume})
        except (ValueError, TypeError):
            logger.warning(f"Could not parse quoteVolume for symbol {symbol}. Ticker data: {ticker}")
            continue
            
    if not volume_filtered_symbols:
        logger.warning(f"No symbols met the minimum quote volume criteria of {min_quote_volume} USDT after all filters.")
        return []

    # 4. Sort and return the top symbols
    ranked_symbols = sorted(volume_filtered_symbols, key=lambda x: x['quoteVolume'], reverse=True)
    top_symbols_list = [item['symbol'] for item in ranked_symbols[:count]]
    
    logger.info(f"Top {len(top_symbols_list)} symbols by volume (after all filters): {top_symbols_list}")

    return top_symbols_list

if __name__ == '__main__':
    # Standalone test for market_scanner.py
    # This requires BinanceFuturesClient and its dependencies to be accessible.
    import sys
    import os

    # Adjust sys.path to allow imports from the project's root when run directly
    current_script_path = os.path.abspath(__file__)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_script_path)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
        print(f"DEBUG: Added to sys.path for direct execution: {project_root}")

    try:
        from trading_bot.utils.logger_config import setup_logger
        from trading_bot.exchange.binance_client import BinanceFuturesClient
        from trading_bot.config import settings # To use configured API keys for real test

        standalone_logger = setup_logger(name="market_scanner_test")

        standalone_logger.info(f"Initializing Binance client for market scanner test (mode: {settings.TRADING_MODE})...")
        # For this test to work, BinanceFuturesClient must be fully functional
        binance_client = BinanceFuturesClient() 

        standalone_logger.info("--- Testing get_top_volume_usdt_futures_symbols ---")
        
        # Testnet volumes can be very low. Adjust min_quote_volume accordingly for testing.
        # For LIVE mode, you'd use a much higher value.
        min_volume_for_this_test = 10000  # Example for Testnet, might need adjustment
        if settings.TRADING_MODE == "LIVE":
            min_volume_for_this_test = 50000000 # Example for Live: 50 Million USDT volume
        else: # Testnet
            standalone_logger.warning(
                f"Using a low min_quote_volume ({min_volume_for_this_test}) for {settings.TRADING_MODE} testing. "
                "This might return many symbols or symbols with little actual Testnet activity."
            )

        top_symbols = get_top_volume_usdt_futures_symbols(
            client=binance_client, 
            count=10, # Get top 10
            min_quote_volume=min_volume_for_this_test
        )

        if top_symbols:
            standalone_logger.info(f"Retrieved top symbols for {settings.TRADING_MODE}: {top_symbols}")
            # Further testing could involve fetching klines for these symbols, etc.
        else:
            standalone_logger.warning(f"No top symbols were retrieved by the market scanner test for {settings.TRADING_MODE}. "
                                      "Consider adjusting min_quote_volume if on Testnet.")

    except ImportError as e:
        print(f"Could not run standalone market_scanner test due to ImportError: {e}. "
              "Ensure PYTHONPATH is set correctly or run from project root "
              "(e.g., using 'python -m trading_bot.core.market_scanner').")
    except Exception as e:
        if 'standalone_logger' in locals() and standalone_logger:
            standalone_logger.critical("An error occurred during standalone market_scanner test:", exc_info=True)
        else:
            print(f"An error occurred during standalone market_scanner test: {type(e).__name__} - {e}")
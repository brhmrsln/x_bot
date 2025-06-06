# trading_bot/core/strategy.py
import logging
import pandas as pd # For EMA calculation and data handling
# from trading_bot.exchange.binance_client import BinanceFuturesClient # For type hinting if used

# Get the logger configured in the main application (or by setup_logger in __main__)
logger = logging.getLogger("trading_bot")

class Strategy:
    def __init__(self, client, strategy_params=None):
        """
        Initializes the Strategy class with EMA crossover parameters.

        :param client: BinanceFuturesClient instance.
        :param strategy_params: Dictionary of parameters for the strategy, e.g.,
                                {
                                    "symbol": "BTCUSDT", 
                                    "kline_interval": "5m",
                                    "kline_limit": 100,      # Number of klines to fetch initially
                                    "short_ema_period": 12,
                                    "long_ema_period": 26
                                }
        """
        self.client = client 
        self.params = strategy_params if strategy_params is not None else {}
        
        # Determine the default symbol for this strategy instance
        default_symbol_fallback = "BTCUSDT"
        try:
            # Attempt to get default symbol from main application settings if available
            from trading_bot.config import settings as app_settings 
            default_symbol_from_settings = app_settings.DEFAULT_SYMBOL
        except ImportError:
            default_symbol_from_settings = default_symbol_fallback 
            logger.debug("Strategy init: Could not import app_settings for default_symbol, using BTCUSDT as fallback.")

        # self.symbol will be the primary symbol this strategy instance focuses on if no other is specified in generate_signal
        self.symbol = self.params.get("symbol", default_symbol_from_settings)
        
        # EMA strategy specific parameters
        self.kline_interval = self.params.get("kline_interval", "5m") 
        self.short_ema_period = int(self.params.get("short_ema_period", 12)) # Ensure integer
        self.long_ema_period = int(self.params.get("long_ema_period", 26))  # Ensure integer
        
        # kline_limit determines how many klines are fetched for EMA calculation.
        # It should be more than long_ema_period for EMAs to stabilize, plus some buffer.
        default_kline_limit = max(self.long_ema_period * 2, 50) # Heuristic for a decent default
        self.kline_limit = int(self.params.get("kline_limit", default_kline_limit)) 

        # Validate EMA periods
        if self.long_ema_period <= self.short_ema_period:
            msg = "Long EMA period must be greater than Short EMA period. Adjust strategy_params."
            logger.error(msg)
            raise ValueError(msg)
        
        # Warn if kline_limit seems too small for reliable EMA calculation and crossover detection
        # We need at least long_ema_period + 1 (for previous point) + some buffer for EMA to settle
        if self.kline_limit <= self.long_ema_period + 1: 
             logger.warning(f"Kline limit ({self.kline_limit}) might be too small for long EMA ({self.long_ema_period}). "
                            f"Consider increasing kline_limit to at least {self.long_ema_period + 5} for stable EMAs and crossover detection.")

        logger.info(f"EMA Crossover Strategy initialized for default symbol '{self.symbol}' with params: "
                    f"Interval='{self.kline_interval}', BaseKlineLimit={self.kline_limit}, "
                    f"ShortEMA={self.short_ema_period}, LongEMA={self.long_ema_period}")

    def generate_signal(self, symbol_to_process=None):
        """
        Generates a trading signal ("BUY", "SELL", or "HOLD") for the given symbol
        based on an EMA (Exponential Moving Average) crossover strategy.

        :param symbol_to_process: The trading symbol (e.g., "BTCUSDT") for which to generate a signal.
                                  If None, the strategy's default symbol (self.symbol) is used.
        :return: A signal string: "BUY", "SELL", or "HOLD".
        """
        current_symbol = symbol_to_process if symbol_to_process is not None else self.symbol
        
        if not current_symbol:
            logger.error("No symbol provided or set for signal generation. Returning HOLD.")
            return "HOLD"
            
        logger.debug(f"Generating EMA crossover signal for {current_symbol} using {self.kline_interval} klines...")

        # 1. Fetch historical klines
        # Ensure kline_limit is sufficient for EMA calculation + crossover detection.
        # The kline_limit is taken from instance parameters.
        klines_data = self.client.get_historical_klines(
            symbol=current_symbol, 
            interval=self.kline_interval, 
            limit=self.kline_limit 
        )

        # We need at least long_ema_period + 1 data points for EMAs and crossover check.
        if not klines_data or len(klines_data) < self.long_ema_period + 1:
            logger.warning(f"Could not fetch enough kline data for {current_symbol} to generate EMA signal. "
                           f"Fetched: {len(klines_data) if klines_data else 0}, "
                           f"Required minimum for analysis: {self.long_ema_period + 1}. Returning HOLD.")
            return "HOLD"

        # 2. Convert klines to pandas DataFrame
        df_columns = [
            'open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 
            'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 
            'taker_buy_quote_asset_volume', 'ignore'
        ]
        df = pd.DataFrame(klines_data, columns=df_columns)
        
        # Convert essential price and volume columns to numeric types
        numeric_cols = ['open', 'high', 'low', 'close', 'volume'] 
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce') # 'coerce' turns conversion errors into NaNs
        
        df.dropna(subset=['close'], inplace=True) # Drop rows if 'close' price couldn't be converted (is NaN)

        if len(df) < self.long_ema_period + 1: # Check length again after potential NaN drops
            logger.warning(f"Not enough valid (numeric close) kline data after cleaning for {current_symbol}. "
                           f"Rows: {len(df)}, Required minimum: {self.long_ema_period + 1}. Returning HOLD.")
            return "HOLD"
        
        # 3. Calculate EMAs
        try:
            # adjust=False is common in trading to give more weight to recent data.
            # min_periods ensures EMA calculation starts only after enough data points.
            df['short_ema'] = df['close'].ewm(span=self.short_ema_period, adjust=False, min_periods=self.short_ema_period).mean()
            df['long_ema'] = df['close'].ewm(span=self.long_ema_period, adjust=False, min_periods=self.long_ema_period).mean()
        except Exception as e:
            logger.error(f"Error calculating EMAs for {current_symbol}: {e}", exc_info=True)
            return "HOLD"
        
        # Check if EMAs have enough non-NaN values at the end for crossover detection.
        # We need the last two points (-1 and -2) of both EMAs to be valid numbers.
        if df['short_ema'].iloc[-2:].isnull().any() or df['long_ema'].iloc[-2:].isnull().any():
            logger.warning(f"Not enough non-NaN EMA values to detect crossover for {current_symbol} (likely due to short data series or many NaNs). "
                           f"ShortEMA tail: {df['short_ema'].iloc[-2:].values}, LongEMA tail: {df['long_ema'].iloc[-2:].values}. Returning HOLD.")
            return "HOLD"

        # 4. Implement EMA Crossover Logic
        # Get the last two values (latest and previous) of each EMA series.
        last_short_ema = df['short_ema'].iloc[-1]
        prev_short_ema = df['short_ema'].iloc[-2]
        last_long_ema = df['long_ema'].iloc[-1]
        prev_long_ema = df['long_ema'].iloc[-2]

        logger.debug(f"EMA values for {current_symbol} [{self.kline_interval}]: "
                     f"PrevShort={prev_short_ema:.4f}, LastShort={last_short_ema:.4f} | "
                     f"PrevLong={prev_long_ema:.4f}, LastLong={last_long_ema:.4f}")

        signal = "HOLD" # Default signal

        # Bullish Crossover: Short EMA was below or equal to Long EMA, and now Short EMA is above Long EMA
        if prev_short_ema <= prev_long_ema and last_short_ema > last_long_ema:
            signal = "BUY"
            logger.info(f"EMA Crossover Signal for {current_symbol}: BUY (ShortEMA {last_short_ema:.2f} crossed above LongEMA {last_long_ema:.2f})")
        
        # Bearish Crossover: Short EMA was above or equal to Long EMA, and now Short EMA is below Long EMA
        elif prev_short_ema >= prev_long_ema and last_short_ema < last_long_ema:
            signal = "SELL"
            logger.info(f"EMA Crossover Signal for {current_symbol}: SELL (ShortEMA {last_short_ema:.2f} crossed below LongEMA {last_long_ema:.2f})")
        else:
            logger.debug(f"No EMA crossover detected for {current_symbol}. Signal: HOLD.")
            
        return signal

if __name__ == '__main__':
    import sys
    import os
    import random
    import time

    # Adjust sys.path to allow imports from the project's root
    current_script_path = os.path.abspath(__file__)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_script_path)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
        print(f"DEBUG: Added to sys.path for direct execution: {project_root}")

    try:
        from trading_bot.utils.logger_config import setup_logger
        
        default_test_symbol_for_run = "BTCUSDT" 
        try:
            from trading_bot.config import settings as app_settings
            default_test_symbol_for_run = app_settings.DEFAULT_SYMBOL
            print(f"DEBUG: Loaded default symbol '{default_test_symbol_for_run}' from app_settings.")
        except ImportError:
            print(f"DEBUG: Could not import app_settings for default_test_symbol, using '{default_test_symbol_for_run}' as fallback for test.")

        # --- DEĞİŞİKLİK BURADA ---
        # Configure the logger used by the Strategy class ("trading_bot")
        # and also use it for __main__ block's specific logging.
        configured_logger = setup_logger(name="trading_bot") 
        # configured_logger şimdi Strategy sınıfının kullandığı logger ile aynı.
        # 'standalone_logger' yerine 'configured_logger' veya doğrudan 'logger' (global olan) kullanılabilir.
        # Ancak karışıklığı önlemek için __main__ bloğuna özel bir isimle aldık.
        # Önemli olan "trading_bot" adıyla setup_logger'ın çağrılmış olması.

        class MockBinanceClient:
            def get_historical_klines(self, symbol, interval, limit):
                # Bu logger artık "trading_bot" logger'ı olacak ve DEBUG mesajları gösterecek
                logger.info(f"MockClient: get_historical_klines called for {symbol}, interval {interval}, limit {limit}")
                mock_klines = []
                base_price = 100000 
                prices = []
                for i in range(limit):
                    price_offset = 0
                    if i < limit * 0.4: 
                        price_offset = - (limit * 0.4 - i) * 10 
                    elif i < limit * 0.6: 
                        price_offset = (i - limit * 0.4) * 25 
                    else: 
                        price_offset = (limit * 0.2 * 25) + (i - limit * 0.6) * 5
                    close_price = base_price + price_offset + random.uniform(-50, 50)
                    prices.append(close_price)

                for i in range(limit):
                    close_price = prices[i]
                    interval_value = 1 
                    if interval[:-1].isdigit():
                        interval_value = int(interval[:-1])
                    open_p = close_price - random.uniform(0,10)
                    high_p = max(close_price, open_p) + random.uniform(0,10)
                    low_p = min(close_price, open_p) - random.uniform(0,10)
                    mock_klines.append([
                        (1678886400000 + i*60000*interval_value), 
                        str(open_p), str(high_p), str(low_p), str(close_price),                           
                        str(random.uniform(10,100)),                
                        (1678886400000 + (i+1)*60000*interval_value -1), 
                        "0", "0", "0", "0", "0" 
                    ])
                return mock_klines

        mock_client_ema = MockBinanceClient()
        strategy_params_ema = {
            "symbol": default_test_symbol_for_run, 
            "kline_interval": "5m",        
            "kline_limit": 60,             
            "short_ema_period": 12,        
            "long_ema_period": 26          
        }
        ema_strategy = Strategy(client=mock_client_ema, strategy_params=strategy_params_ema)
        
        signal = ema_strategy.generate_signal() # Strategy'nin default sembolünü kullanır
        
        # __main__ bloğuna özel logları configured_logger ile basalım
        configured_logger.info(f"EMA Strategy Test Signal for {ema_strategy.symbol}: {signal}")

    except ImportError as e:
        print(f"Could not run standalone strategy test due to ImportError: {e}. "
              "Ensure relevant modules are in PYTHONPATH or run from project root (e.g., using 'python -m trading_bot.core.strategy').")
    except Exception as e:
        if 'configured_logger' in locals() and configured_logger: # Değişken adını güncelledik
            configured_logger.critical("An error occurred during standalone strategy test:", exc_info=True)
        else:
            print(f"An error occurred during standalone strategy test: {type(e).__name__} - {e}")

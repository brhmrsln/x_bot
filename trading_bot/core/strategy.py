# trading_bot/core/strategy.py
import logging
import pandas as pd # For EMA calculation and data handling
# from trading_bot.exchange.binance_client import BinanceFuturesClient # For type hinting, if used

# Attempt to import settings and logger setup function from the project structure
try:
    from trading_bot.config import settings
    from trading_bot.utils.logger_config import setup_logger
except ImportError:
    # Fallback for direct execution
    import sys
    import os
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root_dir = os.path.abspath(os.path.join(current_script_dir, '..', '..'))
    if project_root_dir not in sys.path:
        sys.path.insert(0, project_root_dir)
    from trading_bot.config import settings
    from trading_bot.utils.logger_config import setup_logger

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
                                    "kline_limit": 100,
                                    "short_ema_period": 12,
                                    "long_ema_period": 26
                                }
        """
        self.client = client 
        self.params = strategy_params if strategy_params is not None else {}
        
        # Strategy specific parameters from strategy_params or defaults
        try:
            # Attempt to get default symbol from main application settings if available
            # This makes the strategy more integrated if run as part of the main bot
            from trading_bot.config import settings as app_settings
            default_symbol_from_settings = app_settings.DEFAULT_SYMBOL
        except ImportError:
            default_symbol_from_settings = "BTCUSDT" # Fallback for isolated testing
            logger.debug("Strategy init: Could not import app_settings for default_symbol, using BTCUSDT fallback.")

        self.symbol = self.params.get("symbol", default_symbol_from_settings)
        self.kline_interval = self.params.get("kline_interval", "5m") 
        self.kline_limit = self.params.get("kline_limit", 100) 
        self.short_ema_period = int(self.params.get("short_ema_period", 12)) # Ensure integer
        self.long_ema_period = int(self.params.get("long_ema_period", 26))  # Ensure integer

        if self.long_ema_period <= self.short_ema_period:
            logger.error("Long EMA period must be greater than Short EMA period. Adjust strategy_params.")
            raise ValueError("Long EMA period must be greater than Short EMA period.")
        if self.kline_limit <= self.long_ema_period: # Need enough data for the longest EMA + previous point for crossover
             logger.warning(f"Kline limit ({self.kline_limit}) might be too small for long EMA ({self.long_ema_period}). "
                            f"Consider increasing kline_limit to at least {self.long_ema_period + 5} for stable EMAs.")

        logger.info(f"EMA Crossover Strategy initialized for symbol '{self.symbol}' with params: "
                    f"Interval='{self.kline_interval}', KlineLimit={self.kline_limit}, "
                    f"ShortEMA={self.short_ema_period}, LongEMA={self.long_ema_period}")

    def _calculate_emas(self, df_klines):
        """Calculates short and long EMAs on the close prices."""
        if 'close' not in df_klines.columns:
            logger.error("DataFrame for EMA calculation does not contain 'close' column.")
            return None, None
        # Ensure there's enough data (at least long_ema_period + 1 to have a previous point for crossover logic)
        if len(df_klines) < self.long_ema_period + 1: 
            logger.warning(f"Not enough kline data (rows: {len(df_klines)}) to reliably calculate EMAs requiring period {self.long_ema_period} and a preceding point.")
            return None, None
            
        try:
            # Calculate EMAs using pandas. adjust=False is common in trading.
            short_ema = df_klines['close'].ewm(span=self.short_ema_period, adjust=False).mean()
            long_ema = df_klines['close'].ewm(span=self.long_ema_period, adjust=False).mean()
            return short_ema, long_ema
        except Exception as e:
            logger.error(f"Error calculating EMAs: {e}", exc_info=True)
            return None, None

    def generate_signal(self, symbol=None):
        """
        Generates a trading signal for the given symbol based on EMA crossover.

        :param symbol: The trading symbol (e.g., "BTCUSDT"). If None, self.symbol from init is used.
        :return: A signal string: "BUY", "SELL", or "HOLD".
        """
        current_symbol = symbol if symbol else self.symbol
        logger.debug(f"Generating EMA crossover signal for {current_symbol} using {self.kline_interval} klines...")

        # 1. Fetch historical klines
        # Ensure kline_limit is sufficient for EMA calculation + crossover detection (needs at least long_ema_period + 2 points ideally)
        # Let's fetch a bit more to be safe, e.g., long_ema_period + short_ema_period or a fixed larger number like 100 if periods are small
        # self.kline_limit should already be set appropriately in __init__
        klines_to_fetch = max(self.kline_limit, self.long_ema_period + self.short_ema_period, 50) # Ensure a decent minimum
        
        klines_data = self.client.get_historical_klines(
            symbol=current_symbol, 
            interval=self.kline_interval, 
            limit=klines_to_fetch
        )

        # We need at least long_ema_period + 1 data points to calculate EMAs and check crossover from previous point
        if not klines_data or len(klines_data) < self.long_ema_period + 1:
            logger.warning(f"Could not fetch enough kline data for {current_symbol} to generate EMA signal. "
                           f"Fetched: {len(klines_data) if klines_data else 0}, Required for analysis: {self.long_ema_period + 1}. Returning HOLD.")
            return "HOLD"

        # 2. Convert klines to pandas DataFrame
        df_columns = [
            'open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 
            'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 
            'taker_buy_quote_asset_volume', 'ignore'
        ]
        df = pd.DataFrame(klines_data, columns=df_columns)
        
        # Convert price and volume columns to numeric types
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'quote_asset_volume', 
                        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce') # 'coerce' turns errors into NaNs
        
        df.dropna(subset=['close'], inplace=True) # Drop rows where close price couldn't be converted

        if len(df) < self.long_ema_period + 1: # Check again after potential drops
            logger.warning(f"Not enough valid kline data after cleaning for {current_symbol}. "
                           f"Rows: {len(df)}, Required: {self.long_ema_period + 1}. Returning HOLD.")
            return "HOLD"
        
        # 3. Calculate EMAs
        df['short_ema'] = df['close'].ewm(span=self.short_ema_period, adjust=False).mean()
        df['long_ema'] = df['close'].ewm(span=self.long_ema_period, adjust=False).mean()
        
        # Check if EMAs could be calculated (they will have NaNs at the beginning)
        if df['long_ema'].isnull().all() or df['short_ema'].isnull().all():
            logger.warning(f"EMAs resulted in all NaNs for {current_symbol}. Insufficient data length or other issue. Returning HOLD.")
            return "HOLD"

        # We need at least two valid (non-NaN) points from the end of EMA series to detect a crossover.
        # The longest EMA will have more NaNs at the beginning.
        # Let's ensure the last two points of the long_ema are not NaN.
        if df['long_ema'].iloc[-2:].isnull().any():
            logger.warning(f"Not enough non-NaN EMA values to detect crossover for {current_symbol} "
                           f"(Last two long_ema: {df['long_ema'].iloc[-2:].values}). Returning HOLD.")
            return "HOLD"

        # 4. Implement EMA Crossover Logic
        # Get the last two values of each EMA series (latest and previous).
        last_short_ema = df['short_ema'].iloc[-1]
        prev_short_ema = df['short_ema'].iloc[-2]
        last_long_ema = df['long_ema'].iloc[-1]
        prev_long_ema = df['long_ema'].iloc[-2]

        logger.debug(f"EMA values for {current_symbol} [{self.kline_interval}]: "
                     f"PrevShort={prev_short_ema:.4f}, LastShort={last_short_ema:.4f} | "
                     f"PrevLong={prev_long_ema:.4f}, LastLong={last_long_ema:.4f}")

        signal = "HOLD" # Default signal

        # Bullish Crossover: Short EMA crosses above Long EMA
        if prev_short_ema <= prev_long_ema and last_short_ema > last_long_ema:
            signal = "BUY"
            logger.info(f"EMA Crossover Signal for {current_symbol}: BUY (ShortEMA crossed above LongEMA)")
        
        # Bearish Crossover: Short EMA crosses below Long EMA
        elif prev_short_ema >= prev_long_ema and last_short_ema < last_long_ema:
            signal = "SELL"
            logger.info(f"EMA Crossover Signal for {current_symbol}: SELL (ShortEMA crossed below LongEMA)")
        else:
            logger.debug(f"No EMA crossover detected for {current_symbol}. Signal: HOLD.")
            
        return signal

if __name__ == '__main__':
     try:
         from trading_bot.utils.logger_config import setup_logger
         from trading_bot.config import settings
         import random
         standalone_logger = setup_logger(name="strategy_test_ema")
       
         class MockBinanceClient:
             def get_historical_klines(self, symbol, interval, limit):
                 standalone_logger.info(f"MockClient: get_historical_klines called for {symbol}, interval {interval}, limit {limit}")
                 mock_klines = []
                 # Simulate prices that might cause a crossover
                 # Start with short_ema below long_ema, then make it cross above
                 base_price = 100000
                 prices = []
                 for i in range(limit):
                     if i < limit // 2:
                         prices.append(base_price - (limit//2 - i) * 10) # Price increasing towards crossover
                     else:
                         prices.append(base_price + (i - limit//2) * 20) # Price increases faster after mid-point
                 for i in range(limit):
                     close_price = prices[i] + random.uniform(-5, 5) # Add some noise
                     mock_klines.append([
                         (1678886400000 + i*60000*int(interval[:-1])), # open_time (adjust by interval)
                         str(close_price - random.uniform(0,1)),    # open
                         str(close_price + random.uniform(0,1)),    # high
                         str(close_price - random.uniform(0,2)),    # low
                         str(close_price),                           # close
                         str(random.uniform(10,100)),                # volume
                         (1678886400000 + (i+1)*60000*int(interval[:-1]) -1), # close_time
                         "0", "0", "0", "0", "0" 
                     ])
                 return mock_klines
         mock_client_ema = MockBinanceClient()
         strategy_params_ema = {
             "symbol": settings.DEFAULT_SYMBOL if hasattr(settings, 'DEFAULT_SYMBOL') else "BTCUSDT",
             "kline_interval": "5m", 
             "kline_limit": 60, # Must be > long_ema_period + a few for stability
             "short_ema_period": 12, 
             "long_ema_period": 26  
         }
         ema_strategy = Strategy(client=mock_client_ema, strategy_params=strategy_params_ema)
       
         signal = ema_strategy.generate_signal() 
         standalone_logger.info(f"EMA Strategy Test Signal for {ema_strategy.symbol}: {signal}")
     except ImportError as e:
         print(f"ImportError in strategy.py __main__: {e}")
     except Exception as e:
         if 'standalone_logger' in locals() and standalone_logger:
             standalone_logger.critical("Error in strategy.py __main__ test:", exc_info=True)
         else:
             print(f"Error in strategy.py __main__ test: {type(e).__name__} - {e}")
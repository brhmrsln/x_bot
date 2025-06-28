# trading_bot/core/simple_ema_crossover_strategy.py (Volatility Filter Added)

import pandas as pd
import pandas_ta as ta
from trading_bot.core.base_strategy import BaseStrategy

class SimpleEmaCrossoverStrategy(BaseStrategy):
    """
    A simple trend-following strategy based on two EMA crossovers,
    with an added volatility filter to avoid trading in non-ideal market conditions.
    """

    @staticmethod
    def get_required_parameters():
        """This strategy's required parameters and their corresponding setting names."""
        return {
            "fast_ema_period": "CROSSOVER_FAST_EMA_PERIOD",
            "slow_ema_period": "CROSSOVER_SLOW_EMA_PERIOD",
            "atr_period": "CROSSOVER_ATR_PERIOD",
            "atr_sl_multiplier": "CROSSOVER_ATR_SL_MULTIPLIER",
            "atr_tp_multiplier": "CROSSOVER_ATR_TP_MULTIPLIER",
            # --- NEW PARAMETERS FOR VOLATILITY FILTER ---
            "min_volatility_threshold": "CROSSOVER_MIN_VOLATILITY_THRESHOLD",
            "max_volatility_threshold": "CROSSOVER_MAX_VOLATILITY_THRESHOLD",
        }

    def generate_signal(self, data: pd.DataFrame):
        """Generates a BUY or SELL signal based on the data, if volatility is within range."""
        try:
            params = self.params
            
            # Calculate Indicators
            data.ta.ema(length=params['fast_ema_period'], append=True, col_names=(f'EMA_fast',))
            data.ta.ema(length=params['slow_ema_period'], append=True, col_names=(f'EMA_slow',))
            data.ta.atr(length=params['atr_period'], append=True, col_names=(f'ATR',))

            # Look at the last two candles for signals
            last_candle = data.iloc[-2]
            previous_candle = data.iloc[-3]
            current_price = data.iloc[-1]['close']

            # --- NEW: Volatility Filter Logic ---
            # Normalize ATR as a percentage of the closing price
            normalized_atr = (last_candle['ATR'] / last_candle['close']) * 100
            
            # Check if volatility is within the desired range
            is_volatility_tradable = params['min_volatility_threshold'] <= normalized_atr <= params['max_volatility_threshold']
            # ------------------------------------

            # BUY Signal: Fast EMA crosses above Slow EMA AND volatility is tradable
            is_buy_signal = previous_candle['EMA_fast'] < previous_candle['EMA_slow'] and last_candle['EMA_fast'] > last_candle['EMA_slow']
            if is_buy_signal and is_volatility_tradable: # <-- VOLATILITY FILTER ADDED
                sl_price = current_price - (last_candle['ATR'] * params['atr_sl_multiplier'])
                tp_price = current_price + (last_candle['ATR'] * params['atr_tp_multiplier'])
                return "BUY", sl_price, tp_price

            # SELL Signal: Fast EMA crosses below Slow EMA AND volatility is tradable
            is_sell_signal = previous_candle['EMA_fast'] > previous_candle['EMA_slow'] and last_candle['EMA_fast'] < last_candle['EMA_slow']
            if is_sell_signal and is_volatility_tradable: # <-- VOLATILITY FILTER ADDED
                sl_price = current_price + (last_candle['ATR'] * params['atr_sl_multiplier'])
                tp_price = current_price - (last_candle['ATR'] * params['atr_tp_multiplier'])
                return "SELL", sl_price, tp_price

            return None, None, None
        except Exception:
            return None, None, None
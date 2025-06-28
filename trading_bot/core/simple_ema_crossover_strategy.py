# trading_bot/core/simple_ema_crossover_strategy.py

import pandas as pd
import pandas_ta as ta
from trading_bot.core.base_strategy import BaseStrategy

class SimpleEmaCrossoverStrategy(BaseStrategy):
    """
    Sadece iki EMA'nın kesişimine dayanan basit bir trend takip stratejisi.
    Hızlı EMA, yavaş EMA'yı yukarı kesince AL, aşağı kesince SAT.
    """

    @staticmethod
    def get_required_parameters():
        """Bu strateji için gerekli parametreleri döndürür."""
        return {
            "fast_ema_period": "CROSSOVER_FAST_EMA_PERIOD",
            "slow_ema_period": "CROSSOVER_SLOW_EMA_PERIOD",
            "atr_period": "CROSSOVER_ATR_PERIOD",
            "atr_sl_multiplier": "CROSSOVER_ATR_SL_MULTIPLIER",
            "atr_tp_multiplier": "CROSSOVER_ATR_TP_MULTIPLIER",
        }

    def generate_signal(self, data: pd.DataFrame):
        """Verilen veri ile AL/SAT sinyali üretir."""
        try:
            params = self.params
            
            # Göstergeleri hesapla
            data.ta.ema(length=params['fast_ema_period'], append=True, col_names=(f'EMA_fast',))
            data.ta.ema(length=params['slow_ema_period'], append=True, col_names=(f'EMA_slow',))
            data.ta.atr(length=params['atr_period'], append=True, col_names=(f'ATR',))

            # Sinyal için son iki muma bak
            last_candle = data.iloc[-2]
            previous_candle = data.iloc[-3]
            current_price = data.iloc[-1]['close']

            # ALIM Sinyali: Hızlı EMA, yavaş EMA'yı yukarı keserse
            if previous_candle['EMA_fast'] < previous_candle['EMA_slow'] and last_candle['EMA_fast'] > last_candle['EMA_slow']:
                sl_price = current_price - (last_candle['ATR'] * params['atr_sl_multiplier'])
                tp_price = current_price + (last_candle['ATR'] * params['atr_tp_multiplier'])
                return "BUY", sl_price, tp_price

            # SATIM Sinyali: Hızlı EMA, yavaş EMA'yı aşağı keserse
            if previous_candle['EMA_fast'] > previous_candle['EMA_slow'] and last_candle['EMA_fast'] < last_candle['EMA_slow']:
                sl_price = current_price + (last_candle['ATR'] * params['atr_sl_multiplier'])
                tp_price = current_price - (last_candle['ATR'] * params['atr_tp_multiplier'])
                return "SELL", sl_price, tp_price

            return None, None, None
        except Exception:
            return None, None, None
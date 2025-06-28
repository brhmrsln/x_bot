# trading_bot/core/momentum_scalping_strategy.py

import pandas as pd
import pandas_ta as ta
from trading_bot.core.base_strategy import BaseStrategy

class MomentumScalpingStrategy(BaseStrategy):
    """
    1 dakikalık zaman diliminde anlık trendi yakalayıp, 
    RSI ile teyit edilen küçük geri çekilmelerde pozisyona giren 
    ve hacimle onaylayan bir scalping stratejisi.
    """
    
    @staticmethod
    def get_required_parameters():
        """Bu strateji için gerekli parametreleri döndürür."""
        return {
            "fast_ema_period": "SCALPING_FAST_EMA_PERIOD",
            "slow_ema_period": "SCALPING_SLOW_EMA_PERIOD",
            "rsi_period": "SCALPING_RSI_PERIOD",
            "rsi_pullback_level_long": "SCALPING_RSI_PULLBACK_LEVEL_LONG",
            "rsi_pullback_level_short": "SCALPING_RSI_PULLBACK_LEVEL_SHORT",
            "volume_ma_period": "SCALPING_VOLUME_MA_PERIOD",
            "atr_period": "SCALPING_ATR_PERIOD",
            "atr_multiplier_sl": "SCALPING_ATR_MULTIPLIER_SL",
            "atr_multiplier_tp": "SCALPING_ATR_MULTIPLIER_TP"
        }

    def generate_signal(self, data: pd.DataFrame):
        # ... Bu metodun içeriği aynı kalıyor, sadece params -> self.params oldu ...
        try:
            params = self.params
            # ... (önceki cevaptaki generate_signal içeriğinin tamamı buraya gelecek)
            fast_ema_period = params['fast_ema_period']
            slow_ema_period = params['slow_ema_period']
            rsi_period = params['rsi_period']
            # ... (diğer tüm kodlar) ...
            data.ta.ema(length=fast_ema_period, append=True, col_names=(f'EMA_{fast_ema_period}',))
            data.ta.ema(length=slow_ema_period, append=True, col_names=(f'EMA_{slow_ema_period}',))
            data.ta.rsi(length=rsi_period, append=True, col_names=(f'RSI_{rsi_period}',))
            data.ta.sma(close=data['volume'], length=params['volume_ma_period'], append=True, col_names=(f'VOLUME_SMA_{params["volume_ma_period"]}',))
            data.ta.atr(length=params['atr_period'], append=True, col_names=(f'ATR_{params["atr_period"]}',))
            
            if data.isnull().values.any():
                return None, None, None

            last_candle = data.iloc[-2]
            current_price = data.iloc[-1]['close']
            
            is_uptrend = last_candle[f'EMA_{fast_ema_period}'] > last_candle[f'EMA_{slow_ema_period}']
            is_downtrend = last_candle[f'EMA_{fast_ema_period}'] < last_candle[f'EMA_{slow_ema_period}']
            volume_confirmed = last_candle['volume'] > last_candle[f'VOLUME_SMA_{params["volume_ma_period"]}']

            if is_uptrend and volume_confirmed:
                rsi_value = last_candle[f'RSI_{rsi_period}']
                if params['rsi_pullback_level_long'] <= rsi_value < params['rsi_pullback_level_long'] + 5:
                    atr_value = last_candle[f'ATR_{params["atr_period"]}']
                    sl_price = current_price - (atr_value * params['atr_multiplier_sl'])
                    tp_price = current_price + (atr_value * params['atr_multiplier_tp'])
                    return "BUY", sl_price, tp_price

            if is_downtrend and volume_confirmed:
                rsi_value = last_candle[f'RSI_{rsi_period}']
                if params['rsi_pullback_level_short'] - 5 < rsi_value <= params['rsi_pullback_level_short']:
                    atr_value = last_candle[f'ATR_{params["atr_period"]}']
                    sl_price = current_price + (atr_value * params['atr_multiplier_sl'])
                    tp_price = current_price - (atr_value * params['atr_multiplier_tp'])
                    return "SELL", sl_price, tp_price

            return None, None, None
        except Exception as e:
            return None, None, None
# trading_bot/core/mean_reversion_strategy.py

import pandas as pd
import pandas_ta as ta
from trading_bot.core.base_strategy import BaseStrategy

class MeanReversionStrategy(BaseStrategy):
    """
    Yüksek zaman dilimindeki trend yönünde, düşük zaman dilimindeki aşırı satım/alım 
    bölgelerinden ortalamaya dönüş bekleyerek işlem açan bir strateji.
    """

    @staticmethod
    def get_required_parameters():
        """Bu strateji için gerekli olan parametreleri settings.py'deki isimleriyle eşleştirir."""
        return {
            "htf_kline_interval": "MTA_KLINE_INTERVAL",
            "ltf_kline_interval": "STRATEGY_KLINE_INTERVAL",
            "kline_limit": "STRATEGY_KLINE_LIMIT",
            "htf_short_ema_period": "MTA_SHORT_EMA_PERIOD",
            "htf_long_ema_period": "MTA_LONG_EMA_PERIOD",
            "stoch_rsi_period": "STOCH_RSI_PERIOD",
            "stoch_rsi_k": "STOCH_RSI_K",
            "stoch_rsi_d": "STOCH_RSI_D",
            "stoch_rsi_oversold": "STOCH_RSI_OVERSOLD",
            "stoch_rsi_overbought": "STOCH_RSI_OVERBOUGHT",
            "bollinger_period": "STRATEGY_BOLLINGER_PERIOD",
            "bollinger_std_dev": "STRATEGY_BOLLINGER_STD_DEV",
            "atr_period": "ATR_PERIOD",
            "atr_sl_multiplier": "ATR_SL_MULTIPLIER",
            "atr_tp_multiplier": "ATR_TP_MULTIPLIER",
        }

    def generate_signal(self, htf_data: pd.DataFrame, ltf_data: pd.DataFrame):
        # ... Bu metodun içeriği aynı kalıyor, değişiklik yok ...
        try:
            # ... (önceki cevaptaki generate_signal içeriğinin tamamı buraya gelecek)
            htf_data.ta.ema(length=self.params['htf_short_ema_period'], append=True, col_names=('HTF_EMA_short',))
            htf_data.ta.ema(length=self.params['htf_long_ema_period'], append=True, col_names=('HTF_EMA_long',))
            # ... (diğer tüm kodlar) ...
            last_htf_candle = htf_data.iloc[-1]
            main_trend = None
            if last_htf_candle['HTF_EMA_short'] > last_htf_candle['HTF_EMA_long']:
                main_trend = "UP"
            elif last_htf_candle['HTF_EMA_short'] < last_htf_candle['HTF_EMA_long']:
                main_trend = "DOWN"

            if not main_trend:
                return None, None, None

            stoch_rsi = ltf_data.ta.stochrsi(length=self.params['stoch_rsi_period'], rsi_length=self.params['stoch_rsi_period'], k=self.params['stoch_rsi_k'], d=self.params['stoch_rsi_d'], append=True)
            ltf_data.ta.bbands(length=self.params['bollinger_period'], std=self.params['bollinger_std_dev'], append=True)
            ltf_data.ta.atr(length=self.params['atr_period'], append=True, col_names=('ATR',))
            
            last_ltf = ltf_data.iloc[-2]
            previous_ltf = ltf_data.iloc[-3]
            current_price = ltf_data.iloc[-1]['close']
            
            stoch_k_col = f"STOCHRSIk_{self.params['stoch_rsi_period']}_{self.params['stoch_rsi_period']}_{self.params['stoch_rsi_k']}_{self.params['stoch_rsi_d']}"
            stoch_d_col = f"STOCHRSId_{self.params['stoch_rsi_period']}_{self.params['stoch_rsi_period']}_{self.params['stoch_rsi_k']}_{self.params['stoch_rsi_d']}"
            bb_lower_col = f"BBL_{self.params['bollinger_period']}_{self.params['bollinger_std_dev']}"
            bb_middle_col = f"BBM_{self.params['bollinger_period']}_{self.params['bollinger_std_dev']}"
            bb_upper_col = f"BBU_{self.params['bollinger_period']}_{self.params['bollinger_std_dev']}"

            if main_trend == "UP":
                is_oversold = last_ltf[stoch_k_col] < self.params['stoch_rsi_oversold']
                is_bullish_cross = previous_ltf[stoch_k_col] < previous_ltf[stoch_d_col] and last_ltf[stoch_k_col] > last_ltf[stoch_d_col]
                in_lower_band = last_ltf['close'] < last_ltf[bb_middle_col]
                
                if is_oversold and is_bullish_cross and in_lower_band:
                    sl = current_price - (last_ltf['ATR'] * self.params['atr_sl_multiplier'])
                    tp = current_price + (last_ltf['ATR'] * self.params['atr_tp_multiplier'])
                    return "BUY", sl, tp

            if main_trend == "DOWN":
                is_overbought = last_ltf[stoch_k_col] > self.params['stoch_rsi_overbought']
                is_bearish_cross = previous_ltf[stoch_k_col] > previous_ltf[stoch_d_col] and last_ltf[stoch_k_col] < last_ltf[stoch_d_col]
                in_upper_band = last_ltf['close'] > last_ltf[bb_middle_col]

                if is_overbought and is_bearish_cross and in_upper_band:
                    sl = current_price + (last_ltf['ATR'] * self.params['atr_sl_multiplier'])
                    tp = current_price - (last_ltf['ATR'] * self.params['atr_tp_multiplier'])
                    return "SELL", sl, tp

            return None, None, None
        except Exception:
            return None, None, None
# trading_bot/core/strategy.py
import logging
import pandas as pd
import pandas_ta as ta

logger = logging.getLogger("trading_bot")

class Strategy:
    def __init__(self, client, strategy_params=None):
        """
        Initializes the High-Probability Mean Reversion Strategy.
        """
        self.client = client 
        self.params = strategy_params if strategy_params is not None else {}
        
        # Load all strategy parameters from the dictionary
        self.kline_interval = self.params.get("kline_interval", "5m")
        self.kline_limit = int(self.params.get("kline_limit", 200))
        # MTA Trend Filter
        self.mta_kline_interval = self.params.get("mta_kline_interval", "30m")
        self.mta_short_ema_period = int(self.params.get("mta_short_ema_period", 20))
        self.mta_long_ema_period = int(self.params.get("mta_long_ema_period", 50))
        # Stochastic RSI
        self.stoch_rsi_period = int(self.params.get("stoch_rsi_period", 14))
        self.stoch_rsi_k = int(self.params.get("stoch_rsi_k", 3))
        self.stoch_rsi_d = int(self.params.get("stoch_rsi_d", 3))
        self.stoch_rsi_oversold = int(self.params.get("stoch_rsi_oversold", 25))
        self.stoch_rsi_overbought = int(self.params.get("stoch_rsi_overbought", 75))
        # Bollinger Bands
        self.bollinger_period = int(self.params.get("bollinger_period", 20))
        self.bollinger_std_dev = int(self.params.get("bollinger_std_dev", 2))
        # ATR
        self.atr_period = int(self.params.get("atr_period", 14))
        self.atr_sl_multiplier = float(self.params.get("atr_sl_multiplier", 1.5))
        self.atr_tp_multiplier = float(self.params.get("atr_tp_multiplier", 2.5))

        logger.info("High-Probability Mean Reversion Strategy initialized.")

    def _get_and_prepare_data(self, symbol, interval, limit):
        """Helper function to fetch and prepare kline data as a pandas DataFrame."""
        logger.debug(f"Fetching {limit} klines for {symbol} with {interval} interval...")
        klines_data = self.client.get_historical_klines(symbol, interval, limit)
        
        if not klines_data or len(klines_data) < 50: # A safe minimum check
            logger.warning(f"Could not fetch sufficient kline data for {symbol} [{interval}].")
            return None

        df = pd.DataFrame(klines_data, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 
            'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(subset=numeric_cols, inplace=True)
        return df

    def generate_signal(self, symbol):
        """
        Generates a trading signal based on a high-probability mean reversion strategy.
        """
        logger.debug(f"--- Generating signal for {symbol} ---")

        # 1. Trend Filter (HTF - e.g., 30m) - Using Stacked EMAs
        df_htf = self._get_and_prepare_data(symbol, self.mta_kline_interval, self.kline_limit)
        if df_htf is None: return {"signal": "HOLD"}
            
        df_htf.ta.ema(length=self.mta_short_ema_period, append=True)
        df_htf.ta.ema(length=self.mta_long_ema_period, append=True)
        
        mta_ema_short_col = f'EMA_{self.mta_short_ema_period}'
        mta_ema_long_col = f'EMA_{self.mta_long_ema_period}'

        if pd.isna(df_htf[mta_ema_long_col].iloc[-1]):
            logger.warning(f"[{symbol} | {self.mta_kline_interval}] Not enough data for trend EMAs.")
            return {"signal": "HOLD"}
        
        last_price_htf = df_htf['close'].iloc[-1]
        last_mta_short_ema = df_htf[mta_ema_short_col].iloc[-1]
        last_mta_long_ema = df_htf[mta_ema_long_col].iloc[-1]
        
        main_trend = "SIDEWAYS"
        if last_price_htf > last_mta_short_ema > last_mta_long_ema: main_trend = "UP"
        elif last_price_htf < last_mta_short_ema < last_mta_long_ema: main_trend = "DOWN"
        
        logger.debug(f"[{symbol} | {self.mta_kline_interval}] Main Trend: {main_trend}")
        if main_trend == "SIDEWAYS": return {"signal": "HOLD"}

        # 2. Entry Trigger & Filters (LTF - e.g., 5m)
        df_ltf = self._get_and_prepare_data(symbol, self.kline_interval, self.kline_limit)
        if df_ltf is None: return {"signal": "HOLD"}

        # Calculate all indicators on the LTF dataframe
        df_ltf.ta.stochrsi(length=self.stoch_rsi_period, rsi_length=self.stoch_rsi_period, k=self.stoch_rsi_k, d=self.stoch_rsi_d, append=True)
        df_ltf.ta.bbands(length=self.bollinger_period, std=self.bollinger_std_dev, append=True)
        df_ltf.ta.atr(length=self.atr_period, append=True)

        stoch_k_col = f'STOCHRSIk_{self.stoch_rsi_period}_{self.stoch_rsi_period}_{self.stoch_rsi_k}_{self.stoch_rsi_d}'
        stoch_d_col = f'STOCHRSId_{self.stoch_rsi_period}_{self.stoch_rsi_period}_{self.stoch_rsi_k}_{self.stoch_rsi_d}'
        bbl_col = f'BBL_{self.bollinger_period}_{self.bollinger_std_dev:.1f}'
        bbu_col = f'BBU_{self.bollinger_period}_{self.bollinger_std_dev:.1f}'
        bbm_col = f'BBM_{self.bollinger_period}_{self.bollinger_std_dev:.1f}'
        atr_col = f'ATRr_{self.atr_period}'
        required_cols = [stoch_k_col, stoch_d_col, bbl_col, bbu_col, atr_col]

        if df_ltf.iloc[-2:][required_cols].isnull().values.any():
            logger.warning(f"NaN values in recent indicator data for {symbol}. Cannot generate signal.")
            return {"signal": "HOLD"}
            
        last = df_ltf.iloc[-1]
        prev = df_ltf.iloc[-2]
        
        # BUY Signal Logic ("Buy the Dip")
        if main_trend == "UP":
            # Condition: Stochastic RSI bullish crossover below the oversold line
            if prev[stoch_k_col] <= prev[stoch_d_col] and last[stoch_k_col] > last[stoch_d_col] and last[stoch_d_col] < self.stoch_rsi_oversold:
                logger.info(f"[{symbol}] Potential BUY Signal: Stochastic RSI bullish crossover in oversold area.")
                # Condition: Price pullback towards the middle Bollinger Band
                if last['close'] < last[bbm_col]:
                    logger.debug(f"[{symbol}] Bollinger Band check PASSED (Price is in lower half).")
                    last_atr = last[atr_col]
                    sl_price = last['low'] - (last_atr * self.atr_sl_multiplier)
                    tp_price = last['close'] + (last_atr * self.atr_tp_multiplier)
                    return {"signal": "BUY", "sl_price": sl_price, "tp_price": tp_price}
        
        # SELL Signal Logic ("Sell the Rip")
        if main_trend == "DOWN":
            # Condition: Stochastic RSI bearish crossover above the overbought line
            if prev[stoch_k_col] >= prev[stoch_d_col] and last[stoch_k_col] < last[stoch_d_col] and last[stoch_d_col] > self.stoch_rsi_overbought:
                logger.info(f"[{symbol}] Potential SELL Signal: Stochastic RSI bearish crossover in overbought area.")
                # Condition: Price pullback towards the middle Bollinger Band
                if last['close'] > last[bbm_col]:
                    logger.debug(f"[{symbol}] Bollinger Band check PASSED (Price is in upper half).")
                    last_atr = last[atr_col]
                    sl_price = last['high'] + (last_atr * self.atr_sl_multiplier)
                    tp_price = last['close'] - (last_atr * self.atr_tp_multiplier)
                    return {"signal": "SELL", "sl_price": sl_price, "tp_price": tp_price}
                    
        logger.debug(f"[{symbol}] No actionable signal found.")
        return {"signal": "HOLD"}
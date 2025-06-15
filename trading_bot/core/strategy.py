# trading_bot/core/strategy.py
import logging
import pandas as pd
import pandas_ta as ta  # For calculating technical analysis indicators

# Get the logger configured in main.py
logger = logging.getLogger("trading_bot")

class Strategy:
    def __init__(self, client, strategy_params=None):
        """
        Initializes the multi-condition, multi-timeframe Strategy.
        It uses parameters passed from main.py, which are loaded from settings.py.
        """
        self.client = client 
        self.params = strategy_params if strategy_params is not None else {}
        
        # --- Load all strategy parameters ---
        self.kline_interval = self.params.get("kline_interval", "15m")
        self.mta_kline_interval = self.params.get("mta_kline_interval", "1h")
        self.mta_ema_period = int(self.params.get("mta_ema_period", 50))
        self.short_ema_period = int(self.params.get("short_ema_period", 12))
        self.long_ema_period = int(self.params.get("long_ema_period", 26))
        self.rsi_period = int(self.params.get("rsi_period", 14))
        self.rsi_overbought = int(self.params.get("rsi_overbought", 70))
        self.rsi_oversold = int(self.params.get("rsi_oversold", 30))
        self.bollinger_period = int(self.params.get("bollinger_period", 20))
        self.bollinger_std_dev = int(self.params.get("bollinger_std_dev", 2))
        self.atr_period = int(self.params.get("atr_period", 14))
        self.atr_sl_multiplier = float(self.params.get("atr_sl_multiplier", 2.0))
        self.atr_tp_multiplier = float(self.params.get("atr_tp_multiplier", 4.0)) # for a 1:2 Risk/Reward
        self.kline_limit = int(self.params.get("kline_limit", 200))

        # --- Validate parameters ---
        if self.long_ema_period <= self.short_ema_period:
            raise ValueError("Long EMA period must be greater than Short EMA period.")
        
        required_data_length = max(self.long_ema_period, self.mta_ema_period, self.bollinger_period, self.rsi_period, self.atr_period) + 2
        if self.kline_limit < required_data_length:
             logger.warning(f"Kline limit ({self.kline_limit}) might be too small for the longest indicator period. "
                            f"Consider increasing kline_limit to at least {required_data_length} for stable indicators.")

        logger.info("Multi-condition Strategy with ATR risk management initialized.")

    def _get_and_prepare_data(self, symbol, interval, limit):
        """Helper function to fetch and prepare kline data as a pandas DataFrame."""
        logger.debug(f"Fetching {limit} klines for {symbol} with {interval} interval...")
        klines_data = self.client.get_historical_klines(symbol, interval, limit)
        
        min_required_data = max(self.long_ema_period, self.mta_ema_period, self.bollinger_period) + 1
        if not klines_data or len(klines_data) < min_required_data:
            logger.warning(f"Could not fetch sufficient kline data ({len(klines_data) if klines_data else 0}/{min_required_data}) for {symbol} [{interval}].")
            return None

        # Create DataFrame with correct column names
        df = pd.DataFrame(klines_data, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 
            'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 
            'taker_buy_quote_asset_volume', 'ignore'
        ])
        
        # Convert essential columns to numeric types
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(subset=numeric_cols, inplace=True)
        return df

    def generate_signal(self, symbol):
        """
        Generates a trading signal dictionary containing the action ('BUY'/'SELL'/'HOLD')
        and the calculated SL/TP prices based on ATR if a signal is found.
        Returns None if no actionable signal is generated.
        """
        logger.debug(f"--- Generating signal for {symbol} ---")

        # 1. Trend Filter (Higher Timeframe - e.g., 1h)
        df_htf = self._get_and_prepare_data(symbol, self.mta_kline_interval, self.kline_limit)
        if df_htf is None:
            logger.warning(f"Not enough HTF data for trend analysis on {symbol}. Returning HOLD.")
            return {"signal": "HOLD"}
            
        df_htf.ta.ema(length=self.mta_ema_period, append=True)
        last_price_htf = df_htf['close'].iloc[-1]
        last_mta_ema = df_htf[f'EMA_{self.mta_ema_period}'].iloc[-1]
        
        main_trend = "SIDEWAYS"
        if last_price_htf > last_mta_ema: main_trend = "UP"
        elif last_price_htf < last_mta_ema: main_trend = "DOWN"
        
        logger.debug(f"[{symbol} | {self.mta_kline_interval}] Main Trend: {main_trend} (Price: {last_price_htf:.4f}, EMA_{self.mta_ema_period}: {last_mta_ema:.4f})")

        if main_trend == "SIDEWAYS":
            return {"signal": "HOLD"}

        # 2. Entry Trigger & Confirmation Filters (Lower Timeframe - e.g., 15m)
        df_ltf = self._get_and_prepare_data(symbol, self.kline_interval, self.kline_limit)
        if df_ltf is None:
            logger.warning(f"Not enough LTF data for entry analysis on {symbol}. Returning HOLD.")
            return {"signal": "HOLD"}

        # Calculate all indicators on the LTF dataframe using pandas-ta
        df_ltf.ta.ema(length=self.short_ema_period, append=True)
        df_ltf.ta.ema(length=self.long_ema_period, append=True)
        df_ltf.ta.rsi(length=self.rsi_period, append=True)
        df_ltf.ta.bbands(length=self.bollinger_period, std=self.bollinger_std_dev, append=True)
        df_ltf.ta.atr(length=self.atr_period, append=True)

        required_cols = [f'EMA_{self.short_ema_period}', f'EMA_{self.long_ema_period}', f'RSI_{self.rsi_period}', f'BBM_{self.bollinger_period}_{self.bollinger_std_dev:.1f}', f'ATRr_{self.atr_period}']
        if df_ltf[required_cols].iloc[-2:].isnull().values.any():
            logger.warning(f"NaN values found in recent indicator data for {symbol}. Cannot generate signal.")
            return {"signal": "HOLD"}
            
        last = df_ltf.iloc[-1]
        prev = df_ltf.iloc[-2]

        # EMA Crossover Conditions
        short_ema_crossed_up = prev[f'EMA_{self.short_ema_period}'] <= prev[f'EMA_{self.long_ema_period}'] and last[f'EMA_{self.short_ema_period}'] > last[f'EMA_{self.long_ema_period}']
        short_ema_crossed_down = prev[f'EMA_{self.short_ema_period}'] >= prev[f'EMA_{self.long_ema_period}'] and last[f'EMA_{self.short_ema_period}'] < last[f'EMA_{self.long_ema_period}']
        
        # --- FINAL DECISION LOGIC ---
        
        # BUY Signal Logic (Mean Reversion)
        if main_trend == "UP" and short_ema_crossed_up:
            logger.info(f"[{symbol} | {self.kline_interval}] Potential BUY Signal (Bullish EMA Crossover). Checking filters...")
            # RSI Filter (Not overbought)
            if last[f'RSI_{self.rsi_period}'] < self.rsi_overbought:
                logger.debug(f"[{symbol}] RSI check PASSED (RSI: {last[f'RSI_{self.rsi_period}']:.2f} < {self.rsi_overbought})")
                # Bollinger Band "Buy the Dip" Filter
                # Check if price is in the lower half of the channel (between lower and middle band)
                if last['close'] < last[f'BBM_{self.bollinger_period}_{self.bollinger_std_dev:.1f}'] and \
                   last['close'] > last[f'BBL_{self.bollinger_period}_{self.bollinger_std_dev:.1f}']:
                    logger.debug(f"[{symbol}] Bollinger Band 'Buy the Dip' check PASSED.")
                    
                    # All conditions met, calculate ATR-based SL/TP and return signal
                    last_atr = last[f'ATRr_{self.atr_period}']
                    stop_loss_price = last['close'] - (last_atr * self.atr_sl_multiplier)
                    take_profit_price = last['close'] + (last_atr * self.atr_tp_multiplier)
                    logger.info(f"All conditions met for {symbol}. Final Signal: BUY")
                    return {"signal": "BUY", "sl_price": stop_loss_price, "tp_price": take_profit_price}
        
        # SELL Signal Logic (Mean Reversion)
        if main_trend == "DOWN" and short_ema_crossed_down:
            logger.info(f"[{symbol} | {self.kline_interval}] Potential SELL Signal (Bearish EMA Crossover). Checking filters...")
            # RSI Filter (Not oversold)
            if last[f'RSI_{self.rsi_period}'] > self.rsi_oversold:
                logger.debug(f"[{symbol}] RSI check PASSED (RSI: {last[f'RSI_{self.rsi_period}']:.2f} > {self.rsi_oversold})")
                # Bollinger Band "Sell the Rip" Filter
                # Check if price is in the upper half of the channel (between upper and middle band)
                if last['close'] > last[f'BBM_{self.bollinger_period}_{self.bollinger_std_dev:.1f}'] and \
                   last['close'] < last[f'BBU_{self.bollinger_period}_{self.bollinger_std_dev:.1f}']:
                    logger.debug(f"[{symbol}] Bollinger Band 'Sell the Rip' check PASSED.")

                    # All conditions met, calculate ATR-based SL/TP and return signal
                    last_atr = last[f'ATRr_{self.atr_period}']
                    stop_loss_price = last['close'] + (last_atr * self.atr_sl_multiplier)
                    take_profit_price = last['close'] - (last_atr * self.atr_tp_multiplier)
                    logger.info(f"All conditions met for {symbol}. Final Signal: SELL")
                    return {"signal": "SELL", "sl_price": stop_loss_price, "tp_price": take_profit_price}
                    
        logger.debug(f"[{symbol}] No signal generated. Main Trend: {main_trend}, Bullish Cross: {short_ema_crossed_up}, Bearish Cross: {short_ema_crossed_down}")
        return {"signal": "HOLD"}
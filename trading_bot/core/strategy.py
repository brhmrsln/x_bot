# trading_bot/core/strategy.py
import logging
import pandas as pd
import pandas_ta as ta # For calculating RSI, Bollinger Bands, etc.

logger = logging.getLogger("trading_bot")

class Strategy:
    def __init__(self, client, strategy_params=None):
        """
        Initializes the multi-condition, multi-timeframe Strategy.
        """
        self.client = client 
        self.params = strategy_params if strategy_params is not None else {}
        
        # --- Main Timeframe (for entry signals) ---
        self.kline_interval = self.params.get("kline_interval", "15m") 
        self.short_ema_period = int(self.params.get("short_ema_period", 10))
        self.long_ema_period = int(self.params.get("long_ema_period", 20))
        
        # --- Trend Filter Timeframe (higher timeframe) ---
        self.mta_kline_interval = self.params.get("mta_kline_interval", "1h") # MTA = Multi-Timeframe Analysis
        self.mta_ema_period = int(self.params.get("mta_ema_period", 50))
        
        # --- Confirmation Filter Parameters ---
        self.rsi_period = int(self.params.get("rsi_period", 14))
        self.rsi_overbought = int(self.params.get("rsi_overbought", 70))
        self.rsi_oversold = int(self.params.get("rsi_oversold", 30))
        self.bollinger_period = int(self.params.get("bollinger_period", 20))
        self.bollinger_std_dev = int(self.params.get("bollinger_std_dev", 2))

        # --- Data Fetching Limit ---
        # Must be enough for all indicator calculations
        self.kline_limit = int(self.params.get("kline_limit", max(self.long_ema_period, self.mta_ema_period, self.bollinger_period) + 50))

        logger.info("Multi-condition Strategy initialized with parameters.")
        # Add more detailed logging of params if needed

    def _get_data(self, symbol, interval, limit):
        """Helper function to fetch and prepare kline data."""
        logger.debug(f"Fetching {limit} klines for {symbol} with {interval} interval...")
        klines_data = self.client.get_historical_klines(symbol, interval, limit)
        if not klines_data or len(klines_data) < limit:
            logger.warning(f"Could not fetch sufficient kline data ({len(klines_data) if klines_data else 0}/{limit}) for {symbol} [{interval}].")
            return None

        df = pd.DataFrame(klines_data, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 
            'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 
            'taker_buy_quote_asset_volume', 'ignore'
        ])
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(subset=numeric_cols, inplace=True)
        return df

    def generate_signal(self, symbol):
        """
        Generates a trading signal ("BUY", "SELL", or "HOLD") based on a
        multi-timeframe, multi-indicator strategy.
        """
        logger.debug(f"--- Generating signal for {symbol} ---")

        # 1. Trend Filter (Higher Timeframe - e.g., 1h)
        df_htf = self._get_data(symbol, self.mta_kline_interval, self.kline_limit)
        if df_htf is None or len(df_htf) < self.mta_ema_period:
            logger.warning(f"Not enough HTF data for trend analysis on {symbol}. Returning HOLD.")
            return "HOLD"
            
        df_htf.ta.ema(length=self.mta_ema_period, append=True)
        last_price = df_htf['close'].iloc[-1]
        last_mta_ema = df_htf[f'EMA_{self.mta_ema_period}'].iloc[-1]
        
        main_trend = "SIDEWAYS"
        if last_price > last_mta_ema: main_trend = "UP"
        elif last_price < last_mta_ema: main_trend = "DOWN"
        
        logger.debug(f"[{symbol} | {self.mta_kline_interval}] Main Trend determined as: {main_trend} (Price: {last_price}, EMA_{self.mta_ema_period}: {last_mta_ema:.2f})")

        if main_trend == "SIDEWAYS":
            logger.debug(f"[{symbol}] Main trend is sideways. No trade signal. Returning HOLD.")
            return "HOLD"

        # 2. Entry Trigger & Confirmation Filters (Lower Timeframe - e.g., 15m)
        df_ltf = self._get_data(symbol, self.kline_interval, self.kline_limit)
        if df_ltf is None or len(df_ltf) < self.long_ema_period + 1:
            logger.warning(f"Not enough LTF data for entry analysis on {symbol}. Returning HOLD.")
            return "HOLD"

        # Calculate all indicators on the LTF dataframe
        df_ltf.ta.ema(length=self.short_ema_period, append=True)
        df_ltf.ta.ema(length=self.long_ema_period, append=True)
        df_ltf.ta.rsi(length=self.rsi_period, append=True)
        df_ltf.ta.bbands(length=self.bollinger_period, std=self.bollinger_std_dev, append=True)
        
        # Check for NaN values in the last row for all necessary indicators
        required_cols = [f'EMA_{self.short_ema_period}', f'EMA_{self.long_ema_period}', f'RSI_{self.rsi_period}', f'BBM_{self.bollinger_period}_{self.bollinger_std_dev}.0']
        if df_ltf[required_cols].iloc[-2:].isnull().values.any():
            logger.warning(f"NaN values found in recent indicator data for {symbol}. Cannot generate signal. Returning HOLD.")
            return "HOLD"
            
        # Get latest values
        last_row = df_ltf.iloc[-1]
        prev_row = df_ltf.iloc[-2]

        # EMA Crossover check
        short_ema_crossed_up = prev_row[f'EMA_{self.short_ema_period}'] <= prev_row[f'EMA_{self.long_ema_period}'] and \
                               last_row[f'EMA_{self.short_ema_period}'] > last_row[f'EMA_{self.long_ema_period}']
        
        short_ema_crossed_down = prev_row[f'EMA_{self.short_ema_period}'] >= prev_row[f'EMA_{self.long_ema_period}'] and \
                                 last_row[f'EMA_{self.short_ema_period}'] < last_row[f'EMA_{self.long_ema_period}']

        # --- FINAL DECISION LOGIC ---
        # BUY Signal Logic
        if main_trend == "UP" and short_ema_crossed_up:
            logger.info(f"[{symbol} | {self.kline_interval}] Potential BUY Signal (Bullish EMA Crossover). Checking confirmation filters...")
            # RSI Filter
            if last_row[f'RSI_{self.rsi_period}'] < self.rsi_overbought:
                logger.debug(f"[{symbol}] RSI check PASSED (RSI: {last_row[f'RSI_{self.rsi_period}']:.2f} < {self.rsi_overbought})")
                # Bollinger Band Filter
                if last_row['close'] > last_row[f'BBM_{self.bollinger_period}_{self.bollinger_std_dev}.0']: # Price is above middle band
                    logger.debug(f"[{symbol}] Bollinger Band check PASSED (Close: {last_row['close']} > Middle Band: {last_row[f'BBM_{self.bollinger_period}_{self.bollinger_std_dev}.0']:.2f})")
                    logger.info(f"All conditions met for {symbol}. Final Signal: BUY")
                    return "BUY"
        
        # SELL Signal Logic
        if main_trend == "DOWN" and short_ema_crossed_down:
            logger.info(f"[{symbol} | {self.kline_interval}] Potential SELL Signal (Bearish EMA Crossover). Checking confirmation filters...")
            # RSI Filter
            if last_row[f'RSI_{self.rsi_period}'] > self.rsi_oversold:
                logger.debug(f"[{symbol}] RSI check PASSED (RSI: {last_row[f'RSI_{self.rsi_period}']:.2f} > {self.rsi_oversold})")
                # Bollinger Band Filter
                if last_row['close'] < last_row[f'BBM_{self.bollinger_period}_{self.bollinger_std_dev}.0']: # Price is below middle band
                    logger.debug(f"[{symbol}] Bollinger Band check PASSED (Close: {last_row['close']} < Middle Band: {last_row[f'BBM_{self.bollinger_period}_{self.bollinger_std_dev}.0']:.2f})")
                    logger.info(f"All conditions met for {symbol}. Final Signal: SELL")
                    return "SELL"
                    
        logger.debug(f"[{symbol}] No signal generated. Main Trend: {main_trend}, Bullish Cross: {short_ema_crossed_up}, Bearish Cross: {short_ema_crossed_down}")
        return "HOLD"

if __name__ == '__main__':
    # TODO test logic
    print("Standalone test for the new strategy is complex and requires a sophisticated mock client.")
    print("It's recommended to test this strategy through the main.py entry point with real Testnet data.")
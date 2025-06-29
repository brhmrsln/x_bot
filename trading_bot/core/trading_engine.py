# trading_bot/core/trading_engine.py

import logging
import time
import json
import os
import sys
import pandas as pd

try:
    from trading_bot.config import settings
    from trading_bot.exchange.binance_client import BinanceFuturesClient
    from trading_bot.core.market_scanner import get_top_volume_usdt_futures_symbols
    from trading_bot.utils.trade_logger import log_trade
    from trading_bot.utils.notifier import send_telegram_message
    from trading_bot.core.base_strategy import BaseStrategy
except ImportError as e:
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from trading_bot.config import settings
    from trading_bot.exchange.binance_client import BinanceFuturesClient
    from trading_bot.core.market_scanner import get_top_volume_usdt_futures_symbols
    from trading_bot.utils.trade_logger import log_trade
    from trading_bot.utils.notifier import send_telegram_message
    from trading_bot.core.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class TradingEngine:
    def __init__(self, client: BinanceFuturesClient, strategy: BaseStrategy):
        self.client = client
        self.strategy = strategy
        self.running = False
        
        # Load configurable parameters from settings
        self.loop_interval_seconds = settings.ENGINE_LOOP_INTERVAL_SECONDS
        self.symbols_to_scan_count = settings.SCAN_TOP_N_SYMBOLS
        self.min_24h_quote_volume = settings.MIN_24H_QUOTE_VOLUME
        self.max_concurrent_positions = settings.MAX_CONCURRENT_POSITIONS
        self.position_size_usdt = settings.POSITION_SIZE_USDT
        self.leverage = settings.LEVERAGE

        # State Management
        self.state_file_path = settings.STATE_FILE_PATH
        self.open_positions = self._load_state()

        logger.info("TradingEngine initialized with parameters:")
        logger.info(f"  Loop Interval: {self.loop_interval_seconds} seconds")
        logger.info(f"  Symbols to Scan: Top {self.symbols_to_scan_count}")
        logger.info(f"  Min 24h Volume: {self.min_24h_quote_volume:,.0f} USDT")
        logger.info(f"  Max Concurrent Positions: {self.max_concurrent_positions}")
        logger.info(f"  Position Size: {self.position_size_usdt} USDT")
        logger.info(f"  Leverage: {self.leverage}x")
        logger.info(f"Engine started. Found and loaded {len(self.open_positions)} existing position(s) from state file.")

    def _load_state(self):
        if not os.path.exists(self.state_file_path):
            logger.info(f"State file '{self.state_file_path}' not found. Starting with empty state.")
            return {}
        try:
            with open(self.state_file_path, 'r', encoding='utf-8') as f:
                positions = json.load(f)
                logger.info(f"Successfully loaded state from '{self.state_file_path}'.")
                return positions if isinstance(positions, dict) else {}
        except (json.JSONDecodeError, TypeError):
            logger.error(f"Error decoding JSON from '{self.state_file_path}' or file is malformed. Starting fresh.", exc_info=True)
            return {}
        except Exception as e:
            logger.error(f"An unexpected error occurred loading state from '{self.state_file_path}': {e}", exc_info=True)
            return {}

    def _save_state(self):
        logger.debug(f"Saving current state ({len(self.open_positions)} open positions) to '{self.state_file_path}'...")
        try:
            state_dir = os.path.dirname(self.state_file_path)
            os.makedirs(state_dir, exist_ok=True)
            with open(self.state_file_path, 'w', encoding='utf-8') as f:
                json.dump(self.open_positions, f, indent=4)
            logger.info(f"Successfully saved state. {len(self.open_positions)} position(s) are actively managed.")
        except Exception as e:
            logger.error(f"CRITICAL: Could not save state to '{self.state_file_path}': {e}", exc_info=True)

    def stop(self):
        logger.info("Stopping TradingEngine...")
        self.running = False

    def run(self):
        logger.info("Starting TradingEngine...")
        self.running = True
        while self.running:
            try:
                logger.info("--- Starting new trading loop iteration ---")
                self._manage_open_positions()
                if len(self.open_positions) < self.max_concurrent_positions:
                    self._scan_for_new_trades()
                else:
                    logger.info(f"Maximum concurrent positions ({self.max_concurrent_positions}) reached. Not scanning for new entries.")
                
                logger.info(f"--- Trading loop iteration finished. Waiting for {self.loop_interval_seconds} seconds... ---")
                time.sleep(self.loop_interval_seconds)
            except KeyboardInterrupt:
                self.stop()
            except Exception as e:
                logger.critical(f"A critical error occurred in the main trading loop: {e}", exc_info=True)
                send_telegram_message(f"🚨 **CRITICAL ERROR** 🚨\n\nBot loop failed: {e}")
                logger.info("Pausing for 60 seconds before retrying...")
                time.sleep(60)
        logger.info("TradingEngine has been stopped.")

    def _manage_open_positions(self):
        if not self.open_positions:
            logger.debug("No open positions to manage.")
            return

        logger.info(f"Managing {len(self.open_positions)} open position(s): {list(self.open_positions.keys())}")
        
        all_positions_df = self.client.get_all_open_positions_df()
        
        for symbol, position_data in list(self.open_positions.items()):
            if symbol not in all_positions_df.index:
                logger.info(f"Position for {symbol} appears to be closed on the exchange. Logging and cleaning up.")
                log_trade({'symbol': symbol, 'pnl_usd': 'N/A - Closed externally', 'side': position_data.get('side')})
                send_telegram_message(f"🔔 **Position Closed Externally:**\nSymbol: `{symbol}`")
                del self.open_positions[symbol]
                self._save_state()

    def _scan_for_new_trades(self):
        logger.info("Scanning for new trade opportunities...")
        symbols_to_check = get_top_volume_usdt_futures_symbols(
            client=self.client, count=self.symbols_to_scan_count, min_quote_volume=self.min_24h_quote_volume)
        
        if not symbols_to_check:
            logger.warning("Market scanner did not return any symbols to check.")
            return

        for symbol in symbols_to_check:
            if not self.running or len(self.open_positions) >= self.max_concurrent_positions:
                if len(self.open_positions) >= self.max_concurrent_positions:
                    logger.info("Max concurrent positions reached. Stopping scan for this loop.")
                break 
            
            logger.debug(f"Processing symbol: {symbol}")
            trade_initiated = self._process_symbol_for_entry(symbol)
            if trade_initiated:
                logger.info(f"A new trade was initiated for {symbol}. Stopping scan for this loop.")
                break
            time.sleep(2)

    def _process_symbol_for_entry(self, symbol):
        if symbol in self.open_positions:
            logger.debug(f"Already managing an internal position for {symbol}. Skipping.")
            return False

        try:
            kline_interval = settings.STRATEGY_KLINE_INTERVAL
            kline_limit = 200
            
            logger.debug(f"Fetching {kline_limit} klines for {symbol} with interval {kline_interval}...")
            klines_df = self.client.get_historical_klines(symbol, kline_interval, limit=kline_limit)

            if klines_df is None or klines_df.empty or len(klines_df) < kline_limit:
                logger.warning(f"Not enough kline data for {symbol}. Need {kline_limit}, got {len(klines_df)}.")
                return False

            signal, sl_price, tp_price = self.strategy.generate_signal(data=klines_df)
            
            if signal in ["BUY", "SELL"] and sl_price is not None and tp_price is not None:
                logger.info(f"Actionable signal '{signal}' received for {symbol}. Preparing to execute trade...")
                return self._execute_trade(symbol, signal, sl_price, tp_price)
        
        except Exception as e:
            logger.error(f"Error processing symbol {symbol} for entry: {e}", exc_info=True)
        
        return False

    def _execute_trade(self, symbol, signal, sl_price, tp_price):
        try:
            side = "BUY" if signal == "BUY" else "SELL"
            logger.info(f"Executing {side} trade for {symbol} | SL: {sl_price:.4f} | TP: {tp_price:.4f}")

            # Set leverage before placing trade
            self.client.set_leverage(symbol=symbol, leverage=self.leverage)
            time.sleep(0.5)

            # Open the position with SL/TP orders
            # This is a simplified call; your client's method might differ
            # Assume it returns a tuple: (entry_order, stop_order, tp_order)
            result = self.client.open_position_market_with_sl_tp(
                symbol=symbol,
                order_side=side,
                position_size_usdt=self.position_size_usdt,
                stop_loss_price=sl_price,
                take_profit_price=tp_price
            )
            
            # This part needs to be adapted based on what your client method returns
            if result and result[0] and result[0].get('status') == 'FILLED':
                entry_order = result[0]
                logger.info(f"Successfully opened new {side} position for {symbol}. Updating internal state.")
                
                # Update internal state
                self.open_positions[symbol] = {
                    "side": side,
                    "quantity": float(entry_order.get('executedQty')),
                    "entry_price": float(entry_order.get('avgPrice')),
                    # ... add other necessary info ...
                }
                self._save_state()
                
                # Send notification
                msg = f"🚀 **NEW POSITION OPENED** 🚀\n\n`{symbol}` | **{side}**"
                send_telegram_message(msg)
                
                return True
            else:
                logger.error(f"Failed to open new {side} position for {symbol}. Result: {result}")
                return False

        except Exception as e:
            logger.error(f"An error occurred during trade execution for {symbol}: {e}", exc_info=True)
            return False
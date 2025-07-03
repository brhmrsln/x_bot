# trading_bot/core/trading_engine.py

import logging
import time
import json
import os
import sys
import pandas as pd
from datetime import datetime

try:
    from trading_bot.config import settings
    from trading_bot.exchange.binance_client import BinanceFuturesClient
    from trading_bot.core.market_scanner import get_top_volume_usdt_futures_symbols
    from trading_bot.utils.trade_logger import log_trade
    from trading_bot.utils.notifier import send_telegram_message
    from trading_bot.core.base_strategy import BaseStrategy
except ImportError:
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    if project_root not in sys.path: sys.path.insert(0, project_root)
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
        
        self.loop_interval_seconds = settings.ENGINE_LOOP_INTERVAL_SECONDS
        self.symbols_to_scan_count = settings.SCAN_TOP_N_SYMBOLS
        self.max_concurrent_positions = settings.MAX_CONCURRENT_POSITIONS
        self.position_size_usdt = settings.POSITION_SIZE_USDT
        self.leverage = settings.LEVERAGE

        self.state_file_path = settings.STATE_FILE_PATH
        self.open_positions = self._load_state()

    def _load_state(self):
        if not os.path.exists(self.state_file_path): return {}
        try:
            with open(self.state_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading state file: {e}")
            return {}

    def _save_state(self):
        try:
            with open(self.state_file_path, 'w', encoding='utf-8') as f:
                json.dump(self.open_positions, f, indent=4)
        except Exception as e:
            logger.error(f"CRITICAL: Could not save state: {e}")

    def stop(self):
        self.running = False

    def run(self):
        logger.info("TradingEngine starting main loop...")
        self.running = True
        while self.running:
            try:
                logger.info("--- Starting new trading loop iteration ---")
                self._manage_open_positions()
                if len(self.open_positions) < self.max_concurrent_positions:
                    self._scan_for_new_trades()
                else:
                    logger.info(f"Max concurrent positions ({self.max_concurrent_positions}) reached.")
                
                logger.info(f"--- Loop finished. Waiting for {self.loop_interval_seconds} seconds... ---")
                time.sleep(self.loop_interval_seconds)
            except KeyboardInterrupt:
                self.stop()
            except Exception as e:
                logger.critical(f"A critical error occurred in the main trading loop: {e}", exc_info=True)
                time.sleep(60)
        logger.info("TradingEngine has been stopped.")

    # --- COMPLETELY REWRITTEN FUNCTION FOR ROBUST MANAGEMENT ---
    def _manage_open_positions(self):
        """
        Manages open positions by checking the single source of truth: the exchange's open positions list.
        If a position in our state is no longer open on the exchange, it's considered closed.
        """
        if not self.open_positions:
            logger.debug("No internal positions to manage.")
            return

        logger.info(f"Managing {len(self.open_positions)} internal position(s): {list(self.open_positions.keys())}")
        
        # The single source of truth for what's currently open
        exchange_open_positions_df = self.client.get_all_open_positions_df()
        
        # Iterate over a copy because we will modify the dictionary
        for symbol, internal_pos_data in list(self.open_positions.items()):
            
            # If the symbol from our state file is NOT in the list of open positions from the exchange...
            if symbol not in exchange_open_positions_df.index:
                logger.info(f"Position for {symbol} is no longer open on the exchange. Handling closure...")

                # 1. CRITICAL STEP: Cancel any lingering SL/TP orders for this symbol. This fixes the bug.
                logger.info(f"Cancelling all open orders for {symbol} to clean up...")
                self.client.cancel_all_open_orders(symbol)
                
                # 2. Log the trade (we don't know the exact PnL without querying trade history, so log as "unknown")
                log_trade({
                    'symbol': symbol,
                    'pnl_usd': 'Unknown (Closed by SL/TP)',
                    'side': internal_pos_data.get('side'),
                    'exit_reason': 'STOP_LOSS or TAKE_PROFIT'
                })
                
                # 3. Send notification
                send_telegram_message(f"✅ **Position Closed:**\nSymbol: `{symbol}`\nReason: Stop-Loss or Take-Profit hit.")

                # 4. Remove from our internal state and save
                del self.open_positions[symbol]
                self._save_state()
                logger.info(f"Position for {symbol} removed from internal state.")

            else:
                # If the position is still open on the exchange, do nothing.
                logger.debug(f"Position for {symbol} is still confirmed open on the exchange.")
            
            time.sleep(1) # Small delay between checking each internal position

    def _scan_for_new_trades(self):
        # This function's logic remains the same
        logger.info("Scanning for new trade opportunities...")
        symbols_to_check = get_top_volume_usdt_futures_symbols(self.client)
        if not symbols_to_check:
            logger.warning("Market scanner returned no symbols.")
            return

        for symbol in symbols_to_check:
            if not self.running or len(self.open_positions) >= self.max_concurrent_positions: break
            self._process_symbol_for_entry(symbol)
            time.sleep(2)

    def _process_symbol_for_entry(self, symbol):
        # This function's logic remains the same
        if symbol in self.open_positions: return False
        try:
            klines_df = self.client.get_historical_klines(symbol, settings.STRATEGY_KLINE_INTERVAL, limit=200)
            if klines_df.empty or len(klines_df) < 200: return False
            
            signal, sl_price, tp_price = self.strategy.generate_signal(data=klines_df)
            
            if signal:
                return self._execute_trade(symbol, signal, sl_price, tp_price)
        except Exception as e:
            logger.error(f"Error processing {symbol} for entry: {e}")
        return False

    def _execute_trade(self, symbol, signal, sl_price, tp_price):
        # This function's logic remains the same
        side = "BUY" if signal == "BUY" else "SELL"
        logger.info(f"Executing {side} trade for {symbol}...")
        try:
            self.client.set_leverage(symbol, self.leverage)
            entry, sl_order, tp_order = self.client.open_position_market_with_sl_tp(
                symbol, side, self.position_size_usdt, sl_price, tp_price
            )
            if entry and sl_order and tp_order:
                self.open_positions[symbol] = {
                    "side": side, "entry_price": float(entry['avgPrice']),
                    "quantity": float(entry['executedQty']),
                    "stop_loss_order_id": sl_order.get('orderId'),
                    "take_profit_order_id": tp_order.get('orderId')
                }
                self._save_state()
                send_telegram_message(f"🚀 **NEW POSITION OPENED**\n`{symbol}` | **{side}**")
                return True
        except Exception as e:
            logger.error(f"Trade execution failed for {symbol}: {e}")
        return False
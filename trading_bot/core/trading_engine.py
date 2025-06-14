# trading_bot/core/trading_engine.py
import logging
import time
import json
import os

try:
    from trading_bot.config import settings
    from trading_bot.exchange.binance_client import BinanceFuturesClient
    from trading_bot.core.strategy import Strategy
    from trading_bot.core.market_scanner import get_top_volume_usdt_futures_symbols
    from trading_bot.utils.trade_logger import log_trade
except ImportError as e:
    print(f"CRITICAL: Failed to import necessary modules in TradingEngine: {e}")
    import sys
    sys.exit("Exiting due to import error. Please run from project root or check PYTHONPATH.")

logger = logging.getLogger("trading_bot")

class TradingEngine:
    def __init__(self, client: BinanceFuturesClient, strategy: Strategy):
        """
        Initializes the TradingEngine and loads state from a file on startup.
        """
        self.client = client
        self.strategy = strategy
        self.running = False
        
        # --- Load configurable parameters from settings ---
        self.loop_interval_seconds = settings.ENGINE_LOOP_INTERVAL_SECONDS
        self.symbols_to_scan_count = settings.SCAN_TOP_N_SYMBOLS
        self.min_24h_quote_volume = settings.MIN_24H_QUOTE_VOLUME
        self.max_concurrent_positions = settings.MAX_CONCURRENT_POSITIONS
        self.position_size_usdt = settings.POSITION_SIZE_USDT
        self.sl_percentage = settings.STOP_LOSS_PERCENTAGE
        self.tp_percentage = settings.TAKE_PROFIT_PERCENTAGE
        self.leverage = settings.LEVERAGE

        # --- State Management: Load open positions from file on startup ---
        self.state_file_path = "open_positions.json"
        self.open_positions = self._load_state()

        logger.info("TradingEngine initialized with parameters:")
        logger.info(f"  Loop Interval: {self.loop_interval_seconds} seconds")
        logger.info(f"  Symbols to Scan: Top {self.symbols_to_scan_count}")
        logger.info(f"  Min 24h Volume: {self.min_24h_quote_volume:,.0f} USDT")
        logger.info(f"  Max Concurrent Positions: {self.max_concurrent_positions}")
        logger.info(f"  Position Size: {self.position_size_usdt} USDT (nominal)")
        logger.info(f"  Leverage: {self.leverage}x")
        logger.info(f"  Stop-Loss: {self.sl_percentage*100:.2f}%")
        logger.info(f"  Take-Profit: {self.tp_percentage*100:.2f}%")
        logger.info(f"Engine started. Found and loaded {len(self.open_positions)} existing position(s) from state file.")

    def _load_state(self):
        """Loads the open positions from the state file (open_positions.json)."""
        if not os.path.exists(self.state_file_path):
            logger.info(f"State file '{self.state_file_path}' not found. Starting with empty state.")
            return {}
        try:
            with open(self.state_file_path, 'r', encoding='utf-8') as f:
                positions = json.load(f)
                logger.info(f"Successfully loaded state from '{self.state_file_path}'.")
                return positions if isinstance(positions, dict) else {}
        except (json.JSONDecodeError, TypeError):
            logger.error(f"Error decoding JSON from '{self.state_file_path}' or file is malformed. Starting with a clean slate.", exc_info=True)
            return {}
        except Exception as e:
            logger.error(f"An unexpected error occurred loading state from '{self.state_file_path}': {e}", exc_info=True)
            return {}

    def _save_state(self):
        """Saves the current self.open_positions dictionary to the state file."""
        logger.debug(f"Saving current state ({len(self.open_positions)} open positions) to '{self.state_file_path}'...")
        try:
            with open(self.state_file_path, 'w', encoding='utf-8') as f:
                json.dump(self.open_positions, f, indent=4)
                logger.info(f"Successfully saved state. {len(self.open_positions)} position(s) are actively managed.")
        except Exception as e:
            logger.error(f"CRITICAL: Could not save state to '{self.state_file_path}': {e}", exc_info=True)

    def stop(self):
        """Stops the trading engine loop gracefully."""
        logger.info("Stopping TradingEngine...")
        self.running = False

    def run(self):
        """Starts the main trading engine loop."""
        logger.info("Starting TradingEngine...")
        self.running = True

        while self.running:
            try:
                logger.info("--- Starting new trading loop iteration ---")
                
                # 1. Manage existing open positions (check for SL/TP hits, etc.)
                self._manage_open_positions()

                # 2. Scan for new trade opportunities if below max capacity
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
                logger.info("Pausing for 60 seconds before retrying...")
                time.sleep(60)

        logger.info("TradingEngine has been stopped.")
        
    def _manage_open_positions(self):
        """Iterates through open positions, checks their status, and handles closure."""
        if not self.open_positions:
            logger.debug("No open positions to manage.")
            return

        logger.info(f"Managing {len(self.open_positions)} open position(s): {list(self.open_positions.keys())}")
        
        symbols_to_remove_from_state = []

        for symbol, trade_info in self.open_positions.items():
            if not self.running: break
            
            logger.debug(f"Checking status for position: {symbol}")

            sl_order_id = trade_info.get("stop_loss_order_id")
            tp_order_id = trade_info.get("take_profit_order_id")
            is_closed = False
            closing_order_data = None
            exit_reason = "UNKNOWN"
            
            # Check Stop-Loss Order Status
            if sl_order_id:
                sl_order = self.client.query_order(symbol, sl_order_id)
                if sl_order and sl_order.get('status') == 'FILLED':
                    logger.info(f"STOP-LOSS order {sl_order_id} for {symbol} has been FILLED.")
                    closing_order_data, exit_reason = sl_order, "STOP_LOSS"
                    if tp_order_id: self.client.cancel_order(symbol, tp_order_id)
                    is_closed = True
                elif sl_order and sl_order.get('status') not in ['NEW', 'PARTIALLY_FILLED']:
                    logger.warning(f"Stop-Loss order {sl_order_id} for {symbol} is no longer active (Status: {sl_order.get('status')}). Assuming position is compromised. Removing from state.")
                    if tp_order_id: self.client.cancel_order(symbol, tp_order_id)
                    is_closed = True

            # Check Take-Profit Order Status (only if SL was not filled)
            if not is_closed and tp_order_id:
                tp_order = self.client.query_order(symbol, tp_order_id)
                if tp_order and tp_order.get('status') == 'FILLED':
                    logger.info(f"TAKE-PROFIT order {tp_order_id} for {symbol} has been FILLED.")
                    closing_order_data, exit_reason = tp_order, "TAKE_PROFIT"
                    if sl_order_id: self.client.cancel_order(symbol, sl_order_id)
                    is_closed = True
                elif tp_order and tp_order.get('status') not in ['NEW', 'PARTIALLY_FILLED']:
                    logger.warning(f"Take-Profit order {tp_order_id} for {symbol} is no longer active (Status: {tp_order.get('status')}). Assuming position is compromised. Removing from state.")
                    if sl_order_id: self.client.cancel_order(symbol, sl_order_id)
                    is_closed = True
            
            if is_closed:
                if closing_order_data: 
                    self._handle_trade_closure(symbol, trade_info, closing_order_data, exit_reason)
                symbols_to_remove_from_state.append(symbol)
            else:
                 logger.debug(f"Position for {symbol} is still open.")

            time.sleep(1)

        if symbols_to_remove_from_state:
            for symbol in set(symbols_to_remove_from_state):
                if symbol in self.open_positions:
                    del self.open_positions[symbol]
            self._save_state()

    def _handle_trade_closure(self, symbol, entry_trade_info, closing_order, exit_reason):
        """Calculates PnL and logs the completed trade to the CSV file."""
        logger.info(f"Handling closure of trade for {symbol} due to {exit_reason}.")
        
        exit_price = float(closing_order.get('avgPrice', 0))
        entry_price = entry_trade_info.get('entry_price', 0)
        quantity = entry_trade_info.get('quantity', 0)
        side = entry_trade_info.get('side')
        entry_commission = entry_trade_info.get('entry_commission', 0.0)

        exit_commission = 0.0
        closing_order_id = closing_order.get('orderId')
        if closing_order_id:
            trade_details = self.client.get_trades_for_order(symbol, closing_order_id)
            if trade_details:
                exit_commission = trade_details.get('total_commission', 0.0)
        total_commission = entry_commission + exit_commission
        
        if entry_price == 0 or quantity == 0:
            logger.error(f"Could not calculate PnL for {symbol} due to missing entry data (price or quantity is zero).")
            return
            
        pnl_usdt = 0.0
        if side.upper() == "LONG": pnl_usdt = (exit_price - entry_price) * quantity
        elif side.upper() == "SHORT": pnl_usdt = (entry_price - exit_price) * quantity
        
        net_pnl_usdt = pnl_usdt - total_commission
        entry_nominal_value = entry_price * quantity
        pnl_percentage = (net_pnl_usdt / entry_nominal_value) if entry_nominal_value != 0 else 0.0
        
        logger.info(f"Trade Closed for {symbol}: Gross PnL={pnl_usdt:.4f} USDT, Total Commission={total_commission:.6f}, Net PnL={net_pnl_usdt:.4f} USDT")
        
        log_trade({
            'symbol': symbol, 'side': side, 'quantity': quantity, 'entry_price': entry_price,
            'exit_price': exit_price, 'pnl_usdt': net_pnl_usdt, 'pnl_percentage': pnl_percentage,
            'entry_commission': entry_commission, 'exit_commission': exit_commission, 'total_commission': total_commission,
            'entry_reason': entry_trade_info.get('entry_reason', 'N/A'), 'exit_reason': exit_reason
        })

    def _scan_for_new_trades(self):
        """Scans the market and processes symbols for potential new entries."""
        symbols_to_check = get_top_volume_usdt_futures_symbols(
            client=self.client, count=self.symbols_to_scan_count, min_quote_volume=self.min_24h_quote_volume)
        if not symbols_to_check:
            logger.warning("Market scanner did not return any symbols to check.")
            return

        for symbol in symbols_to_check:
            if not self.running: break
            if len(self.open_positions) >= self.max_concurrent_positions:
                logger.info("Max concurrent positions reached. Stopping scan for new trades in this loop.")
                break 
            
            self._process_symbol_for_entry(symbol)
            time.sleep(2)

    def _process_symbol_for_entry(self, symbol):
        """Processes a single symbol for a potential new trade entry."""
        if symbol in self.open_positions:
            logger.debug(f"Already managing an internal position state for {symbol}. Skipping for new entry signal.")
            return True # Returning True to indicate we are "busy" with this symbol.

        try:
            exchange_positions = self.client.get_position_info(symbol)
            if exchange_positions:
                logger.warning(f"Found an existing position for {symbol} on the exchange while checking for a new entry. "
                               "Skipping trade to avoid duplicates. Please sync state or close manually.")
                return True # Indicate busy to stop further scanning in this loop
        except Exception as e:
            logger.error(f"Could not verify existing position for {symbol} due to an API error: {e}. Skipping trade for safety.", exc_info=True)
            return False

        signal = self.strategy.generate_signal(symbol)
        if signal == "BUY" or signal == "SELL":
            logger.info(f"Actionable signal '{signal}' received for {symbol}. Preparing to execute trade...")
            trade_opened = self._execute_trade(symbol, signal)
            return trade_opened
        return False

    def _execute_trade(self, symbol, side):
        """Sets leverage, calculates SL/TP, places orders, and updates state."""
        try:
            self.client.set_leverage(symbol=symbol, leverage=self.leverage)
            time.sleep(0.5)
            
            current_price = self.client.get_mark_price(symbol)
            if not current_price:
                logger.error(f"Could not get MARK PRICE for {symbol}. Cannot execute trade.")
                return False

            symbol_info = self.client._get_symbol_info(symbol)
            if not symbol_info:
                 logger.error(f"Could not get symbol info for {symbol}. Cannot validate filters.")
                 return False

            if side.upper() == "BUY":
                sl_price = current_price * (1 - self.sl_percentage)
                tp_price = current_price * (1 + self.tp_percentage)
            elif side.upper() == "SELL":
                sl_price = current_price * (1 + self.sl_percentage)
                tp_price = current_price * (1 - self.tp_percentage)
            else: 
                logger.error(f"Invalid side '{side}' provided to _execute_trade.")
                return False

            price_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'PERCENT_PRICE'), None)
            if price_filter:
                multiplier_up = float(price_filter['multiplierUp'])
                multiplier_down = float(price_filter['multiplierDown'])
                max_allowed_price = self.client._format_price(symbol, current_price * multiplier_up)
                min_allowed_price = self.client._format_price(symbol, current_price * multiplier_down)
                
                original_tp = tp_price
                original_sl = sl_price
                tp_price = max(min(tp_price, max_allowed_price), min_allowed_price)
                sl_price = max(min(sl_price, max_allowed_price), min_allowed_price)

                if tp_price != original_tp: logger.warning(f"TP price for {symbol} adjusted from {original_tp} to {tp_price} due to PERCENT_PRICE filter.")
                if sl_price != original_sl: logger.warning(f"SL price for {symbol} adjusted from {original_sl} to {sl_price} due to PERCENT_PRICE filter.")
            
            entry_order, stop_order, tp_order = self.client.open_position_market_with_sl_tp(
                symbol=symbol, order_side=side, position_size_usdt=self.position_size_usdt,
                stop_loss_price=sl_price, take_profit_price=tp_price)

            if entry_order and entry_order.get('status') == 'FILLED':
                entry_commission = 0.0
                entry_order_id = entry_order.get('orderId')
                if entry_order_id:
                    time.sleep(1) 
                    trade_details = self.client.get_trades_for_order(symbol, entry_order_id)
                    if trade_details: entry_commission = trade_details.get('total_commission', 0.0)

                logger.info(f"Successfully opened new {side} position for {symbol}. Updating internal state.")
                self.open_positions[symbol] = {
                    "side": side, "quantity": float(entry_order.get('executedQty')),
                    "entry_price": float(entry_order.get('avgPrice')), "entry_commission": entry_commission,
                    "entry_order_id": entry_order_id, "stop_loss_order_id": stop_order.get('orderId') if stop_order else None,
                    "take_profit_order_id": tp_order.get('orderId') if tp_order else None, "entry_reason": "EMA_CROSSOVER",
                }
                self._save_state()
                return True
            else:
                logger.error(f"Failed to open new {side} position for {symbol}. Entry order response: {entry_order}")
                return False
        
        except Exception as e:
            logger.error(f"An error occurred during trade execution for {symbol}: {e}", exc_info=True)
            return False
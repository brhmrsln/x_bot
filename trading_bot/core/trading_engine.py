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
    from trading_bot.utils.notifier import send_telegram_message
except ImportError as e:
    print(f"CRITICAL: Failed to import necessary modules in TradingEngine: {e}")
    # This path adjustment is a fallback for direct execution.
    # It's better to run the project from the root with `python main.py`.
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    # Retry imports after path adjustment
    from trading_bot.config import settings
    from trading_bot.exchange.binance_client import BinanceFuturesClient
    from trading_bot.core.strategy import Strategy
    from trading_bot.core.market_scanner import get_top_volume_usdt_futures_symbols
    from trading_bot.utils.trade_logger import log_trade
    from trading_bot.utils.notifier import send_telegram_message


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
        self.leverage = settings.LEVERAGE

        # --- State Management ---
        self.state_file_path = settings.STATE_FILE_PATH
        self.open_positions = self._load_state()

        logger.info("TradingEngine initialized with parameters:")
        logger.info(f"  Loop Interval: {self.loop_interval_seconds} seconds")
        logger.info(f"  Symbols to Scan: Top {self.symbols_to_scan_count}")
        logger.info(f"  Min 24h Volume: {self.min_24h_quote_volume:,.0f} USDT")
        logger.info(f"  Max Concurrent Positions: {self.max_concurrent_positions}")
        logger.info(f"  Position Size: {self.position_size_usdt} USDT (nominal)")
        logger.info(f"  Leverage: {self.leverage}x")
        logger.info(f"Engine started. Found and loaded {len(self.open_positions)} existing position(s) from state file.")

    def _load_state(self):
        """Loads open positions from the state file (e.g., open_positions.json)."""
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
        """Saves the current self.open_positions dictionary to the state file."""
        logger.debug(f"Saving current state ({len(self.open_positions)} open positions) to '{self.state_file_path}'...")
        try:
            state_dir = os.path.dirname(self.state_file_path)
            if not os.path.exists(state_dir):
                os.makedirs(state_dir)
            
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
        """Iterates through open positions, checks their status, and handles closure."""
        if not self.open_positions:
            logger.debug("No open positions to manage.")
            return

        logger.info(f"Managing {len(self.open_positions)} open position(s): {list(self.open_positions.keys())}")
        
        symbols_to_process = list(self.open_positions.keys()) 

        for symbol in symbols_to_process:
            if not self.running: break
            
            trade_info = self.open_positions.get(symbol)
            if not trade_info: continue

            logger.debug(f"Checking status for position: {symbol}")

            sl_order_id = trade_info.get("stop_loss_order_id")
            tp_order_id = trade_info.get("take_profit_order_id")
            is_closed = False
            closing_order_data = None
            exit_reason = "UNKNOWN"
            
            sl_order_data = self.client.query_order(symbol, sl_order_id) if sl_order_id else None
            time.sleep(0.2)
            tp_order_data = self.client.query_order(symbol, tp_order_id) if tp_order_id else None

            sl_status = sl_order_data.get('status') if sl_order_data else None
            tp_status = tp_order_data.get('status') if tp_order_data else None

            if sl_status == 'FILLED':
                logger.info(f"STOP-LOSS order {sl_order_id} for {symbol} has been FILLED.")
                closing_order_data, exit_reason = sl_order_data, "STOP_LOSS"
                if tp_order_id: self.client.cancel_order(symbol, tp_order_id)
                is_closed = True
            elif tp_status == 'FILLED':
                logger.info(f"TAKE-PROFIT order {tp_order_id} for {symbol} has been FILLED.")
                closing_order_data, exit_reason = tp_order_data, "TAKE_PROFIT"
                if sl_order_id: self.client.cancel_order(symbol, sl_order_id)
                is_closed = True
            
            elif (sl_order_id and sl_status not in ['NEW', 'PARTIALLY_FILLED']) or \
                 (tp_order_id and tp_status not in ['NEW', 'PARTIALLY_FILLED']):
                logger.warning(f"Protective order(s) for {symbol} are inactive but not FILLED. SL: {sl_status}, TP: {tp_status}. Assuming manual intervention.")
                is_closed = True
                closing_order_data = None 
            
            if is_closed:
                if closing_order_data: 
                    self._handle_trade_closure(symbol, trade_info, closing_order_data, exit_reason)
                
                logger.info(f"Performing final cleanup check for {symbol} to remove any dust.")
                time.sleep(1)
                dust_position_info = self.client.get_position_info(symbol)
                
                if dust_position_info:
                    logger.warning(f"Dust position found for {symbol}. Sending final close order to sweep. Dust: {dust_position_info}")
                    self.client.close_position_market(symbol=symbol, position_side=trade_info['side'])
                
                if symbol in self.open_positions:
                    del self.open_positions[symbol]
                    logger.info(f"Removed processed position {symbol} from active state.")
                    self._save_state()
            else:
                 logger.debug(f"Position for {symbol} is still open. SL Status: {sl_status}, TP Status: {tp_status}")
            time.sleep(1)

    def _handle_trade_closure(self, symbol, entry_trade_info, closing_order, exit_reason):
        """Fetches final PnL and commission and logs the completed trade."""
        logger.info(f"Handling closure of trade for {symbol} due to {exit_reason}.")
        
        closing_order_id = closing_order.get('orderId')
        if not closing_order_id:
            logger.error(f"Could not log trade for {symbol} because closing order ID is missing.")
            return

        closing_trade_details = self.client.get_trades_for_order(symbol, closing_order_id)
        if not closing_trade_details:
            logger.error(f"Could not get closing trade details for order {closing_order_id}. Cannot log PnL.")
            return
            
        net_pnl_usdt = closing_trade_details.get('total_pnl', 0.0)
        exit_commission = closing_trade_details.get('total_commission', 0.0)
        
        entry_price = entry_trade_info.get('entry_price', 0)
        quantity = entry_trade_info.get('quantity', 0)
        side = entry_trade_info.get('side')
        entry_commission = entry_trade_info.get('entry_commission', 0.0)
        total_commission = entry_commission + exit_commission
        
        entry_nominal_value = entry_price * quantity
        pnl_percentage = (net_pnl_usdt / entry_nominal_value) if entry_nominal_value != 0 else 0.0
        
        exit_price = float(closing_order.get('avgPrice', 0))

        logger.info(f"Trade Closed for {symbol}: Net PnL (from API)={net_pnl_usdt:.4f} USDT, Total Commission={total_commission:.6f}")
        
        trade_log_data = {
            'symbol': symbol, 'side': side, 'quantity': quantity, 'entry_price': entry_price,
            'exit_price': exit_price, 'pnl_usdt': net_pnl_usdt, 'pnl_percentage': pnl_percentage,
            'entry_commission': entry_commission, 'exit_commission': exit_commission, 'total_commission': total_commission,
            'entry_reason': entry_trade_info.get('entry_reason', 'N/A'), 'exit_reason': exit_reason
        }
        log_trade(trade_log_data)
        
        pnl_icon = "✅" if net_pnl_usdt >= 0 else "🔻"
        msg = (f"{pnl_icon} **POSITION CLOSED** {pnl_icon}\n\n"
               f"Symbol: `{symbol}`\n"
               f"Side: `{side}` | Exit: `{exit_reason}`\n"
               f"Entry: `{entry_price}` | Exit: `{exit_price}`\n"
               f"**Net PnL: `{net_pnl_usdt:.4f} USDT`**")
        send_telegram_message(msg)

    def _scan_for_new_trades(self):
        """Scans the market and processes symbols for potential new entries."""
        logger.info("Scanning for new trade opportunities...")
        symbols_to_check = get_top_volume_usdt_futures_symbols(
            client=self.client, count=self.symbols_to_scan_count, min_quote_volume=self.min_24h_quote_volume)
        if not symbols_to_check:
            return

        for symbol in symbols_to_check:
            if not self.running or len(self.open_positions) >= self.max_concurrent_positions:
                if len(self.open_positions) >= self.max_concurrent_positions:
                    logger.info("Max concurrent positions reached. Stopping scan for new trades.")
                break 
            
            trade_initiated = self._process_symbol_for_entry(symbol)
            if trade_initiated:
                logger.info(f"A new trade was initiated. Stopping scan for this loop.")
                break
            time.sleep(2)

    def _process_symbol_for_entry(self, symbol):
        """Processes a single symbol for a potential new trade entry."""
        if symbol in self.open_positions:
            logger.debug(f"Already managing an internal position for {symbol}. Skipping.")
            return False

        try:
            exchange_positions = self.client.get_position_info(symbol)
            if exchange_positions:
                logger.warning(f"Found an existing position for {symbol} on the exchange. Skipping to avoid duplicates.")
                return True
        except Exception as e:
            logger.error(f"Could not verify existing position for {symbol}: {e}. Skipping.", exc_info=True)
            return False

        signal_data = self.strategy.generate_signal(symbol)
        signal = signal_data.get("signal") if signal_data else "HOLD"

        if signal == "BUY" or signal == "SELL":
            logger.info(f"Actionable signal '{signal}' received for {symbol}. Preparing to execute trade...")
            return self._execute_trade(symbol, signal_data)
        return False

    def _execute_trade(self, symbol, signal_data):
        """
        Sets leverage, calculates SL/TP from signal, places orders, updates state,
        and sends a detailed Telegram notification.
        """
        side = signal_data.get("signal")
        sl_price = signal_data.get("sl_price")
        tp_price = signal_data.get("tp_price")

        if not all([side, sl_price, tp_price]):
            logger.error(f"Signal for {symbol} is missing critical data (side, sl_price, or tp_price). Aborting trade.")
            return False
            
        try:
            logger.info(f"Setting leverage for {symbol} to {self.leverage}x before placing trade.")
            self.client.set_leverage(symbol=symbol, leverage=self.leverage)
            time.sleep(0.5)
            
            # Since SL/TP prices are pre-calculated by the strategy, we use them directly.
            # The PERCENT_PRICE filter check is still useful as a final safety measure.
            current_price = self.client.get_mark_price(symbol)
            if not current_price:
                logger.error(f"Could not get MARK PRICE for {symbol} to validate SL/TP. Aborting trade.")
                return False

            symbol_info = self.client._get_symbol_info(symbol)
            if not symbol_info:
                 logger.error(f"Could not get symbol info for {symbol}. Cannot validate filters.")
                 return False

            price_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'PERCENT_PRICE'), None)
            if price_filter:
                multiplier_up = float(price_filter['multiplierUp'])
                multiplier_down = float(price_filter['multiplierDown'])
                max_allowed_price = self.client._format_price(symbol, current_price * multiplier_up)
                min_allowed_price = self.client._format_price(symbol, current_price * multiplier_down)
                
                original_tp, original_sl = tp_price, sl_price
                tp_price = max(min(tp_price, max_allowed_price), min_allowed_price)
                sl_price = max(min(sl_price, max_allowed_price), min_allowed_price)

                if tp_price != original_tp: logger.warning(f"TP price for {symbol} adjusted from {original_tp:.4f} to {tp_price:.4f} due to PERCENT_PRICE filter.")
                if sl_price != original_sl: logger.warning(f"SL price for {symbol} adjusted from {original_sl:.4f} to {sl_price:.4f} due to PERCENT_PRICE filter.")
            
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
                    "take_profit_order_id": tp_order.get('orderId') if tp_order else None, "entry_reason": "MTA_EMA_RSI_BB",
                }
                self._save_state()

                # Calculate effective percentages for the notification message
                entry_price_val = self.open_positions[symbol]['entry_price']
                effective_sl_percent = 0.0
                effective_tp_percent = 0.0

                if entry_price_val > 0:
                    if side.upper() == "BUY":
                        effective_sl_percent = abs((entry_price_val - sl_price) / entry_price_val) * 100
                        effective_tp_percent = abs((tp_price - entry_price_val) / entry_price_val) * 100
                    elif side.upper() == "SELL":
                        effective_sl_percent = abs((sl_price - entry_price_val) / entry_price_val) * 100
                        effective_tp_percent = abs((entry_price_val - tp_price) / entry_price_val) * 100

                msg = (f"🚀 **NEW POSITION OPENED** 🚀\n\n"
                       f"`{symbol}` | **{side}**\n\n"
                       f"Entry Price: `{entry_price_val:.4f}`\n"
                       f"Quantity: `{self.open_positions[symbol]['quantity']}`\n\n"
                       f"SL Price: `{sl_price:.4f}` (~{effective_sl_percent:.2f}%)\n"
                       f"TP Price: `{tp_price:.4f}` (~{effective_tp_percent:.2f}%)")
                
                send_telegram_message(msg)
                return True
            else:
                logger.error(f"Failed to open new {side} position for {symbol}. Entry order response: {entry_order}")
                return False
        
        except Exception as e:
            logger.error(f"An error occurred during trade execution for {symbol}: {e}", exc_info=True)
            return False
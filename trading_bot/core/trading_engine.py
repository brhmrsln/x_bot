# trading_bot/core/trading_engine.py
import logging
import time

# Attempt to import settings and logger setup function from the project structure
try:
    from trading_bot.config import settings
    from trading_bot.utils.logger_config import setup_logger
    from trading_bot.core.market_scanner import get_top_volume_usdt_futures_symbols
    from trading_bot.core.strategy import Strategy
    from trading_bot.exchange.binance_client import BinanceFuturesClient

except ImportError:
    # Fallback for direct execution
    import sys
    import os
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root_dir = os.path.abspath(os.path.join(current_script_dir, '..', '..'))
    if project_root_dir not in sys.path:
        sys.path.insert(0, project_root_dir)
    from trading_bot.config import settings
    from trading_bot.utils.logger_config import setup_logger
    from trading_bot.core.market_scanner import get_top_volume_usdt_futures_symbols
    from trading_bot.core.strategy import Strategy
    from trading_bot.exchange.binance_client import BinanceFuturesClient

logger = logging.getLogger("trading_bot")

class TradingEngine:
    def __init__(self, client: BinanceFuturesClient, strategy: Strategy):
        """Initializes the TradingEngine."""
        self.client = client
        self.strategy = strategy
        self.running = False
        
        # --- Load configurable parameters from settings ---
        self.loop_interval_seconds = int(getattr(settings, 'ENGINE_LOOP_INTERVAL_SECONDS', 300))
        self.symbols_to_scan_count = int(getattr(settings, 'SCAN_TOP_N_SYMBOLS', 20))
        self.min_24h_quote_volume = float(getattr(settings, 'MIN_24H_QUOTE_VOLUME', 50000000))
        self.max_concurrent_positions = int(getattr(settings, 'MAX_CONCURRENT_POSITIONS', 1))
        self.position_size_usdt = float(getattr(settings, 'POSITION_SIZE_USDT', 1000))
        self.sl_percentage = float(getattr(settings, 'STOP_LOSS_PERCENTAGE', 0.01))
        self.tp_percentage = float(getattr(settings, 'TAKE_PROFIT_PERCENTAGE', 0.02))

        # --- State Management: Dictionary to hold details of open positions ---
        # Key: symbol (str), Value: trade_info (dict)
        self.open_positions = {} 
        # Example trade_info:
        # { "side": "LONG", "quantity": 0.01, "entry_price": 50000, "entry_order_id": 12345, 
        #   "stop_loss_order_id": 12346, "take_profit_order_id": 12347, "entry_reason": "EMA_CROSSOVER" }
        
        logger.info("TradingEngine initialized with parameters:")
        # ... (Önceki __init__ içindeki logger.info'lar aynı kalabilir)

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
                
                # 1. Manage existing open positions (check for SL/TP hits)
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
        """
        Iterates through open positions, checks the status of their SL/TP orders,
        and handles closure if an order is FILLED or becomes inactive (e.g., CANCELED).
        """
        if not self.open_positions:
            logger.debug("No open positions to manage.")
            return

        logger.info(f"Managing {len(self.open_positions)} open position(s): {list(self.open_positions.keys())}")
        
        symbols_to_remove_from_state = [] # To collect symbols of trades that are no longer active

        for symbol, trade_info in self.open_positions.items():
            if not self.running: break
            
            logger.debug(f"Checking status for position: {symbol}")

            sl_order_id = trade_info.get("stop_loss_order_id")
            tp_order_id = trade_info.get("take_profit_order_id")
            
            is_closed_by_fill = False

            # Check Stop-Loss Order Status
            if sl_order_id:
                sl_order = self.client.query_order(symbol, sl_order_id)
                if sl_order and sl_order.get('status') == 'FILLED':
                    logger.info(f"STOP-LOSS order {sl_order_id} for {symbol} has been FILLED.")
                    self._handle_trade_closure(symbol, trade_info, sl_order, "STOP_LOSS")
                    if tp_order_id: self.client.cancel_order(symbol, tp_order_id)
                    symbols_to_remove_from_state.append(symbol)
                    is_closed_by_fill = True
                elif sl_order and sl_order.get('status') not in ['NEW', 'PARTIALLY_FILLED']:
                    # If SL order is CANCELED, EXPIRED, REJECTED etc., the position is unprotected.
                    logger.warning(f"Stop-Loss order {sl_order_id} for {symbol} is no longer active (Status: {sl_order.get('status')}). "
                                   "Assuming position is compromised or manually closed. Removing from active state.")
                    if tp_order_id: self.client.cancel_order(symbol, tp_order_id) # Cancel the TP order as well
                    symbols_to_remove_from_state.append(symbol)
                    continue # Skip to the next symbol in the loop

            # Check Take-Profit Order Status (only if not already closed by SL)
            if not is_closed_by_fill and tp_order_id:
                tp_order = self.client.query_order(symbol, tp_order_id)
                if tp_order and tp_order.get('status') == 'FILLED':
                    logger.info(f"TAKE-PROFIT order {tp_order_id} for {symbol} has been FILLED.")
                    self._handle_trade_closure(symbol, trade_info, tp_order, "TAKE_PROFIT")
                    if sl_order_id: self.client.cancel_order(symbol, sl_order_id)
                    symbols_to_remove_from_state.append(symbol)
                elif tp_order and tp_order.get('status') not in ['NEW', 'PARTIALLY_FILLED']:
                    logger.warning(f"Take-Profit order {tp_order_id} for {symbol} is no longer active (Status: {tp_order.get('status')}). "
                                   "Assuming position is compromised or manually closed. Removing from active state.")
                    if sl_order_id: self.client.cancel_order(symbol, sl_order_id) # Cancel the SL order as well
                    symbols_to_remove_from_state.append(symbol)
            
            time.sleep(1) 

        # Remove closed or compromised positions from our state dictionary outside the loop
        if symbols_to_remove_from_state:
            for symbol in set(symbols_to_remove_from_state): # Use set to handle unique symbols
                if symbol in self.open_positions:
                    del self.open_positions[symbol]
                    logger.info(f"Removed processed position {symbol} from active state.")

    def _handle_trade_closure(self, symbol, entry_trade_info, closing_order, exit_reason):
        """Calculates PnL and logs the completed trade to the CSV file."""
        logger.info(f"Handling closure of trade for {symbol} due to {exit_reason}.")
        
        exit_price = float(closing_order.get('avgPrice', 0))
        entry_price = entry_trade_info.get('entry_price', 0)
        quantity = entry_trade_info.get('quantity', 0)
        side = entry_trade_info.get('side')

        if exit_price == 0 or entry_price == 0 or quantity == 0:
            logger.error(f"Could not calculate PnL for {symbol} due to missing data "
                         f"(exit_price={exit_price}, entry_price={entry_price}, quantity={quantity}).")
            return
            
        pnl_usdt = 0.0
        pnl_percentage = 0.0
        entry_nominal_value = entry_price * quantity
        
        if side.upper() == "LONG":
            pnl_usdt = (exit_price - entry_price) * quantity
        elif side.upper() == "SHORT":
            pnl_usdt = (entry_price - exit_price) * quantity

        if entry_nominal_value != 0:
            pnl_percentage = pnl_usdt / entry_nominal_value
        
        logger.info(f"Trade Closed for {symbol}: PnL = {pnl_usdt:.4f} USDT, PnL% = {pnl_percentage*100:.2f}%")
        
        trade_log_data = {
            'symbol': symbol, 'side': side, 'quantity': quantity, 'entry_price': entry_price,
            'exit_price': exit_price, 'pnl_usdt': pnl_usdt, 'pnl_percentage': pnl_percentage,
            'entry_reason': entry_trade_info.get('entry_reason', 'N/A'), 'exit_reason': exit_reason
        }
        log_trade(trade_log_data) # Call the function from our trade_logger module
    
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
                logger.info("Max concurrent positions reached during scan. Stopping scan for new trades.")
                break 
            
            logger.debug(f"Checking signal for symbol: {symbol}")
            self._process_symbol_for_entry(symbol)
            time.sleep(2)

    def _process_symbol_for_entry(self, symbol):
        """Processes a single symbol for a potential new trade entry."""
        if symbol in self.open_positions:
            logger.debug(f"Already managing a position for {symbol}. Skipping for new entry signal.")
            return

        signal = self.strategy.generate_signal(symbol)
        if signal == "BUY" or signal == "SELL":
            logger.info(f"Actionable signal '{signal}' received for {symbol}. Preparing to execute trade...")
            self._execute_trade(symbol, signal)

    def _execute_trade(self, symbol, side):
        """Executes a new trade by placing a market order with SL/TP."""
        try:
            current_price = self.client.get_ticker_price(symbol)
            if not current_price:
                logger.error(f"Could not get price for {symbol}. Cannot execute trade.")
                return

            if side.upper() == "BUY":
                sl_price = current_price * (1 - self.sl_percentage)
                tp_price = current_price * (1 + self.tp_percentage)
            elif side.upper() == "SELL":
                sl_price = current_price * (1 + self.sl_percentage)
                tp_price = current_price * (1 - self.tp_percentage)
            else: return

            entry_order, stop_order, tp_order = self.client.open_position_market_with_sl_tp(
                symbol=symbol, order_side=side, position_size_usdt=self.position_size_usdt,
                stop_loss_price=sl_price, take_profit_price=tp_price)

            if entry_order and entry_order.get('status') == 'FILLED':
                logger.info(f"Successfully opened new {side} position for {symbol}. Updating internal state.")
                self.open_positions[symbol] = {
                    "side": side,
                    "quantity": float(entry_order.get('executedQty')),
                    "entry_price": float(entry_order.get('avgPrice')),
                    "entry_order_id": entry_order.get('orderId'),
                    "stop_loss_order_id": stop_order.get('orderId') if stop_order else None,
                    "take_profit_order_id": tp_order.get('orderId') if tp_order else None,
                    "entry_reason": "EMA_CROSSOVER", # Example reason, can be made dynamic
                }
            else:
                logger.error(f"Failed to open new {side} position for {symbol}. Entry order response: {entry_order}")
        
        except Exception as e:
            logger.error(f"An error occurred during trade execution for {symbol}: {e}", exc_info=True)
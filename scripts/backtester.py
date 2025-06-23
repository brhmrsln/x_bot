# scripts/backtester.py
import pandas as pd
import os
import sys
import logging
import argparse
from datetime import datetime

# --- Path Setup ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- Imports from our project ---
from trading_bot.config import settings
from x_bot.trading_bot.core.mean_reversion_strategy import Strategy 
from trading_bot.utils.logger_config import setup_logger

# --- Backtester Configuration ---
INITIAL_CAPITAL = 10000.0
TAKER_FEE = 0.0005
logger = setup_logger(name="backtester")

class MockClient:
    """A fake client that serves historical data to the Strategy class."""
    def __init__(self, ltf_df=None, htf_df=None):
        self._ltf_data = ltf_df
        self._htf_data = htf_df
        self.current_index = 0

    def get_historical_klines(self, symbol, interval, limit):
        source_df = None
        if interval == settings.MTA_KLINE_INTERVAL:
            source_df = self._htf_data
        elif interval == settings.STRATEGY_KLINE_INTERVAL:
            source_df = self._ltf_data
        
        if source_df is None: return []
        
        end_time = self._ltf_data.index[self.current_index]
        relevant_data = source_df[source_df.index <= end_time]
        data_slice = relevant_data.tail(limit).reset_index()
        data_slice['open_time'] = (data_slice['open_time'].astype('int64') / 1_000_000).astype('int64')
        return data_slice.values.tolist()

    def set_current_index(self, index):
        self.current_index = index

def report_results(trade_history, initial_capital, final_capital, df, peak_equity, max_drawdown):
    """Calculates and logs the backtest performance report."""
    logger.info("="*50)
    logger.info("Backtest Finished. Performance Report:")
    logger.info("="*50)
    if not trade_history:
        logger.warning("No trades were executed during the backtest.")
        logger.info("="*50)
        return

    df_trades = pd.DataFrame(trade_history)
    total_trades = len(df_trades)
    winning_trades = df_trades[df_trades['pnl'] > 0]
    losing_trades = df_trades[df_trades['pnl'] <= 0]
    win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0
    total_net_pnl = final_capital - initial_capital
    avg_win = winning_trades['pnl'].mean() if not winning_trades.empty else 0
    avg_loss = losing_trades['pnl'].mean() if not losing_trades.empty else 0
    gross_profits = winning_trades['pnl'].sum()
    gross_losses = losing_trades['pnl'].sum()
    profit_factor = abs(gross_profits / gross_losses) if gross_losses != 0 else float('inf')
    max_drawdown_percent = (max_drawdown / peak_equity) * 100 if peak_equity > 0 else 0

    logger.info(f"Period Tested: {df.index[0]} -> {df.index[-1]}")
    logger.info(f"Initial Capital: ${initial_capital:,.2f}")
    logger.info(f"Final Capital:   ${final_capital:,.2f}")
    logger.info(f"Peak Capital:    ${peak_equity:,.2f}")
    logger.info(f"Total Net PnL:   ${total_net_pnl:,.2f} ({(total_net_pnl/initial_capital):.2%})")
    logger.info(f"Max Drawdown:    $-{max_drawdown:,.2f} ({max_drawdown_percent:.2f}%)")
    logger.info("-"*50)
    logger.info(f"Total Trades Executed: {total_trades}")
    logger.info(f"Win Rate: {win_rate:.2f}%")
    logger.info(f"Profit Factor: {profit_factor:.2f}")
    logger.info(f"Average Winning Trade:  ${avg_win:,.2f}")
    logger.info(f"Average Losing Trade: ${avg_loss:,.2f}")
    logger.info("="*50)

def run_backtest(ltf_data_path: str, htf_data_path: str, capital: float):
    """Orchestrates the backtest using the real Strategy class."""
    log_dir = os.path.join(project_root, "logs")
    base_name = os.path.basename(ltf_data_path).split('_15m_')[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"backtest_report_{base_name}_{timestamp}.log"
    report_filepath = os.path.join(log_dir, report_filename)
    os.makedirs(log_dir, exist_ok=True)
    
    report_file_handler = logging.FileHandler(report_filepath)
    report_formatter = logging.Formatter('%(asctime)s - %(levelname)-8s - %(message)s')
    report_file_handler.setFormatter(report_formatter)
    logger.addHandler(report_file_handler)

    try:
        logger.info("="*50)
        logger.info(f"Starting High-Fidelity Backtest for Pullback to Trend Strategy...")
        logger.info(f"Initial Capital: ${capital:,.2f}")
        logger.info(f"LTF Data: {os.path.basename(ltf_data_path)}")
        logger.info(f"HTF Data: {os.path.basename(htf_data_path)}")
        logger.info("="*50)

        df_ltf = pd.read_csv(ltf_data_path, index_col='open_time', parse_dates=True)
        df_htf = pd.read_csv(htf_data_path, index_col='open_time', parse_dates=True)
        logger.info(f"Loaded {len(df_ltf)} LTF klines and {len(df_htf)} HTF klines.")
        
        mock_client = MockClient(ltf_df=df_ltf, htf_df=df_htf)
        strategy_params = {
            "mta_kline_interval": settings.MTA_KLINE_INTERVAL, "mta_ema_period": settings.MTA_EMA_PERIOD,
            "kline_interval": settings.STRATEGY_KLINE_INTERVAL, "kline_limit": settings.STRATEGY_KLINE_LIMIT,
            "ema_period": settings.STRATEGY_EMA_PERIOD, "risk_atr_period": settings.RISK_ATR_PERIOD
        }
        strategy = Strategy(client=mock_client, strategy_params=strategy_params)
        
        cash, position, trade_history = capital, None, []
        peak_equity, max_drawdown = capital, 0.0

        logger.info("Starting simulation loop...")
        start_index = settings.STRATEGY_KLINE_LIMIT
        for i in range(start_index, len(df_ltf)):
            mock_client.set_current_index(i)
            current_candle = df_ltf.iloc[i]
            
            if position:
                is_closed = False
                exit_price = 0.0
                exit_reason = "UNKNOWN"
                
                if position['side'] == 'LONG':
                    if current_candle['low'] <= position['sl_price']:
                        is_closed = True
                        exit_price = position['sl_price']
                        exit_reason = "STOP_LOSS"
                    elif current_candle['high'] >= position['tp_price']:
                        is_closed = True
                        exit_price = position['tp_price']
                        exit_reason = "TAKE_PROFIT"
                elif position['side'] == 'SHORT':
                    if current_candle['high'] >= position['sl_price']:
                        is_closed = True
                        exit_price = position['sl_price']
                        exit_reason = "STOP_LOSS"
                    elif current_candle['low'] <= position['tp_price']:
                        is_closed = True
                        exit_price = position['tp_price']
                        exit_reason = "TAKE_PROFIT"
                
                if is_closed:
                    gross_pnl = (exit_price - position['entry_price']) * position['quantity'] if position['side'] == 'LONG' else (position['entry_price'] - exit_price) * position['quantity']
                    exit_commission = abs(exit_price * position['quantity']) * TAKER_FEE
                    net_pnl = gross_pnl - position['entry_commission'] - exit_commission
                    cash += net_pnl
                    
                    logger.info(f"[{current_candle.name}] CLOSE {position['side']} at {exit_price:.5f}. Net PnL: {net_pnl:.2f}. Cash: ${cash:,.2f}")
                    
                    trade_history.append({"pnl": net_pnl, "exit_time": current_candle.name, "entry_time": position['entry_time']})
                    position = None
                    
                    peak_equity = max(peak_equity, cash)
                    max_drawdown = max(max_drawdown, peak_equity - cash)
            
            if position is None:
                symbol = os.path.basename(ltf_data_path).split('_')[0]
                signal_data = strategy.generate_signal(symbol)
                if signal_data and signal_data.get("signal") in ["BUY", "SELL"]:
                    side = signal_data.get("signal")
                    trigger_candle = signal_data.get("trigger_candle")
                    risk_atr = signal_data.get("risk_atr")
                    entry_price = current_candle['open']
                    quantity = (settings.POSITION_SIZE_USDT / entry_price)
                    entry_commission = (entry_price * quantity) * TAKER_FEE
                    cash -= entry_commission
                    
                    if side == "BUY":
                        sl_price = trigger_candle['low'] - (risk_atr * settings.SL_ATR_MULTIPLIER)
                        tp_price = entry_price + ((entry_price - sl_price) * settings.RISK_REWARD_RATIO)
                    else: # SELL
                        sl_price = trigger_candle['high'] + (risk_atr * settings.SL_ATR_MULTIPLIER)
                        tp_price = entry_price - ((sl_price - entry_price) * settings.RISK_REWARD_RATIO)

                    position = {"side": side, "entry_price": entry_price, "quantity": quantity, "sl_price": sl_price, "tp_price": tp_price, "entry_time": current_candle.name, "entry_commission": entry_commission}
                    logger.info(f"[{current_candle.name}] OPEN {side} at {entry_price:.5f} | SL: {sl_price:.5f}, TP: {tp_price:.5f}")

        report_results(trade_history, capital, cash, df_ltf, peak_equity, max_drawdown)
    
    finally:
        logger.removeHandler(report_file_handler)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="A high-fidelity backtester for MTA strategies.")
    parser.add_argument('--ltf-datafile', required=True, help="Path to the Lower Timeframe kline data CSV (e.g., 15m).")
    parser.add_argument('--htf-datafile', required=True, help="Path to the Higher Timeframe kline data CSV (e.g., 1h).")
    parser.add_argument('--capital', type=float, default=INITIAL_CAPITAL, help=f"Initial capital (default: {INITIAL_CAPITAL}).")
    args = parser.parse_args()
    
    run_backtest(ltf_data_path=args.ltf_datafile, htf_data_path=args.htf_datafile, capital=args.capital)
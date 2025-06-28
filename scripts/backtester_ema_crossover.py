# scripts/backtester_ema_crossover.py (A dedicated script for the Simple EMA Crossover strategy)

import pandas as pd
import argparse
import logging
import sys
import os
from tqdm import tqdm
from datetime import datetime

# --- Project Root Setup ---
# This allows the script to be run from anywhere within the project.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- Project Module Imports ---
from trading_bot.config import settings
from trading_bot.core.simple_ema_crossover_strategy import SimpleEmaCrossoverStrategy

# --- Logger Configuration ---
def setup_logger(debug=False):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)
    return logging.getLogger("EmaCrossoverBacktester")

def run_backtest(args, logger):
    """
    Executes the backtest for the Simple EMA Crossover strategy.
    """
    # 1. Load Strategy and Parameters (Directly)
    try:
        strategy_class = SimpleEmaCrossoverStrategy
        required_params_map = strategy_class.get_required_parameters()
        strategy_params = {key: getattr(settings, name) for key, name in required_params_map.items()}
        strategy = strategy_class(strategy_params)
        logger.info(f"Strategy 'SimpleEmaCrossoverStrategy' loaded successfully.")
        logger.info(f"Strategy Parameters Used: {strategy_params}")
    except (ValueError, AttributeError) as e:
        logger.error(f"Failed to load strategy: {e}")
        return [], args.capital, args.capital, 0

    # 2. Load Data
    try:
        df = pd.read_csv(args.datafile)
        df['open_time_dt'] = pd.to_datetime(df['open_time'], unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        logger.info(f"Data loaded successfully: {args.datafile}")
    except FileNotFoundError as e:
        logger.error(f"Data file not found: {e}")
        return [], args.capital, args.capital, 0

    # 3. Initialize Backtest Variables
    capital = args.capital
    peak_equity = capital
    max_drawdown = 0.0
    position = None
    trades = []
    indicator_warmup_period = 200 # Number of initial candles to skip for indicator warmup

    logger.info("Starting backtest...")
    iterator = tqdm(range(indicator_warmup_period, len(df)), desc="Backtesting EMA Crossover")
    
    for i in iterator:
        # Check for SL/TP if a position is open
        if position:
            current_candle = df.iloc[i]
            pnl, trade_closed, exit_price, exit_reason = 0, False, 0, "UNKNOWN"
            
            if position['side'] == 'LONG':
                if current_candle['low'] <= position['sl']: trade_closed, exit_price, exit_reason = True, position['sl'], "STOP_LOSS"
                elif current_candle['high'] >= position['tp']: trade_closed, exit_price, exit_reason = True, position['tp'], "TAKE_PROFIT"
            elif position['side'] == 'SHORT':
                if current_candle['high'] >= position['sl']: trade_closed, exit_price, exit_reason = True, position['sl'], "STOP_LOSS"
                elif current_candle['low'] <= position['tp']: trade_closed, exit_price, exit_reason = True, position['tp'], "TAKE_PROFIT"
            
            if trade_closed:
                pnl = ((exit_price - position['entry_price']) * position['amount']) if position['side'] == 'LONG' else ((position['entry_price'] - exit_price) * position['amount'])
                capital -= (args.positionsize * args.fee) # Subtract closing fee
                capital += pnl
                
                peak_equity = max(peak_equity, capital)
                max_drawdown = max(max_drawdown, peak_equity - capital)
                
                trade_duration = current_candle['open_time_dt'] - position['entry_time']
                
                trade_log = {
                    'capital_before_trade': position['capital_before_trade'],
                    'capital_after_trade': capital,
                    'entry_time': position['entry_time'],
                    'exit_time': current_candle['open_time_dt'],
                    'duration': str(trade_duration),
                    'side': position['side'],
                    'entry_price': position['entry_price'],
                    'exit_price': exit_price,
                    'stop_loss': position['sl'],
                    'take_profit': position['tp'],
                    'pnl_usd': pnl,
                    'exit_reason': exit_reason,
                    'position_size_usd': args.positionsize,
                    'leverage': args.leverage
                }
                trade_log.update(position['entry_indicators'])
                trades.append(trade_log)
                
                position = None

        # Check for new signal if no position is open
        if not position:
            historical_data = df.iloc[i - indicator_warmup_period : i].copy()
            signal, sl, tp = strategy.generate_signal(historical_data)

            if signal in ['BUY', 'SELL']:
                capital_before_trade = capital
                
                entry_price = df.iloc[i]['open']
                
                entry_indicators = {}
                last_indicator_candle = historical_data.iloc[-1]
                for col in last_indicator_candle.index:
                    if col.upper().startswith(('EMA', 'ATR')):
                        entry_indicators[col] = last_indicator_candle[col]
                
                position = {
                    'capital_before_trade': capital_before_trade,
                    'entry_time': df.iloc[i]['open_time_dt'],
                    'side': 'LONG' if signal == 'BUY' else 'SHORT',
                    'entry_price': entry_price,
                    'amount': (args.positionsize * args.leverage) / entry_price,
                    'sl': sl, 
                    'tp': tp,
                    'entry_indicators': entry_indicators
                }
                capital -= (args.positionsize * args.fee) # Subtract opening fee

    return trades, capital, peak_equity, max_drawdown

def save_detailed_trade_log(trades, args):
    """Saves a detailed CSV log of all executed trades."""
    if not trades: return
    
    log_df = pd.DataFrame(trades)
    
    desired_order = [
        'capital_before_trade', 'capital_after_trade', 'pnl_usd', 'entry_time', 'exit_time', 'duration', 
        'side', 'entry_price', 'exit_price', 'stop_loss', 'take_profit', 'exit_reason',
        'position_size_usd', 'leverage'
    ]
    indicator_cols = [col for col in log_df.columns if col not in desired_order]
    final_order = desired_order + indicator_cols
    log_df = log_df[final_order]

    data_dir = os.path.join(project_root, "data")
    os.makedirs(data_dir, exist_ok=True)
    symbol = os.path.basename(args.datafile).split('_')[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"trade_log_{symbol}_ema_crossover_{timestamp}.csv"
    log_filepath = os.path.join(data_dir, log_filename)
    try:
        log_df.to_csv(log_filepath, index=False, float_format='%.5f')
        print(f"\nDetailed trade log saved successfully: {log_filepath}")
    except Exception as e:
        print(f"\nError saving detailed trade log: {e}")

def analyze_and_report(trades, initial_capital, final_capital, peak_equity, max_drawdown, args):
    """Analyzes backtest results and reports them to the console and a file."""
    report_lines = []
    report_lines.append("\n" + "="*50)
    report_lines.append(f" " * 10 + f"BACKTEST RESULTS (Simple EMA Crossover)")
    report_lines.append("="*50)
    
    if not trades:
        report_lines.append("NO TRADES WERE EXECUTED during the test period.")
        report_lines.append("Strategy parameters might be too strict for this dataset.")
    else:
        df_trades = pd.DataFrame(trades)
        total_trades = len(df_trades)
        winning_trades = df_trades[df_trades['pnl_usd'] > 0]
        losing_trades = df_trades[df_trades['pnl_usd'] <= 0]
        win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0
        total_pnl = df_trades['pnl_usd'].sum()
        avg_win = winning_trades['pnl_usd'].mean() if len(winning_trades) > 0 else 0
        avg_loss = losing_trades['pnl_usd'].mean() if len(losing_trades) > 0 else 0
        gross_profits = winning_trades['pnl_usd'].sum()
        gross_losses = abs(losing_trades['pnl_usd'].sum())
        profit_factor = gross_profits / gross_losses if gross_losses != 0 else float('inf')
        max_drawdown_percent = (max_drawdown / peak_equity) * 100 if peak_equity > 0 else 0

        report_lines.append(f"Initial Capital:      {initial_capital:,.2f} USDT")
        report_lines.append(f"Ending Capital:       {final_capital:,.2f} USDT")
        report_lines.append(f"Peak Equity:          {peak_equity:,.2f} USDT")
        report_lines.append(f"Total Net PnL:        {total_pnl:,.2f} USDT ({(total_pnl/initial_capital)*100:.2f}%)")
        report_lines.append(f"Max Drawdown (DD):    {max_drawdown:,.2f} USDT ({max_drawdown_percent:.2f}%)")
        report_lines.append("-"*50)
        report_lines.append(f"Total Trades:         {total_trades}")
        report_lines.append(f"Win Rate:             {win_rate:.2f}%")
        report_lines.append(f"Profit Factor:        {profit_factor:.2f}")
        report_lines.append(f"Average Winning Trade: {avg_win:,.2f} USDT")
        report_lines.append(f"Average Losing Trade:  {avg_loss:,.2f} USDT")

    report_lines.append("="*50)
    report_string = "\n".join(report_lines)
    print(report_string)
    
    # Save the summary report to a file
    log_dir = os.path.join(project_root, "logs")
    os.makedirs(log_dir, exist_ok=True)
    symbol = os.path.basename(args.datafile).split('_')[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"backtest_report_{symbol}_ema_crossover_{timestamp}.log"
    report_filepath = os.path.join(log_dir, report_filename)
    
    try:
        with open(report_filepath, 'w') as f:
            f.write(f"Command: python {' '.join(sys.argv)}\n")
            f.write(report_string)
        print(f"\nBacktest report saved successfully: {report_filepath}")
    except Exception as e:
        print(f"\nError saving backtest report: {e}")

    save_detailed_trade_log(trades, args)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="A dedicated backtester for the Simple EMA Crossover strategy.")
    parser.add_argument('--datafile', required=True, help="Path to the kline data CSV file.")
    parser.add_argument('--capital', type=float, default=1000, help="Initial capital in USDT.")
    parser.add_argument('--positionsize', type=float, default=1000, help="Base size of each position in USDT (before leverage).")
    parser.add_argument('--leverage', type=int, default=10, help="Leverage to use.")
    parser.add_argument('--fee', type=float, default=0.0004, help="Taker fee rate (e.g., 0.0004 for 0.04%).")
    parser.add_argument('--debug', action='store_true', help="Enable detailed debug logging.")
    args = parser.parse_args()
    
    logger = setup_logger(args.debug)
    results, final_capital, peak, mdd = run_backtest(args, logger)
    
    analyze_and_report(results, args.capital, final_capital, peak, mdd, args)
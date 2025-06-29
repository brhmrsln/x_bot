# scripts/optimizer_ema_crossover.py (Daha akıllı raporlama eklendi)

import pandas as pd
import argparse
import logging
import sys
import os
import itertools
from tqdm import tqdm
from datetime import datetime

# --- Gerekli Dosyaların Yollarını Ayarlama ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- İlgili Modülleri İçe Aktarma ---
from scripts.backtester_ema_crossover import run_backtest
from trading_bot.config import settings

# --- Logger Yapılandırması ---
def setup_logger(debug=False):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', stream=sys.stdout)
    return logging.getLogger("Optimizer")

def run_optimization(args):
    main_logger = setup_logger(args.debug)
    main_logger.info("Optimization process started. This may take a long time...")
    
    # --- Test edilecek parametre aralıkları ---
    param_grid = {
        'fast_ema': range(5, 25, 3),
        'slow_ema': range(21, 61, 5),
        'atr_sl': [1.0, 1.5, 2.0, 2.5],
        'atr_tp': [1.5, 2.0, 3.0, 4.0]
    }
    
    keys, values = zip(*param_grid.items())
    combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
    
    main_logger.info(f"Total combinations to test: {len(combinations)}")
    
    results = []
    
    backtest_logger = logging.getLogger("Backtester")
    backtest_logger.propagate = False

    for params in tqdm(combinations, desc="Optimizing Parameters"):
        if params['slow_ema'] <= params['fast_ema']:
            continue

        tqdm.write(f"--- Testing parameters: {params} ---")

        # Gerekli parametreleri Namespace objesine ata
        test_args_dict = args.__dict__.copy()
        test_args_dict.update({
            "CROSSOVER_FAST_EMA_PERIOD": params['fast_ema'],
            "CROSSOVER_SLOW_EMA_PERIOD": params['slow_ema'],
            "CROSSOVER_ATR_PERIOD": 14,
            "CROSSOVER_ATR_SL_MULTIPLIER": params['atr_sl'],
            "CROSSOVER_ATR_TP_MULTIPLIER": params['atr_tp']
        })
        test_args = argparse.Namespace(**test_args_dict)

        trades, final_capital, peak_equity, max_drawdown = run_backtest(test_args, backtest_logger)
        
        if trades:
            df_trades = pd.DataFrame(trades)
            total_pnl = df_trades['pnl_usd'].sum()
            gross_profits = df_trades[df_trades['pnl_usd'] > 0]['pnl_usd'].sum()
            gross_losses = abs(df_trades[df_trades['pnl_usd'] < 0]['pnl_usd'].sum())
            profit_factor = gross_profits / gross_losses if gross_losses > 0 else float('inf')
            
            results.append({
                'params': params,
                'profit_factor': profit_factor,
                'net_pnl': total_pnl,
                'trade_count': len(trades)
            })

    # --- RAPORLAMA BÖLÜMÜ GÜNCELLENDİ ---

    # 1. Rapor: Profit Factor'e göre en iyi sonuçlar (Genel Bakış)
    sorted_by_pf = sorted(results, key=lambda x: x['profit_factor'], reverse=True)
    main_logger.info("\n" + "="*80)
    main_logger.info("OPTIMIZATION FINISHED - TOP 10 RESULTS (SORTED BY PROFIT FACTOR)")
    main_logger.info("="*80)
    for i, res in enumerate(sorted_by_pf[:10]):
        main_logger.info(
            f"Rank #{i+1}: "
            f"Profit Factor: {res['profit_factor']:.2f}, "
            f"Net PnL: ${res['net_pnl']:.2f}, "
            f"Trades: {res['trade_count']}, "
            f"Params: {res['params']}"
        )
    
    # 2. Rapor: Yeterli işlem sayısı olanlar arasında Net PnL'e göre en iyiler (DAHA ANLAMLI)
    MIN_TRADES_THRESHOLD = 50  # İstatistiksel anlamlılık için minimum işlem sayısı
    meaningful_results = [res for res in results if res['trade_count'] >= MIN_TRADES_THRESHOLD]
    
    if meaningful_results:
        sorted_by_pnl = sorted(meaningful_results, key=lambda x: x['net_pnl'], reverse=True)
        main_logger.info("\n" + "="*80)
        main_logger.info(f"TOP 10 RELIABLE RESULTS (Trades >= {MIN_TRADES_THRESHOLD}, SORTED BY NET PNL)")
        main_logger.info("="*80)
        for i, res in enumerate(sorted_by_pnl[:10]):
            main_logger.info(
                f"Rank #{i+1}: "
                f"Net PnL: ${res['net_pnl']:.2f}, "
                f"Profit Factor: {res['profit_factor']:.2f}, "
                f"Trades: {res['trade_count']}, "
                f"Params: {res['params']}"
            )
    else:
        main_logger.warning(f"No parameter combination resulted in more than {MIN_TRADES_THRESHOLD} trades.")

    main_logger.info("="*80)

if __name__ == '__main__':
    # ... (argparse bölümü aynı) ...
    parser = argparse.ArgumentParser(description="Parameter optimizer for the Simple EMA Crossover strategy.")
    parser.add_argument('--datafile', required=True, help="Path to the kline data CSV file.")
    parser.add_argument('--capital', type=float, default=1000)
    parser.add_argument('--positionsize', type=float, default=200)
    parser.add_argument('--leverage', type=int, default=10)
    parser.add_argument('--fee', type=float, default=0.0004)
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    
    run_optimization(args)
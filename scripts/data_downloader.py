# scripts/data_downloader.py 
import os, sys, pandas as pd, time, argparse, logging
from datetime import datetime, timedelta, timezone
from binance.um_futures import UMFutures
from binance.error import ClientError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)-8s - %(message)s')
logger = logging.getLogger("data_downloader")

def save_data(df, symbol, interval, data_type, start_date_str):
    if df is None or df.empty:
        logger.warning(f"No data downloaded for {symbol} {data_type}.")
        return
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    data_dir = os.path.join(project_root, 'data')
    os.makedirs(data_dir, exist_ok=True)
    filename = f"{symbol}_{interval if interval else ''}_{data_type}_{start_date_str}.csv".replace('__','_')
    filepath = os.path.join(data_dir, filename)
    df.to_csv(filepath, index=False)
    logger.info(f"\nSuccessfully downloaded and saved {len(df)} records to: {filepath}")

def _fetch_with_retry(fetch_function, params):
    try:
        return fetch_function(**params)
    except ClientError as e:
        if e.error_code == -1130:
            logger.error(f"FATAL: Invalid parameter in request: {e.error_message}. Halting.")
            return "STOP"
        logger.warning(f"Client error: {e}. Retrying...")
        time.sleep(5)
    except Exception as e:
        logger.warning(f"Generic error: {e}. Retrying...")
        time.sleep(5)
    return None

def download_klines(client, symbol, interval, start_ts, end_ts):
    all_data = []
    current_start_ts = start_ts
    while True:
        logger.info(f"Fetching klines starting from {datetime.fromtimestamp(current_start_ts/1000, tz=timezone.utc)}...")
        params = {"symbol": symbol, "interval": interval, "startTime": current_start_ts, "endTime": end_ts, "limit": 1500}
        chunk = _fetch_with_retry(client.klines, params)
        if chunk == "STOP" or not chunk: break
        all_data.extend(chunk)
        last_timestamp = chunk[-1][6]
        if last_timestamp >= current_start_ts: current_start_ts = last_timestamp + 1
        else: logger.error("Timestamp did not advance. Halting."); break
        if end_ts and current_start_ts > end_ts: break
        time.sleep(0.5)
    
    df = pd.DataFrame(all_data, columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df.drop_duplicates(subset='open_time', keep='first', inplace=True)
    return df

def download_open_interest(client, symbol, interval, start_date_str, end_date_str=None):
    limit_days = 29
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=limit_days)
    start_date_obj = datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if start_date_obj < thirty_days_ago:
        logger.warning(f"OI data is only available for the last {limit_days} days. Adjusting start date.")
        start_date_obj = thirty_days_ago
    start_ts = int(start_date_obj.timestamp() * 1000)
    end_ts = int(datetime.strptime(end_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000) if end_date_str else None
    all_data, current_start_ts = [], start_ts
    while True:
        logger.info(f"Fetching OI chunk starting from {datetime.fromtimestamp(current_start_ts/1000, tz=timezone.utc)}...")
        params = {"symbol": symbol, "period": interval, "startTime": current_start_ts, "endTime": end_ts, "limit": 500}
        chunk = _fetch_with_retry(client.open_interest_hist, params)
        if chunk == "STOP" or not chunk: break
        all_data.extend(chunk)
        last_timestamp = chunk[-1]['timestamp']
        if last_timestamp >= current_start_ts: current_start_ts = last_timestamp + 1
        else: logger.error("Timestamp did not advance. Halting."); break
        if end_ts and current_start_ts > end_ts: break
        time.sleep(0.5)
    df = pd.DataFrame(all_data)
    if not df.empty:
        df.rename(columns={'timestamp': 'open_time', 'sumOpenInterestValue': 'oi_value'}, inplace=True)
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df.drop_duplicates(subset='open_time', keep='first', inplace=True)
        return df[['open_time', 'oi_value']]
    return df

def download_funding_rates(client, symbol, start_ts, end_ts):
    all_data, current_start_ts = [], start_ts
    while True:
        logger.info(f"Fetching FR chunk starting from {datetime.fromtimestamp(current_start_ts/1000, tz=timezone.utc)}...")
        params = {"symbol": symbol, "startTime": current_start_ts, "endTime": end_ts, "limit": 1000}
        chunk = _fetch_with_retry(client.funding_rate, params)
        if chunk == "STOP" or not chunk: break
        all_data.extend(chunk)
        last_timestamp = chunk[-1]['fundingTime']
        if last_timestamp >= current_start_ts: current_start_ts = last_timestamp + 1
        else: logger.error("Timestamp did not advance. Halting."); break
        if end_ts and current_start_ts > end_ts: break
        time.sleep(0.5)
    df = pd.DataFrame(all_data)
    if not df.empty:
        df.rename(columns={'fundingTime': 'open_time', 'fundingRate': 'funding_rate'}, inplace=True)
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df.drop_duplicates(subset='open_time', keep='first', inplace=True)
        return df[['open_time', 'funding_rate']]
    return df

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="A versatile historical data downloader for Binance Futures.")
    parser.add_argument('--type', required=True, choices=['klines', 'oi', 'fr'])
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--interval', help="Required for 'klines' and 'oi'.")
    parser.add_argument('--start-date', required=True, help="Format: YYYY-MM-DD")
    parser.add_argument('--end-date', nargs='?', default=None, help="(Optional) Format: YYYY-MM-DD")
    args = parser.parse_args()

    if args.type in ['klines', 'oi'] and not args.interval:
        parser.error("--interval is required for data type 'klines' and 'oi'.")

    public_client = UMFutures(base_url="https://fapi.binance.com")
    
    start_ts = int(datetime.strptime(args.start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ts = int(datetime.strptime(args.end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000) if args.end_date else None
    
    result_df = None
    if args.type == 'klines':
        result_df = download_klines(public_client, args.symbol, args.interval, start_ts, end_ts)
    elif args.type == 'oi':
        result_df = download_open_interest(public_client, args.symbol, args.interval, args.start_date, args.end_date)
    elif args.type == 'fr':
        result_df = download_funding_rates(public_client, args.symbol, start_ts, end_ts)

    if result_df is not None:
        save_data(result_df, args.symbol, args.interval, args.type, args.start_date)
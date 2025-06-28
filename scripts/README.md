# Utility Scripts

This directory contains helper scripts for one-off or auxiliary tasks that run separately from the main trading bot application. These are tools to support development, data collection, and testing.

---

## `data_downloader.py`

This script is a versatile tool for downloading various types of historical data (Klines, Open Interest, Funding Rates) from the Binance API. The downloaded data is saved to a `.csv` file in the `data/` directory for future backtesting.

### Usage

This script is executed from the command line. From the project's root directory, use the following format:

```bash
python scripts/data_downloader.py --type <TYPE> --symbol <SYMBOL> --interval <INTERVAL> --start-date <DATE>
```

### Options

* `--type <TYPE>`: (Required) The type of data to download.
    * Choices: `klines`, `oi` (Open Interest), `fr` (Funding Rate).
* `--symbol <SYMBOL>`: (Required) The trading pair to download data for (e.g., `BTCUSDT`).
* `--interval <INTERVAL>`: (Required for `klines` and `oi`) The data time interval (e.g., `5m`, `15m`, `1h`, `4h`). Not needed for funding rates.
* `--start-date <YYYY-MM-DD>`: (Required) The start date for the data download.
* `--end-date <YYYY-MM-DD>`: (Optional) The end date for the data download. If omitted, downloads data up to the present.

### Example Commands

* **To download 1-hour kline data for BTCUSDT since 2023:**
    ```bash
    python scripts/data_downloader.py --type klines --symbol BTCUSDT --interval 1h --start-date 2023-01-01
    ```

* **To download 1-hour Open Interest data for BTCUSDT since 2023:**
    ```bash
    python scripts/data_downloader.py --type oi --symbol BTCUSDT --interval 1h --start-date 2023-01-01
    ```

* **To download Funding Rate history for BTCUSDT since 2023:**
    ```bash
    python scripts/data_downloader.py --type fr --symbol BTCUSDT --start-date 2023-01-01
    ```

### Output

The script will create a `.csv` file inside the `data/` directory with a descriptive name.
**Example:** `BTCUSDT_1h_klines_2023-01-01.csv`

---

## `backtester.py` (To be developed)

*(This script will be used to test various strategies on the downloaded historical data and measure their performance.)*


python scripts/backtester_ema_crossover.py --datafile data/SOLUSDT_15m_klines_2024-05-01.csv --capital 1000 --positionsize 200 --leverage 10

python scripts/backtester.py --strategy simple_ema_crossover --datafile-ltf data/SOLUSDT_15m_klines_2024-05-01.csv --capital 1000 --positionsize 1000 --leverage 10
python scripts/data_downloader.py --type klines --symbol SOLUSDT --interval 15m --start-date 2024-05-01
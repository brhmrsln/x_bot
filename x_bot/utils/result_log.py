import csv, pathlib

RESULT_FILE = pathlib.Path("trade_results.csv")

def log_trade(pnl: float, side: str, entry: float, exit: float) -> None:
    new = RESULT_FILE.exists() is False
    with RESULT_FILE.open("a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["side", "entry", "exit", "pnl"])
        w.writerow([side, entry, exit, pnl])

    # show running total
    with RESULT_FILE.open() as fh:
        r = csv.DictReader(fh)
        total = sum(float(row["pnl"]) for row in r)
    print(f"[bold magenta]Running PnL:[/] {total:+.2f} USDT")

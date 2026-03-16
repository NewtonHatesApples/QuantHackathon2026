import zipfile
import requests
import os
import shutil

import pandas as pd
import numpy as np

from datetime import date, timedelta
from pathlib import Path

symbol = "BTCUSDT"
interval = "1m"
base_url = "https://data.binance.vision/data/spot/daily/aggTrades"

start = date(2023, 1, 1)   # inclusive
end = date(2023, 1, 4)   # inclusive

download_dir = "tmp_data"
os.makedirs(download_dir, exist_ok=True)

# 1) Download and unzip daily files
d = start
while d <= end:
    ds = d.strftime("%Y-%m-%d")
    zip_name = f"{symbol}-aggTrades-{ds}.zip"
    url = f"{base_url}/{symbol}/{zip_name}"
    zip_path = os.path.join(download_dir, zip_name)

    print(f"Fetching {url}")
    r = requests.get(url)
    if r.status_code == 200:
        with open(zip_path, "wb") as f:
            f.write(r.content)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(download_dir)
        os.remove(zip_path)  # keep only CSV
        print(f"OK {ds}")
    else:
        print(f"Missing or error for {ds}: {r.status_code}")
    d += timedelta(days=1)

# 2) Concatenate all CSVs in time order
csv_files = sorted(f for f in os.listdir(download_dir) if f.endswith(".csv") and f.startswith(f"{symbol}"))

dfs = []
for fname in csv_files:
    path = os.path.join(download_dir, fname)
    df = pd.read_csv(path, header=None)
    # Binance kline schema:
    # 0 open time, 1 open, 2 high, 3 low, 4 close, 5 volume,
    # 6 close time, 7 quote asset volume, 8 number of trades,
    # 9 taker buy base volume, 10 taker buy quote volume, 11 ignore
    dfs.append(df)

if not dfs:
    raise RuntimeError("No CSVs downloaded; check dates and URLs.")

full = pd.concat(dfs, ignore_index=True)

full = full.sort_values(0).drop_duplicates(subset=0)
full = full.iloc[:, :-2]  # Drop last two column (useless)
threshold = 1e14
# Convert all time data in time column to ms
full.iloc[:, 5] = np.where(full.iloc[:, 5] > threshold, full.iloc[:, 5] // 1000, full.iloc[:, 0])

# 3) Save a single merged CSV
save_dir = "data"
os.makedirs(save_dir, exist_ok=True)
out_file = f"{save_dir}/{symbol}-aggTrades-{start.strftime('%Y-%m-%d')}_{end.strftime('%Y-%m-%d')}.csv"
full.to_csv(out_file, index=False, header=["AggregateTradeID", "Price", "Quantity", "FirstTradeID", "LastTradeID", "TradeTimestamp[ms]"])
print("Merged CSV written to:", out_file)

# Clear all the temp .zip files
root = Path(download_dir)
for item in root.iterdir():
    if item.is_file() or item.is_symlink():
        item.unlink()
    elif item.is_dir():
        shutil.rmtree(item)
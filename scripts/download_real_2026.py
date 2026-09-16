"""
Download real 2026 daily market data for Indian Equities and Indices from Jan 1, 2026 to today.
Tickers:
- NIFTY 50 (^NSEI)
- BANK NIFTY (^NSEBANK)
- INDIA VIX (^INDIAVIX)
Also downloads sample NSE F&O Bhavcopies to benchmark real options strikes & premiums.
"""

import os
import io
import zipfile
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime

os.makedirs("data/real_2026", exist_ok=True)
os.makedirs("data/real_2026/bhavcopies", exist_ok=True)

print("=" * 70)
print(f"DOWNLOADING REAL 2026 MARKET DATA (JAN 1, 2026 TO {datetime.now().strftime('%Y-%m-%d')})")
print("=" * 70)

# 1. Download Index OHLCV via Yahoo Finance
tickers = {
    "INDEX_NIFTY50": "^NSEI",
    "INDEX_BANKNIFTY": "^NSEBANK",
    "INDEX_INDIAVIX": "^INDIAVIX"
}

index_dfs = {}
for name, sym in tickers.items():
    print(f"\n[+] Downloading {name} ({sym})...")
    df = yf.download(sym, start="2026-01-01", end="2026-09-17", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]
    
    df = df.reset_index()
    if 'Date' in df.columns:
        df.rename(columns={'Date': 'datetime'}, inplace=True)
    elif 'date' in df.columns:
        df.rename(columns={'date': 'datetime'}, inplace=True)
        
    df['datetime'] = pd.to_datetime(df['datetime']).dt.strftime('%Y-%m-%d')
    df = df[['datetime', 'open', 'high', 'low', 'close', 'volume']]
    df = df.dropna(subset=['close']).sort_values('datetime').reset_index(drop=True)
    
    out_path = f"data/real_2026/{name}_daily.csv"
    df.to_csv(out_path, index=False)
    index_dfs[name] = df
    print(f"    Saved {len(df)} rows to {out_path}")
    print(f"    Date range: {df['datetime'].min()} to {df['datetime'].max()}")
    print(f"    Latest close ({df.iloc[-1]['datetime']}): {df.iloc[-1]['close']:.2f}")

# 2. Download sample NSE F&O UDiFF Bhavcopies for Options Ground Truth
print("\n[+] Downloading representative NSE F&O UDiFF Bhavcopies for options realism...")
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
sample_dates = ['20260115', '20260319', '20260618', '20260827', '20260915']

bhav_records = []
for d in sample_dates:
    url = f"https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{d}_F_0000.csv.zip"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            z = zipfile.ZipFile(io.BytesIO(r.content))
            csv_name = z.namelist()[0]
            with z.open(csv_name) as f:
                bhav_df = pd.read_csv(f)
                nifty_opts = bhav_df[bhav_df['TckrSymb'] == 'NIFTY']
                print(f"    Downloaded {d} Bhavcopy: {len(bhav_df)} total contracts, {len(nifty_opts)} NIFTY contracts.")
                # Save parsed NIFTY options snapshot
                nifty_opts.to_csv(f"data/real_2026/bhavcopies/NIFTY_options_{d}.csv", index=False)
                bhav_records.append({'date': d, 'contracts': len(nifty_opts), 'status': 'OK'})
        else:
            print(f"    Bhavcopy {d} HTTP {r.status_code}")
    except Exception as e:
        print(f"    Bhavcopy {d} error: {e}")

print("\nData Download Complete.")

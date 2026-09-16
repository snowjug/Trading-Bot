"""
Register all existing datasets with cryptographic provenance metadata.
Creates data/DATA_MANIFEST.json with SHA-256 hashes and full lineage.
"""
import os
import sys
sys.path.insert(0, os.path.abspath('.'))
import glob

from src.data.lineage import DataLineageRegistry, DataCategory

registry = DataLineageRegistry("data/DATA_MANIFEST.json")

# 1. Index EOD CSVs
index_map = {
    'INDEX_NIFTY50': ('^NSEI', 'NIFTY 50 Index'),
    'INDEX_BANKNIFTY': ('^NSEBANK', 'BANK NIFTY Index'),
    'INDEX_INDIA_VIX': ('^INDIAVIX', 'India VIX'),
    'INDEX_NIFTY_IT': ('^NIFTYIT', 'NIFTY IT Index'),
}

for fname, (ticker, inst) in index_map.items():
    path = f'data/raw/{fname}_daily.csv'
    if os.path.exists(path):
        m = registry.register_file(
            file_path=path,
            category=DataCategory.HISTORICAL_EOD_INDEX,
            instrument=inst,
            source_provider='Yahoo Finance (yfinance)',
            source_url=f'https://finance.yahoo.com/quote/{ticker}',
            frequency='1d',
            limitations='EOD OHLCV only. NOT intraday tick-level. Cannot reconstruct sub-daily order book.'
        )
        print(f"Registered {fname}: {m.row_count} rows, hash={m.file_hash_sha256[:16]}...")

# 2. Individual Equity EOD CSVs
equity_files = glob.glob('data/raw/*_daily.csv')
equity_files = [f for f in equity_files if 'INDEX_' not in os.path.basename(f)]
for ef in sorted(equity_files):
    sym = os.path.basename(ef).replace('_daily.csv', '')
    m = registry.register_file(
        file_path=ef,
        category=DataCategory.HISTORICAL_EOD_EQUITY,
        instrument=f'{sym} (NSE)',
        source_provider='Yahoo Finance (yfinance)',
        source_url=f'https://finance.yahoo.com/quote/{sym}.NS',
        frequency='1d',
        limitations='EOD OHLCV only. No bid/ask spread, no tick-level, no intraday timestamps.'
    )
    print(f"Registered {sym}: {m.row_count} rows, hash={m.file_hash_sha256[:16]}...")

# 3. Real 2026 Downloaded Data
for fname in ['INDEX_NIFTY50', 'INDEX_BANKNIFTY', 'INDEX_INDIAVIX']:
    path = f'data/real_2026/{fname}_daily.csv'
    if os.path.exists(path):
        m = registry.register_file(
            file_path=path,
            category=DataCategory.HISTORICAL_EOD_INDEX,
            instrument=fname.replace('INDEX_', '') + ' 2026 YTD',
            source_provider='Yahoo Finance (yfinance)',
            source_url='https://finance.yahoo.com',
            frequency='1d',
            limitations='EOD only, live-downloaded on 2026-09-16.'
        )
        print(f"Registered real_2026/{fname}: {m.row_count} rows")

# 4. NSE UDiFF F&O Bhavcopies
bhav_files = glob.glob('data/real_2026/bhavcopies/*.csv')
for bf in sorted(bhav_files):
    bname = os.path.basename(bf)
    m = registry.register_file(
        file_path=bf,
        category=DataCategory.NSE_UDIFF_BHAVCOPY,
        instrument='NIFTY Options Chain (Filtered)',
        source_provider='NSE India Official Archives',
        source_url=f'https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{bname.split("_")[-1].replace(".csv","")}_F_0000.csv.zip',
        frequency='eod_snapshot',
        limitations='Contains all listed NIFTY option strikes for one trading day. Settlement prices, OI, and traded volume included.'
    )
    print(f"Registered Bhavcopy {bname}: {m.row_count} contracts")

# 5. Universe History
univ_path = 'data/universe_history/nifty50_membership_history.csv'
if os.path.exists(univ_path):
    m = registry.register_file(
        file_path=univ_path,
        category=DataCategory.INDEX_CONSTITUENTS,
        instrument='NIFTY 50 Historical Membership',
        source_provider='NSE India / Manual Research',
        source_url='https://www.nseindia.com/',
        frequency='event',
        limitations='Semi-annual reconstitution events 2015-2026.'
    )
    print(f"Registered universe history: {m.row_count} events")

print(f"\nTotal datasets registered: {len(registry.registry)}")
print(f"Manifest saved to: {registry.manifest_path}")

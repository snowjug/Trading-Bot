import pandas as pd

updates = [
    ('INDEX_NIFTY50', 'INDEX_NIFTY50'),
    ('INDEX_BANKNIFTY', 'INDEX_BANKNIFTY'),
    ('INDEX_INDIA_VIX', 'INDEX_INDIAVIX'),
]

for base_name, real_name in updates:
    raw_path = f"data/raw/{base_name}_daily.csv"
    real_path = f"data/real_2026/{real_name}_daily.csv"
    raw_df = pd.read_csv(raw_path)
    real_df = pd.read_csv(real_path)

    max_d = raw_df['datetime'].max()
    new_rows = real_df[real_df['datetime'] > max_d].copy()
    if len(new_rows) > 0:
        combined = pd.concat([raw_df, new_rows], ignore_index=True)
        combined.to_csv(raw_path, index=False)
        print(f"Updated {raw_path}: added {len(new_rows)} rows up to {combined['datetime'].max()}")
    else:
        print(f"{raw_path} is already up to date ({max_d})")

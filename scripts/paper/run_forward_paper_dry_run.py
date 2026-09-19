"""
FORWARD PAPER TRADING DRY-RUN & REPORT RUNNER.
Performs ONE dry-run execution on the latest available market session (2026-09-18)
and produces reports/FORWARD_PAPER_TRADING.md.
"""
import os, sys, glob
from datetime import date, datetime
from pathlib import Path
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.config import Config
from src.execution.forward_paper_engine import ForwardPaperEngine

def main():
    print("=" * 80)
    print("FORWARD PAPER TRADING ENGINE — DRY RUN EXECUTION")
    print("=" * 80)

    # Verify hard safety lock
    assert not Config.LIVE_TRADING_ENABLED, "LIVE_TRADING_ENABLED must be False!"
    print(f"Safety Check Passed: LIVE_TRADING_ENABLED = {Config.LIVE_TRADING_ENABLED} (Read-Only Mode)")

    engine = ForwardPaperEngine(state_dir="data/paper", min_forward_days=90)

    # 1. Inspect latest authentic market file: idxopt_20260918.parquet
    latest_file = "data/raw/nse/fo_idxopt/idxopt_20260918.parquet"
    if not os.path.exists(latest_file):
        raise FileNotFoundError(f"Missing latest market file: {latest_file}")

    df_raw = pd.read_parquet(latest_file)
    nifty = df_raw[df_raw["TckrSymb"] == "NIFTY"]
    
    current_dt = date(2026, 9, 18)
    expiries = sorted(nifty["XpryDt"].unique())
    next_expiry = expiries[0] if expiries else "2026-09-22"
    is_expiry = (current_dt.strftime("%Y-%m-%d") in expiries)

    spot = float(nifty["UndrlygPric"].iloc[0]) if "UndrlygPric" in nifty.columns and pd.notna(nifty["UndrlygPric"].iloc[0]) else 25200.0
    print(f"Loaded Latest Session: {current_dt} | NIFTY Spot: {spot:.2f} | Next Expiry: {next_expiry} | Is 0DTE: {is_expiry}")

    # 2. Execute dry-run session
    res = engine.evaluate_session(
        current_date=current_dt,
        spot_open=spot,
        spot_close=spot,
        is_expiry=is_expiry,
        contracts_df=nifty[nifty["XpryDt"] == next_expiry],
        expiry_date_str=next_expiry
    )

    print("\nDry-Run Execution Results:")
    print(f"Date: {res['date']}")
    for act in res.get("actions", []):
        print(f"  Action: {act}")

    # 3. Generate Markdown Report
    report_md = engine.generate_report()
    report_path = Path("reports/FORWARD_PAPER_TRADING.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)
    print(f"\nSaved Forward Paper Trading Report to {report_path}")

    # 4. Print Summary Status
    print("\n" + "=" * 80)
    print("FORWARD PAPER ACCOUNTS SUMMARY")
    print("=" * 80)
    for acc in engine.accounts.values():
        print(
            f"{acc.account_id:8} | Init: Rs {acc.initial_capital:>8,.0f} | "
            f"Cash: Rs {acc.cash_balance:>8,.2f} | Equity: Rs {acc.current_equity:>8,.2f} | "
            f"Margin: Rs {acc.margin_utilized:>8,.0f} | Exec: {acc.trades_executed} | Skipped: {acc.trades_skipped_capital}"
        )


if __name__ == "__main__":
    main()

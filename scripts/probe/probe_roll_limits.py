import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from dotenv import load_dotenv; load_dotenv()
from src.data.dhan_client import get_dhan_client
c = get_dhan_client()
print("=== HOW FAR BACK ===")
for frm, to in [("2021-09-01","2021-09-30"),("2020-09-01","2020-09-30"),("2019-09-02","2019-09-30")]:
    r = c.fetch_rolling_options(from_date=frm, to_date=to, strike="ATM", drv_option_type="CALL")
    print(f"  {frm}: ce={len(r['ce'])}")
print("=== PUT SIDE ===")
r = c.fetch_rolling_options(from_date="2026-07-01", to_date="2026-07-31", strike="ATM", drv_option_type="PUT")
print("  PUT req -> ce rows:", len(r["ce"]), " pe rows:", len(r["pe"]))
print("=== STRIKE CEILING (Bot 1 needs ~ATM+13..17) ===")
for k in ["ATM+5","ATM+10","ATM+11","ATM+13","ATM+15","ATM+17","ATM+20","ATM+25"]:
    r = c.fetch_rolling_options(from_date="2026-07-01", to_date="2026-07-15", strike=k, drv_option_type="CALL")
    n = len(r["ce"])
    print(f"  {k:8s} bars={n}" + ("" if n else "   EMPTY"))

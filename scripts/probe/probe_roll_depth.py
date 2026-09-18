import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from dotenv import load_dotenv; load_dotenv()
from src.data.dhan_client import get_dhan_client
c = get_dhan_client()
for frm, to in [("2026-09-01","2026-09-15"),("2026-07-01","2026-07-31"),
                ("2026-03-01","2026-03-31"),("2025-09-01","2025-09-30"),
                ("2025-03-01","2025-03-31"),("2024-09-02","2024-09-30"),
                ("2023-09-01","2023-09-29"),("2022-09-01","2022-09-30")]:
    try:
        r = c.fetch_rolling_options(from_date=frm, to_date=to, strike="ATM", interval="5")
        ce, pe = r["ce"], r["pe"]
        if len(ce):
            print(f"{frm}..{to}: ce={len(ce):6d} pe={len(pe):6d} "
                  f"days={ce['datetime'].dt.date.nunique():3d} "
                  f"span {ce['datetime'].min()} -> {ce['datetime'].max()}")
        else:
            print(f"{frm}..{to}: EMPTY")
    except Exception as e:
        print(f"{frm}..{to}: ERR {type(e).__name__} {str(e)[:100]}")

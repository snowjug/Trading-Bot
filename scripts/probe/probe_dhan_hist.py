import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from dotenv import load_dotenv
load_dotenv()
from src.data.dhan_client import get_dhan_client
c = get_dhan_client()
for seg, inst, sid, name in [("IDX_I","INDEX","13","NIFTY"),("IDX_I","INDEX","21","INDIAVIX")]:
    try:
        df = c.fetch_historical_daily(sid, seg, inst, "2024-01-01", "2024-02-01")
        print(f"{name}: rows={len(df)}")
        if len(df): print(df.head(2).to_string())
    except Exception as e:
        print(name, "ERR", type(e).__name__, str(e)[:160])

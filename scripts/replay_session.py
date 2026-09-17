"""
Market Replay Runner Script (Phase 10).
Usage:
python scripts/replay_session.py --date YYYY-MM-DD --speed 0 --strategy all
"""

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.logging import setup_logging
from src.replay.engine import MarketReplayEngine
from src.replay.event_bus import MarketEventBus

logger = setup_logging("scripts.replay_session")


def main():
    parser = argparse.ArgumentParser(description="Replay Market Data Through Strategy Engine")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Session date YYYY-MM-DD")
    parser.add_argument("--speed", type=float, default=0.0, help="Replay speed (0 = deterministic zero-delay)")
    parser.add_argument("--strategy", default="all", help="Strategy name or 'all'")
    parser.add_argument("--symbol", default="NIFTY", help="Symbol or index")
    args = parser.parse_args()

    replay_d = datetime.strptime(args.date, "%Y-%m-%d").date()
    bus = MarketEventBus()
    
    # Track dispatched events
    dispatched = []
    bus.subscribe(lambda ev: dispatched.append(ev))

    engine = MarketReplayEngine(event_bus=bus, speed=args.speed)
    df = engine.load_dataset_for_date(replay_date=replay_d, symbol=args.symbol)

    if df.empty:
        logger.error(f"No market data available for replay on {args.date}.")
        sys.exit(1)

    result = engine.run_replay(df, strategy_name=args.strategy)
    print("==================================================")
    print("REPLAY SESSION EXECUTION SUMMARY")
    print("==================================================")
    print(f"Date:               {args.date}")
    print(f"Symbol:             {args.symbol}")
    print(f"Speed:              {args.speed} ({'Deterministic' if args.speed == 0 else 'Simulated'})")
    print(f"Events Dispatched:  {len(dispatched)}")
    print(f"Determinism Check:  {result['determinism']}")
    print("==================================================")


if __name__ == "__main__":
    main()

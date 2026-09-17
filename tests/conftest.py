import os
import sys
from pathlib import Path

# Add project root to sys.path so tests can import src cleanly under any pytest version
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


import pytest


@pytest.fixture(autouse=True)
def _no_network_reconciliation(monkeypatch):
    """
    Keeps the suite hermetic.

    Production sessions reconcile against the broker on every cycle, which would
    otherwise make every test that calls evaluate_all_bots perform a live Dhan
    GET /positions request. Tests that exercise reconciliation call
    reconcile_with_broker() directly with injected broker state, which this
    fixture does not touch.
    """
    from src.execution import position_reconciler

    monkeypatch.setattr(position_reconciler, "broker_source_configured", lambda: False)
    monkeypatch.setattr(
        position_reconciler, "fetch_broker_positions_readonly", lambda: (None, False)
    )

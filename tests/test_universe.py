"""
Tests for historical universe management and survivorship bias elimination.
"""
import pytest
from datetime import datetime
from src.data.universe import HistoricalUniverseManager


def test_historical_universe_membership():
    mgr = HistoricalUniverseManager()
    
    # In 2018, YESBANK was in NIFTY 50, but ADANIENT was NOT in NIFTY 50
    u_2018 = mgr.get_eligible_universe(datetime(2018, 5, 1))
    assert "YESBANK" in u_2018, "YESBANK must be present in NIFTY 50 in 2018"
    assert "ADANIENT" not in u_2018, "ADANIENT was not in NIFTY 50 in 2018 (added in 2022)"
    
    # In 2025, YESBANK is NOT in NIFTY 50, but ADANIENT IS in NIFTY 50
    u_2025 = mgr.get_eligible_universe(datetime(2025, 1, 1))
    assert "YESBANK" not in u_2025, "YESBANK was excluded in 2020"
    assert "ADANIENT" in u_2025, "ADANIENT was added in 2022"


def test_is_eligible_helper():
    mgr = HistoricalUniverseManager()
    
    assert mgr.is_eligible("YESBANK", "2017-06-15") is True
    assert mgr.is_eligible("YESBANK", "2021-06-15") is False
    assert mgr.is_eligible("SHRIRAMFIN", "2021-06-15") is False
    assert mgr.is_eligible("SHRIRAMFIN", "2024-05-01") is True

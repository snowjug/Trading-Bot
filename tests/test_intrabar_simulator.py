"""
Tests for Intrabar Simulator path-dependency resolutions.
"""
import pytest
from src.backtesting.intrabar_simulator import IntrabarSimulator, IntrabarMode


def test_intrabar_ambiguous_bar_resolution():
    # Long trade entered @ 100. Target = 105 (+5), Stop = 95 (-5)
    # The bar has High = 108 and Low = 92 (both target and stop hit!)
    entry = 100.0
    target_pts = 5.0
    stop_pts = 5.0
    high = 108.0
    low = 92.0
    close = 101.0

    # 1. Conservative Mode: Must trigger STOP LOSS
    res_cons = IntrabarSimulator.resolve_exit(
        is_long=True, entry_price=entry, target_pts=target_pts, stop_pts=stop_pts,
        high=high, low=low, close=close, mode=IntrabarMode.CONSERVATIVE
    )
    assert res_cons.is_stop is True
    assert res_cons.is_target is False
    assert res_cons.exit_price == 95.0
    assert res_cons.exit_reason == "STOP_CONSERVATIVE"

    # 2. Optimistic Mode: Must trigger TARGET
    res_opt = IntrabarSimulator.resolve_exit(
        is_long=True, entry_price=entry, target_pts=target_pts, stop_pts=stop_pts,
        high=high, low=low, close=close, mode=IntrabarMode.OPTIMISTIC
    )
    assert res_opt.is_stop is False
    assert res_opt.is_target is True
    assert res_opt.exit_price == 105.0
    assert res_opt.exit_reason == "TARGET_OPTIMISTIC"


def test_intrabar_clear_cases():
    entry = 100.0
    target_pts = 5.0
    stop_pts = 5.0
    
    # Case A: Only Target reached (High=106, Low=98)
    res_a = IntrabarSimulator.resolve_exit(
        is_long=True, entry_price=entry, target_pts=target_pts, stop_pts=stop_pts,
        high=106.0, low=98.0, close=104.0, mode=IntrabarMode.CONSERVATIVE
    )
    assert res_a.is_target is True
    assert res_a.exit_price == 105.0

    # Case B: Only Stop reached (High=102, Low=94)
    res_b = IntrabarSimulator.resolve_exit(
        is_long=True, entry_price=entry, target_pts=target_pts, stop_pts=stop_pts,
        high=102.0, low=94.0, close=96.0, mode=IntrabarMode.CONSERVATIVE
    )
    assert res_b.is_stop is True
    assert res_b.exit_price == 95.0

    # Case C: Neither reached (High=103, Low=97, Close=102) -> EOD Close
    res_c = IntrabarSimulator.resolve_exit(
        is_long=True, entry_price=entry, target_pts=target_pts, stop_pts=stop_pts,
        high=103.0, low=97.0, close=102.0, mode=IntrabarMode.CONSERVATIVE
    )
    assert res_c.is_stop is False
    assert res_c.is_target is False
    assert res_c.exit_price == 102.0
    assert res_c.exit_reason == "EOD_CLOSE"

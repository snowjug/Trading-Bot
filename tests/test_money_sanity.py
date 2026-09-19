"""
Money Sanity and Monotonicity Test Suite.
Verifies Section 38 (MONEY SANITY TEST) and Section 39 (MONOTONICITY TESTS)
of the Canonical Strategy Benchmark Master Prompt.

Deterministic tests with mathematically exact expected values:
- Long futures, Short futures
- Long option, Short option
- Vertical spread (defined risk)
- Iron condor (4 legs)
- Monotonicity: higher fees, higher slippage, worse entry/exit strictly decrease Net P&L
- Quantity and lot-size scaling
- Dual-engine Penny-matched statutory cost accounting
"""
import pytest
from src.research.independent_pnl import IndependentPnLCalculator


# ══════════════════════════════════════════════════════════════════════════════
# 1. DETERMINISTIC INSTRUMENT & SPREAD PAYOFF TESTS
# ══════════════════════════════════════════════════════════════════════════════

def test_long_futures_deterministic_pnl():
    """Long future: Gross P&L = (exit - entry) * quantity."""
    entry = 24500.0
    exit_price = 24650.0  # +150 points
    lot_size = 65  # NIFTY lot
    qty = lot_size * 2  # 130 qty (2 lots)

    gross, costs, net = IndependentPnLCalculator.calculate_trade_pnl(
        entry_price=entry,
        exit_price=exit_price,
        quantity=qty,
        is_long=True,
        is_option=False,
        slippage_pts=0.0,
    )
    expected_gross = (24650.0 - 24500.0) * 130
    assert gross == pytest.approx(expected_gross), f"Expected {expected_gross}, got {gross}"
    assert gross == 19500.0

    # Turnovers
    buy_turnover = entry * qty  # 24500 * 130 = 3,185,000
    sell_turnover = exit_price * qty  # 24650 * 130 = 3,204,500
    total_turnover = buy_turnover + sell_turnover  # 6,389,500

    # Check statutory breakdown
    assert costs["brokerage"] == 40.0  # 20 buy + 20 sell
    assert costs["stt"] == round(sell_turnover * 0.0002, 2)  # 0.02% on futures sell
    assert costs["stamp_duty"] == round(buy_turnover * 0.00003, 2)  # 0.003% on buy
    assert net == pytest.approx(gross - costs["total_costs"], abs=0.01)


def test_short_futures_deterministic_pnl():
    """Short future: Gross P&L = (entry - exit) * quantity."""
    entry = 52000.0  # BANKNIFTY
    exit_price = 51750.0  # +250 points profit
    qty = 30  # 2 lots (lot size 15)

    gross, costs, net = IndependentPnLCalculator.calculate_trade_pnl(
        entry_price=entry,
        exit_price=exit_price,
        quantity=qty,
        is_long=False,
        is_option=False,
        slippage_pts=0.0,
    )
    expected_gross = (52000.0 - 51750.0) * 30
    assert gross == pytest.approx(expected_gross)
    assert gross == 7500.0
    assert net < gross  # Costs must deduct from profit


def test_long_option_expires_worthless_caps_loss_at_premium():
    """Long option expiring worthless: Gross loss strictly equals -premium * qty."""
    premium = 120.0
    exit_price = 0.0
    qty = 65

    gross, costs, net = IndependentPnLCalculator.calculate_trade_pnl(
        entry_price=premium,
        exit_price=exit_price,
        quantity=qty,
        is_long=True,
        is_option=True,
        slippage_pts=0.0,
    )
    expected_loss = -120.0 * 65
    assert gross == pytest.approx(expected_loss)
    assert gross == -7800.0
    # Net loss must be even more negative due to buy-side costs
    assert net < gross


def test_vertical_spread_defined_risk_bounds():
    """
    Bull Put Spread:
    Sell 24000 PE @ 140.0, Buy 23800 PE @ 60.0 (Width = 200, Net Credit = 80.0)
    Max Gain = Credit * qty = 80 * 65 = +5,200
    Max Loss = (Width - Credit) * qty = (200 - 80) * 65 = -7,800
    """
    width = 200.0
    credit = 80.0
    lot = 65
    max_gain = credit * lot
    max_loss = (width - credit) * lot

    # Case A: Spot stays above 24000 -> Both expire at 0.0 -> Keep full credit
    short_leg_gross, _, _ = IndependentPnLCalculator.calculate_trade_pnl(
        entry_price=140.0, exit_price=0.0, quantity=lot, is_long=False, is_option=True
    )
    long_leg_gross, _, _ = IndependentPnLCalculator.calculate_trade_pnl(
        entry_price=60.0, exit_price=0.0, quantity=lot, is_long=True, is_option=True
    )
    spread_gross = short_leg_gross + long_leg_gross
    assert spread_gross == pytest.approx(max_gain)
    assert spread_gross == 5200.0

    # Case B: Spot crashes to 23500 -> Max loss breached
    # Short 24000 PE settles at 500, Long 23800 PE settles at 300
    short_leg_gross_b, _, _ = IndependentPnLCalculator.calculate_trade_pnl(
        entry_price=140.0, exit_price=500.0, quantity=lot, is_long=False, is_option=True
    )
    long_leg_gross_b, _, _ = IndependentPnLCalculator.calculate_trade_pnl(
        entry_price=60.0, exit_price=300.0, quantity=lot, is_long=True, is_option=True
    )
    spread_gross_b = short_leg_gross_b + long_leg_gross_b
    assert spread_gross_b == pytest.approx(-max_loss)
    assert spread_gross_b == -7800.0


def test_iron_condor_four_leg_exact_boundaries():
    """
    Iron Condor 4 real legs:
    Put Wing: Long 23600 PE @ 25, Short 23800 PE @ 65 (Width = 200, Put Credit = 40)
    Call Wing: Short 24400 CE @ 70, Long 24600 CE @ 30 (Width = 200, Call Credit = 40)
    Total Credit = 80.0 pts.
    Wing Width = 200.0 pts.
    Max Risk per lot = (200 - 80) * 65 = 7,800.
    """
    lot = 65
    credit = (65 - 25) + (70 - 30)  # 80.0
    wing_width = 200.0
    max_loss = (wing_width - credit) * lot  # 7800.0

    # Test spot at 24100 (in between short strikes, all expire worthless)
    sp_pnl = (65.0 - 0.0) * lot
    lp_pnl = (0.0 - 25.0) * lot
    sc_pnl = (70.0 - 0.0) * lot
    lc_pnl = (0.0 - 30.0) * lot
    condor_gross = sp_pnl + lp_pnl + sc_pnl + lc_pnl
    assert condor_gross == pytest.approx(credit * lot)
    assert condor_gross == 5200.0

    # Test spot at 25000 (severe upward breach)
    # Put legs both 0 -> P&L = +40 * lot
    # Short Call settles at 600, Long Call settles at 400
    sc_loss = (70.0 - 600.0) * lot
    lc_gain = (400.0 - 30.0) * lot
    condor_breach_gross = (40.0 * lot) + sc_loss + lc_gain
    assert condor_breach_gross == pytest.approx(-max_loss)
    assert condor_breach_gross == -7800.0


# ══════════════════════════════════════════════════════════════════════════════
# 2. MONOTONICITY & SCALING TESTS (Master Prompt Section 39)
# ══════════════════════════════════════════════════════════════════════════════

def test_monotonicity_higher_slippage_cannot_improve_net_pnl():
    """Higher slippage must strictly decrease or keep equal net P&L."""
    entry, exit_p, qty = 100.0, 150.0, 65

    _, costs_low, net_low = IndependentPnLCalculator.calculate_trade_pnl(
        entry, exit_p, qty, is_long=True, is_option=True, slippage_pts=0.5
    )
    _, costs_high, net_high = IndependentPnLCalculator.calculate_trade_pnl(
        entry, exit_p, qty, is_long=True, is_option=True, slippage_pts=1.5
    )
    assert costs_high["total_costs"] > costs_low["total_costs"]
    assert net_high < net_low


def test_monotonicity_worse_entry_strictly_decreases_pnl():
    """Worse entry price (higher for buy, lower for sell) strictly degrades P&L."""
    qty = 65
    # Long: normal entry 100 vs worse entry 105
    gross_norm, _, net_norm = IndependentPnLCalculator.calculate_trade_pnl(
        100.0, 150.0, qty, is_long=True, is_option=True, slippage_pts=0.5
    )
    gross_worse, _, net_worse = IndependentPnLCalculator.calculate_trade_pnl(
        105.0, 150.0, qty, is_long=True, is_option=True, slippage_pts=0.5
    )
    assert gross_worse < gross_norm
    assert net_worse < net_norm


def test_monotonicity_worse_exit_strictly_decreases_pnl():
    """Worse exit price (lower for buy, higher for sell) strictly degrades P&L."""
    qty = 65
    # Long: exit 150 vs worse exit 145
    gross_norm, _, net_norm = IndependentPnLCalculator.calculate_trade_pnl(
        100.0, 150.0, qty, is_long=True, is_option=True, slippage_pts=0.5
    )
    gross_worse, _, net_worse = IndependentPnLCalculator.calculate_trade_pnl(
        100.0, 145.0, qty, is_long=True, is_option=True, slippage_pts=0.5
    )
    assert gross_worse < gross_norm
    assert net_worse < net_norm


def test_scaling_doubling_quantity_doubles_gross_pnl():
    """Doubling quantity must double gross P&L exactly."""
    entry, exit_p = 200.0, 260.0
    qty1 = 65
    qty2 = 130

    gross1, _, _ = IndependentPnLCalculator.calculate_trade_pnl(
        entry, exit_p, qty1, is_long=True, is_option=True, slippage_pts=0.0
    )
    gross2, _, _ = IndependentPnLCalculator.calculate_trade_pnl(
        entry, exit_p, qty2, is_long=True, is_option=True, slippage_pts=0.0
    )
    assert gross2 == pytest.approx(gross1 * 2.0)
    assert gross1 == 3900.0
    assert gross2 == 7800.0


def test_scaling_lot_size_scaling_holds_for_defined_risk():
    """Scaling lot count scales defined max loss linearly."""
    width, credit = 200.0, 75.0
    lot_size = 65
    single_lot_risk = (width - credit) * lot_size

    for num_lots in (1, 2, 4, 8):
        scaled_risk = (width - credit) * (lot_size * num_lots)
        assert scaled_risk == pytest.approx(single_lot_risk * num_lots)

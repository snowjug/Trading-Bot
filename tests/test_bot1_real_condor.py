"""
Bot 1 — authentic four-leg Iron Condor.

These tests exist to stop the ways this engine could quietly become fiction:
pricing a leg that never traded, reading the wrong settlement field, silently
substituting a nearer strike, charging a short leg's STT where it is not incurred,
or reporting a green backtest whose sample cannot distinguish it from a loser.
"""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.research import validation as V
from src.research.bot1_condor_real import (
    EXECUTION_BASIS,
    SPEC_OTM_SD,
    SPEC_WING_SD,
    STT_RATE_EXERCISE,
    CondorLeg,
    CondorTrade,
    adverse_fill_pnl,
    build_condor,
    condor_leg_costs,
    condor_strikes,
    load_bhavcopy_store,
    run_real_condor_backtest,
    settlement_price,
    settlement_source,
    summarise_condor,
    weekly_expiry_calendar,
)
from src.execution.cost_model import IndianCostModel


@pytest.fixture(scope="module")
def store():
    s = load_bhavcopy_store()
    if s is None or s.empty:
        pytest.skip("bhavcopy store not ingested; run scripts/ingest_nse_fo_bhavcopy.py")
    return s


@pytest.fixture(scope="module")
def index_df():
    n = pd.read_csv("data/real_2026/INDEX_NIFTY50_daily.csv")
    v = pd.read_csv("data/real_2026/INDEX_INDIAVIX_daily.csv")
    n["datetime"] = pd.to_datetime(n["datetime"])
    v["datetime"] = pd.to_datetime(v["datetime"])
    return n.merge(v[["datetime", "close"]].rename(columns={"close": "vix"}), on="datetime")


# ════════════════════ DATA SEMANTICS ════════════════════

def test_expiry_day_settlement_is_the_underlying_not_the_option(store):
    """
    The trap this engine must not fall into.

    Where the bhavcopy publishes SttlmPric on an expiry session it carries the
    UNDERLYING's settlement price, identical on every row. Reading it as an option
    price would value every leg at the index level.
    """
    checked = 0
    for e in weekly_expiry_calendar(store):
        rows = store[(store["TradDt"] == e) & (store["XpryDt"] == e)]
        if rows.empty:
            continue
        vals = rows["SttlmPric"].dropna().unique()
        if len(vals) != 1 or vals[0] <= 0:
            continue                       # unpublished in this era; covered below
        assert vals[0] > 1000, "settlement must be an index level, not a premium"
        assert settlement_price(store, e) == pytest.approx(float(vals[0]))
        if "UndrlygPric" in rows.columns and rows["UndrlygPric"].notna().any():
            u = float(rows["UndrlygPric"].dropna().iloc[0])
            if u > 0:
                assert abs(vals[0] - u) / u < 0.02
        checked += 1
        if checked >= 20:
            break
    assert checked >= 5, "expected several expiry sessions with a published settlement"


def test_legacy_sessions_publish_no_settlement_and_fail_closed(store):
    """
    A real data regime, not a hypothetical: the legacy derivatives archive writes
    SETTLE_PR = 0.0 on expiry rows for 2019-2020. Without a fallback the engine
    must refuse rather than value the legs at zero.
    """
    zero_era = [e for e in weekly_expiry_calendar(store)
                if e.year <= 2020
                and not store[(store["TradDt"] == e) & (store["XpryDt"] == e)].empty
                and float(store[(store["TradDt"] == e) & (store["XpryDt"] == e)]
                          ["SttlmPric"].max()) <= 0]
    if not zero_era:
        pytest.skip("no legacy expiry session ingested")
    e = zero_era[0]
    assert settlement_price(store, e) is None, "must fail closed without a source"
    assert settlement_price(store, e, {e: 11000.0}) == 11000.0
    assert settlement_price(store, e, {e: 0.0}) is None, "a zero fallback is not a price"
    assert settlement_source(store, e) == "NSE_INDEX_CLOSE_VERIFIED_IDENTICAL"


def test_index_close_fallback_is_verified_identical_where_both_exist(store):
    """
    The fallback is justified by measurement, not assumption.

    On every expiry session where BOTH the bhavcopy settlement and the NSE index
    close exist, they must agree exactly — otherwise the fallback is a proxy and
    must not be used silently.
    """
    idx = pd.read_parquet("data/raw/nse/index_history/nse_index_daily.parquet")
    n = idx[idx["symbol"] == "NIFTY50"][["datetime", "close"]].copy()
    closes = {d.date(): float(c) for d, c in zip(pd.to_datetime(n["datetime"]), n["close"])}

    compared = 0
    for e in weekly_expiry_calendar(store):
        rows = store[(store["TradDt"] == e) & (store["XpryDt"] == e)]
        if rows.empty or e not in closes:
            continue
        vals = rows["SttlmPric"].dropna().unique()
        if len(vals) != 1 or vals[0] <= 0:
            continue
        assert float(vals[0]) == pytest.approx(closes[e], abs=1e-6), (
            f"{e}: index close and settlement diverge, so the fallback is a proxy"
        )
        compared += 1
    assert compared >= 20, "too few comparisons to justify the fallback"


def test_untraded_contracts_have_unusable_closes(store):
    """
    Justifies the TtlTradgVol > 0 rule with the data itself.

    On an expiry session a contract that traded closes near intrinsic; one that did
    not can be hundreds of points away, because its close is a theoretical value.
    """
    for e in weekly_expiry_calendar(store):
        rows = store[(store["TradDt"] == e) & (store["XpryDt"] == e) & (store["OptnTp"] == "CE")]
        if len(rows) < 40:
            continue
        s = settlement_price(store, e)
        if s is None:
            continue
        r = rows.copy()
        r["intrinsic"] = (s - r["StrkPric"]).clip(lower=0)
        r["err"] = (r["ClsPric"] - r["intrinsic"]).abs()
        traded = r[r["TtlTradgVol"] > 0]
        untraded = r[r["TtlTradgVol"] == 0]
        if len(traded) < 10 or len(untraded) < 10:
            continue
        assert traded["err"].mean() < untraded["err"].mean(), (
            "traded closes must track intrinsic more closely than untraded ones"
        )
        return
    pytest.skip("no expiry session with both traded and untraded contracts")


def test_store_carries_no_synthetic_rows(store):
    """Every row must be an exchange print, with a real strike and expiry."""
    assert store["StrkPric"].min() > 0
    assert store["XpryDt"].notna().all()
    assert set(store["OptnTp"].unique()) <= {"CE", "PE"}
    assert (store["TradDt"] <= store["XpryDt"]).all(), "a trade date cannot follow its expiry"


# ════════════════════ CONSTRUCTION: FAIL CLOSED ════════════════════

def test_strikes_follow_the_specification_formula():
    """exp_move = spot * vix/100 * sqrt(5/365), verbatim; shorts 1.8, wings 2.4."""
    spot, vix = 23212.05, 13.2
    k = condor_strikes(spot, vix, SPEC_OTM_SD, SPEC_WING_SD)
    expected = spot * (vix / 100.0) * np.sqrt(5.0 / 365.0)
    assert k["expected_move"] == pytest.approx(expected)
    assert k["long_call"] > k["short_call"] > spot > k["short_put"] > k["long_put"]
    for name in ("short_call", "long_call", "short_put", "long_put"):
        assert k[name] % 50 == 0, "strikes must land on the real 50-point ladder"


def test_a_leg_that_did_not_trade_is_refused(store):
    """A zero-volume contract has no executable price, so the condor must refuse."""
    day = sorted(store["TradDt"].unique())[len(store["TradDt"].unique()) // 2]
    chain = store[store["TradDt"] == day]
    expiry = sorted(chain["XpryDt"].unique())[0]
    sub = chain[chain["XpryDt"] == expiry]
    untraded = sub[(sub["TtlTradgVol"] == 0) & (sub["OptnTp"] == "CE")]
    if untraded.empty:
        pytest.skip("no untraded contract on the sampled session")
    # Aim the construction at a strike that is present but did not trade.
    k = float(untraded.iloc[len(untraded) // 2]["StrkPric"])
    spot = k / (1 + SPEC_OTM_SD * 0.02)
    out = build_condor(store, day, expiry, spot=spot, vix=13.0)
    assert out["ok"] is False or all(
        r["TtlTradgVol"] > 0 for _, _, _, _, r in out["legs"]
    ), "no leg may be filled at a price that never traded"


def test_absent_strike_is_never_replaced_by_a_nearer_one(store):
    """Substituting the nearest available strike would silently change the strategy."""
    day = sorted(store["TradDt"].unique())[0]
    expiry = sorted(store[store["TradDt"] == day]["XpryDt"].unique())[0]
    out = build_condor(store, day, expiry, spot=23000.0, vix=95.0)   # absurd width
    assert out["ok"] is False
    assert out["reason"] in ("STRIKE_ABSENT", "LEG_DID_NOT_TRADE", "NO_CHAIN_FOR_EXPIRY")
    assert "legs" not in out or not out.get("legs")


def test_missing_expiry_chain_fails_closed(store):
    out = build_condor(store, date(1990, 1, 1), date(1990, 1, 8), spot=23000.0, vix=13.0)
    assert out["ok"] is False and out["reason"] == "NO_CHAIN_FOR_EXPIRY"


# ════════════════════ COSTS ════════════════════

def test_short_leg_stt_is_charged_on_the_premium_received(store):
    """
    The defect this function exists to fix.

    A short option expiring worthless exits at 0. The generic roundtrip helper
    charges STT on the exit, reporting almost none, when the real liability is
    0.1% of the premium sold at entry.
    """
    entry, qty = 20.0, 65

    # The naive helper charges STT on the exit, which is 0 for a worthless expiry.
    generic = IndianCostModel.calculate_roundtrip_costs(entry, 0.0, qty)
    assert generic.stt == pytest.approx(0.0), (
        "precondition: the naive roundtrip model charges a short leg no STT at all "
        "when the option expires worthless — this is the defect being fixed"
    )

    # The side-aware model charges it on the premium actually received.
    mine = condor_leg_costs("SELL", entry, 0.0, qty)
    no_premium = condor_leg_costs("SELL", 0.0, 0.0, qty)
    charged_stt = mine - no_premium
    assert charged_stt == pytest.approx(
        entry * qty * IndianCostModel.STT_RATE_SELL
        * (1 + 0)                                  # STT itself is not GST-bearing
        + entry * qty * IndianCostModel.EXCHANGE_TURNOVER_RATE * 1.18
        + entry * qty * IndianCostModel.SEBI_RATE * 1.18,
        rel=1e-6,
    ), "a short leg's STT must scale with the premium received at entry"
    assert charged_stt > 0

    # It is legitimately CHEAPER overall than the naive roundtrip, because holding to
    # expiry involves no exit ORDER: one brokerage charge, one slippage event. That
    # optimism is bounded by the slippage sensitivity, which prices an extra
    # 0.25-2.0 points per leg — far more than a second brokerage charge.
    assert mine < generic.total_costs
    assert generic.total_costs - mine < IndianCostModel.BROKERAGE_PER_ORDER * 1.18 + 0.10 * qty + 1.0


def test_long_leg_pays_exercise_stt_only_when_in_the_money():
    otm = condor_leg_costs("BUY", 10.0, 0.0, 65)
    itm = condor_leg_costs("BUY", 10.0, 200.0, 65)
    assert itm > otm, "an exercised ITM long must pay exercise STT"
    assert itm - otm > 200.0 * 65 * STT_RATE_EXERCISE * 0.5
    assert STT_RATE_EXERCISE > IndianCostModel.STT_RATE_SELL


def test_costs_are_never_negative_or_zero():
    for side in ("BUY", "SELL"):
        for e, x in [(5.0, 0.0), (50.0, 120.0), (0.5, 0.0)]:
            assert condor_leg_costs(side, e, x, 65) > 0


# ════════════════════ BACKTEST BEHAVIOUR ════════════════════

@pytest.fixture(scope="module")
def result(store, index_df):
    return run_real_condor_backtest(index_df, store, signal_lag=0)


def test_backtest_produces_real_four_leg_trades(result):
    assert result["status"] == "OK" and result["trades"]
    for t in result["trades"]:
        assert {l.role for l in t.legs} == {"short_call", "long_call", "short_put", "long_put"}
        assert len({l.strike for l in t.legs}) == 4, "four distinct strikes"
        for l in t.legs:
            assert l.entry_price > 0, "every leg must be priced from a real print"
            assert l.entry_volume > 0, "every leg must have actually traded"
            assert l.quantity > 0 and l.expiry and l.contract_name
            assert l.option_type in ("CE", "PE") and l.side in ("BUY", "SELL")


def test_leg_pnl_sums_to_the_trade_gross(result):
    for t in result["trades"][:40]:
        assert sum(l.pnl for l in t.legs) == pytest.approx(t.gross_pnl, abs=0.02)
        assert t.net_pnl == pytest.approx(t.gross_pnl - t.costs, abs=0.02)


def test_exit_prices_are_exact_cash_settlement(result):
    """Each leg must exit at intrinsic against the settlement price — not a quote."""
    for t in result["trades"][:40]:
        for l in t.legs:
            expect = (max(0.0, t.spot_settle - l.strike) if l.option_type == "CE"
                      else max(0.0, l.strike - t.spot_settle))
            assert l.exit_price == pytest.approx(expect, abs=1e-6)


def test_structure_is_a_defined_risk_condor(result):
    for t in result["trades"][:40]:
        roles = {l.role: l for l in t.legs}
        assert roles["long_call"].strike > roles["short_call"].strike
        assert roles["long_put"].strike < roles["short_put"].strike
        assert roles["short_call"].side == "SELL" and roles["long_call"].side == "BUY"
        assert roles["short_put"].side == "SELL" and roles["long_put"].side == "BUY"
        assert t.max_loss_points > 0, "a defined-risk structure must have a bounded loss"
        assert t.net_pnl >= -(t.max_loss_points * t.lot_size + t.costs) - 0.01, \
            "realised loss must never exceed the structural maximum"


def test_canonical_entry_is_exactly_five_trading_sessions(result, index_df):
    assert result["entry_rule"] == "EXACTLY_5_TRADING_SESSIONS_TO_EXPIRY"
    sess = list(index_df.sort_values("datetime")["datetime"].dt.date)
    pos = {d: i for i, d in enumerate(sess)}
    for t in result["trades"]:
        e, x = pd.Timestamp(t.entry_date).date(), pd.Timestamp(t.expiry).date()
        if e in pos and x in pos:
            assert pos[x] - pos[e] == 5, f"{t.entry_date}->{t.expiry} is not a 5-session hold"


def test_one_trade_per_expiry(result):
    ex = [t.expiry for t in result["trades"]]
    assert len(ex) == len(set(ex)), "the weekly cycle must not be traded twice"


def test_no_future_price_is_consulted(store, index_df):
    """
    Mutating sessions strictly AFTER a trade's expiry must not change it.

    The entry rule counts sessions on the published exchange calendar, which is
    known in advance; this proves no future PRICE leaks in.
    """
    base = run_real_condor_backtest(index_df, store, signal_lag=0)
    cut = pd.Timestamp(base["trades"][3].expiry)
    mutated = index_df.copy()
    m = mutated["datetime"] > cut
    for c in ("open", "high", "low", "close"):
        mutated.loc[m, c] = mutated.loc[m, c] * 1.35
    mutated.loc[m, "vix"] = 45.0
    after = run_real_condor_backtest(mutated, store, signal_lag=0)
    for a, b in zip(base["trades"][:4], after["trades"][:4]):
        assert (a.entry_date, a.expiry, a.net_pnl) == (b.entry_date, b.expiry, b.net_pnl)


def test_every_trade_declares_its_execution_basis(result):
    for t in result["trades"]:
        assert t.execution_basis == EXECUTION_BASIS
        assert "NO_BIDASK" in t.execution_basis, "the missing spread must be declared"


def test_summary_of_no_trades_is_explicit():
    s = summarise_condor([])
    assert s["total_trades"] == 0 and "note" in s
    assert s["execution_basis"] == EXECUTION_BASIS


def test_module_contains_no_fabricated_constants():
    src = open("src/research/bot1_condor_real.py", encoding="utf-8").read()
    for banned in ("55000.0", "2500.0", "0.55", "opt_delta", "credit_per_lot"):
        assert banned not in src, f"fabricated constant {banned!r} must not appear"
    assert "margin_basis" in src and "SPAN_UNVERIFIED" in src


# ════════════════════ ADVERSE FILL ════════════════════

def test_adverse_fill_uses_the_legs_real_traded_range(result):
    """Worst-case entry must come from prints, not an assumed spread."""
    t = result["trades"][0]
    a = adverse_fill_pnl(t)
    assert a is not None
    assert a["net_credit_points"] <= t.net_credit_points + 1e-9, \
        "selling the low and buying the high cannot improve the credit"
    for l in t.legs:
        assert l.entry_day_low <= l.entry_price <= l.entry_day_high, \
            "the close must sit inside its own session range"


def test_adverse_fill_refuses_without_a_usable_range():
    legs = [CondorLeg("short_call", "CE", "SELL", 100.0, "2026-01-01", "1", "X", 65,
                      10.0, 0.0, 5, 5, 0.0, entry_day_high=0.0, entry_day_low=0.0)]
    t = CondorTrade("2026-01-01", "2026-01-08", 5, 1.0, 1.0, 13.0, 50.0, 1.0, legs)
    assert adverse_fill_pnl(t) is None


# ════════════════════ VALIDATION MATHS ════════════════════

def test_clopper_pearson_matches_known_values():
    ci = V.clopper_pearson(0, 46)
    assert ci["lo"] == 0.0 and ci["hi"] == pytest.approx(0.0771, abs=5e-4)
    ci = V.clopper_pearson(1, 44)
    assert ci["hi"] == pytest.approx(0.1202, abs=5e-4)
    assert V.clopper_pearson(0, 0)["hi"] == 1.0


def test_breakeven_rate_reflects_the_payoff_asymmetry():
    be = V.breakeven_adverse_rate(800.0, -17000.0)
    assert be == pytest.approx(800.0 / 17800.0)
    assert V.breakeven_adverse_rate(800.0, 5.0) is None


def test_zero_losses_do_not_count_as_proof():
    """A 100% win rate on a small sample must not read as a demonstrated edge."""
    v = V.sample_size_verdict(46, 0, 0.0476)
    assert v["verdict"] == "NOT_DISTINGUISHABLE"
    assert v["adverse_ci95"][1] > 0.0476
    # With a genuinely large sample the same rate does become conclusive.
    assert V.sample_size_verdict(5000, 0, 0.0476)["verdict"] == "EDGE_DISTINGUISHABLE"


def test_trades_needed_is_finite_and_monotone():
    n = V.trades_needed(0.0476, 0.01)
    assert n and 10 <= n <= 20000
    assert V.trades_needed(0.0476, 0.06) is None, "an assumed rate above break-even is unreachable"


def test_slippage_sensitivity_is_monotonically_worse():
    pnl = [100.0] * 20
    out = V.slippage_sensitivity(pnl, [0.0, 50.0, 200.0])
    assert out[0]["net"] > out[1]["net"] > out[2]["net"]
    assert out[2]["still_profitable"] is False


def test_monte_carlo_preserves_total_pnl():
    pnl = [5.0, -3.0, 8.0, -1.0, 2.0, 7.0, -4.0]
    mc = V.monte_carlo_paths(pnl, n_paths=200)
    assert mc["final_pnl_mean"] == pytest.approx(sum(pnl))
    assert mc["max_drawdown_median"] <= 0


def test_resample_control_declares_what_it_cannot_show():
    out = V.resample_control([5.0, -3.0, 8.0, -1.0, 2.0, 7.0])
    assert "no evidence of entry-selection edge" in out["note"]


def test_multiple_testing_haircut_penalises_extra_variants():
    one = V.deflated_expectation(1, 2.5, 44)
    many = V.deflated_expectation(20, 2.5, 44)
    assert many["p_bonferroni"] > one["p_bonferroni"]
    assert many["variants_examined"] == 20

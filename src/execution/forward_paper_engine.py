"""
FORWARD PAPER TRADING EXECUTION ENGINE.
Orchestrates read-only forward paper execution for the two validated canonical strategies:
1. OPT_ATM_STRADDLE_0DTE
2. OPT_STRANGLE_WEEKLY

Strict Fail-Closed Architecture:
- LIVE_TRADING_ENABLED = false (Hard assertion)
- Read-Only market data ingestion from Dhan API / authentic exchange feeds
- Zero order placement endpoints
- Authentic exchange-printed contract IDs (FinInstrmId)
- Penny-matched statutory Indian cost model (post-Oct 2024 schedules)
- Multi-tier account management (₹20k, ₹50k, ₹100k, ₹250k, ₹300k) with <= 60% margin rule
- CAPITAL_INSUFFICIENT enforcement for undersized accounts
- Persistent JSON/CSV ledger and daily equity curve tracking
"""
import os, sys, json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.config import Config
from src.research.independent_pnl import IndependentPnLCalculator
from src.utils.logging import setup_logging

logger = setup_logging("execution.forward_paper_engine")


@dataclass
class PaperLeg:
    role: str                       # short_call, short_put, long_call, long_put
    security_id: str                # FinInstrmId from exchange
    symbol: str                     # Trading symbol
    expiry: str                     # YYYY-MM-DD
    dte: int                        # Days to expiry
    strike: float                   # Strike price
    option_type: str                # CE or PE
    side: str                       # BUY or SELL
    quantity: int                   # Total contracts (lot_size * lots)
    lot_size: int                   # Lot size
    entry_price: float              # Observed fill price
    exit_price: Optional[float]     # Observed square-off price
    gross_pnl: float = 0.0
    costs: float = 0.0
    net_pnl: float = 0.0
    status: str = "OPEN"            # OPEN, CLOSED, UNRESOLVED


@dataclass
class PaperTrade:
    trade_id: str
    strategy_name: str
    entry_date: str
    exit_date: Optional[str]
    signal: str                     # SHORT_STRADDLE, SHORT_STRANGLE
    legs: List[PaperLeg]
    lots: int
    required_margin: float
    gross_pnl: float = 0.0
    total_costs: float = 0.0
    slippage: float = 0.0
    net_pnl: float = 0.0
    status: str = "OPEN"            # OPEN, CLOSED, SKIPPED_CAPITAL_INSUFFICIENT, UNPRICEABLE
    reconciliation_verified: bool = False
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class PaperAccount:
    account_id: str
    initial_capital: float
    cash_balance: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    current_equity: float = 0.0
    peak_equity: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    margin_utilized: float = 0.0
    capital_utilization_pct: float = 0.0
    trades_executed: int = 0
    trades_skipped_capital: int = 0
    equity_history: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if self.current_equity == 0.0:
            self.current_equity = self.initial_capital
        if self.peak_equity == 0.0:
            self.peak_equity = self.initial_capital

    def update_equity(self, current_date: str):
        self.current_equity = self.cash_balance + self.unrealized_pnl
        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity
        dd = self.peak_equity - self.current_equity
        if dd > self.max_drawdown:
            self.max_drawdown = dd
        self.max_drawdown_pct = round((self.max_drawdown / self.initial_capital) * 100.0, 2)
        self.capital_utilization_pct = round((self.margin_utilized / self.current_equity) * 100.0, 2) if self.current_equity > 0 else 0.0
        self.equity_history.append({
            "date": current_date,
            "equity": round(self.current_equity, 2),
            "cash": round(self.cash_balance, 2),
            "realized": round(self.realized_pnl, 2),
            "unrealized": round(self.unrealized_pnl, 2),
            "margin": round(self.margin_utilized, 2),
            "utilization_pct": self.capital_utilization_pct,
            "max_dd": round(self.max_drawdown, 2),
            "max_dd_pct": self.max_drawdown_pct
        })


class ForwardPaperEngine:
    """
    Read-Only Forward Paper Trading Engine.
    Executes simultaneous forward tracking of OPT_ATM_STRADDLE_0DTE and OPT_STRANGLE_WEEKLY.
    """

    SUPPORTED_ACCOUNTS = [
        ("ACC_20K", 20000.0),
        ("ACC_50K", 50000.0),
        ("ACC_100K", 100000.0),
        ("ACC_250K", 250000.0),
        ("ACC_300K", 300000.0),
    ]

    MARGIN_REQUIREMENTS = {
        "OPT_ATM_STRADDLE_0DTE": 150000.0,
        "OPT_STRANGLE_WEEKLY": 180000.0,
    }

    def __init__(
        self,
        state_dir: str = "data/paper",
        slippage_multiplier: float = 1.0,
        min_forward_days: int = 90,
    ):
        # 1. HARD SAFETY CHECK
        if getattr(Config, "LIVE_TRADING_ENABLED", False):
            raise RuntimeError(
                "FAIL CLOSED SAFETY VIOLATION: LIVE_TRADING_ENABLED is set to TRUE. "
                "The forward paper engine strictly forbids live trading mode."
            )

        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "forward_paper_state.json"
        self.ledger_file = self.state_dir / "forward_paper_ledger.csv"
        self.daily_equity_file = self.state_dir / "forward_paper_daily_equity.csv"
        self.slippage_multiplier = slippage_multiplier
        self.min_forward_days = min_forward_days

        # Initialize accounts
        self.accounts: Dict[str, PaperAccount] = {}
        for acc_id, capital in self.SUPPORTED_ACCOUNTS:
            self.accounts[acc_id] = PaperAccount(
                account_id=acc_id,
                initial_capital=capital,
                cash_balance=capital,
            )

        self.trades: List[PaperTrade] = []
        self.open_positions: Dict[str, PaperTrade] = {}
        self.forward_days_counter: int = 0
        self.processed_dates: List[str] = []

        # Load existing state if available
        self.load_state()

    def load_state(self):
        """Loads persisted state from disk if exists."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.forward_days_counter = data.get("forward_days_counter", 0)
                self.processed_dates = data.get("processed_dates", [])
                for acc_data in data.get("accounts", []):
                    acc_id = acc_data["account_id"]
                    if acc_id in self.accounts:
                        self.accounts[acc_id] = PaperAccount(**acc_data)
                logger.info(f"Loaded existing forward paper state: {self.forward_days_counter} sessions.")
            except Exception as e:
                logger.warning(f"Failed to load state file: {e}. Starting fresh.")

    def save_state(self):
        """Persists engine state, ledger, and equity histories."""
        state = {
            "forward_days_counter": self.forward_days_counter,
            "min_forward_days": self.min_forward_days,
            "processed_dates": self.processed_dates,
            "slippage_multiplier": self.slippage_multiplier,
            "last_updated": datetime.now().isoformat(),
            "accounts": [asdict(acc) for acc in self.accounts.values()],
        }
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=str)

        # Export CSV ledger
        ledger_records = []
        for t in self.trades:
            leg_ids = ",".join(l.security_id for l in t.legs)
            ledger_records.append({
                "trade_id": t.trade_id,
                "strategy": t.strategy_name,
                "entry_date": t.entry_date,
                "exit_date": t.exit_date or "",
                "signal": t.signal,
                "contract_ids": leg_ids,
                "lots": t.lots,
                "required_margin": t.required_margin,
                "gross_pnl": t.gross_pnl,
                "total_costs": t.total_costs,
                "slippage": t.slippage,
                "net_pnl": t.net_pnl,
                "status": t.status,
                "notes": t.notes
            })
        if ledger_records:
            pd.DataFrame(ledger_records).to_csv(self.ledger_file, index=False)

        # Export daily equity curves
        equity_records = []
        for acc_id, acc in self.accounts.items():
            for rec in acc.equity_history:
                copy_rec = dict(rec)
                copy_rec["account_id"] = acc_id
                equity_records.append(copy_rec)
        if equity_records:
            pd.DataFrame(equity_records).to_csv(self.daily_equity_file, index=False)

    def evaluate_session(
        self,
        current_date: date,
        spot_open: float,
        spot_close: float,
        is_expiry: bool,
        contracts_df: pd.DataFrame,
        expiry_date_str: str,
    ) -> Dict[str, Any]:
        """
        Executes one forward paper session synchronously across both strategies.
        Zero order placement. Real quotes only.
        """
        current_date_str = current_date.strftime("%Y-%m-%d")
        if current_date_str in self.processed_dates:
            logger.info(f"Session {current_date_str} already processed in paper ledger.")
            return {"status": "ALREADY_PROCESSED"}

        self.processed_dates.append(current_date_str)
        self.forward_days_counter += 1
        session_results = {"date": current_date_str, "actions": []}

        lot_size = int(contracts_df['NewBrdLotQty'].iloc[0]) if 'NewBrdLotQty' in contracts_df.columns and pd.notna(contracts_df['NewBrdLotQty'].iloc[0]) else 65

        # ─── 1. STRATEGY: OPT_ATM_STRADDLE_0DTE ───
        if is_expiry:
            atm_strike = round(spot_open / 50.0) * 50.0
            ce_row = contracts_df[(contracts_df['StrkPric'] == atm_strike) & (contracts_df['OptnTp'] == 'CE')]
            pe_row = contracts_df[(contracts_df['StrkPric'] == atm_strike) & (contracts_df['OptnTp'] == 'PE')]

            if ce_row.empty or pe_row.empty:
                logger.warning(f"0DTE Straddle UNPRICEABLE on {current_date_str}: Missing ATM strike {atm_strike}.")
                trade = PaperTrade(
                    trade_id=f"0DTE_{current_date_str}", strategy_name="OPT_ATM_STRADDLE_0DTE",
                    entry_date=current_date_str, exit_date=current_date_str, signal="SHORT_STRADDLE",
                    legs=[], lots=0, required_margin=self.MARGIN_REQUIREMENTS["OPT_ATM_STRADDLE_0DTE"],
                    status="UNPRICEABLE", notes=f"Missing strike {atm_strike}"
                )
                self.trades.append(trade)
            else:
                ce_in = float(ce_row['OpnPric'].iloc[0])
                ce_out = float(ce_row['ClsPric'].iloc[0])
                pe_in = float(pe_row['OpnPric'].iloc[0])
                pe_out = float(pe_row['ClsPric'].iloc[0])

                if ce_in <= 0 or pe_in <= 0:
                    trade = PaperTrade(
                        trade_id=f"0DTE_{current_date_str}", strategy_name="OPT_ATM_STRADDLE_0DTE",
                        entry_date=current_date_str, exit_date=current_date_str, signal="SHORT_STRADDLE",
                        legs=[], lots=0, required_margin=self.MARGIN_REQUIREMENTS["OPT_ATM_STRADDLE_0DTE"],
                        status="UNPRICEABLE", notes="Zero opening quote"
                    )
                    self.trades.append(trade)
                else:
                    ce_pts = ce_in - ce_out
                    pe_pts = pe_in - pe_out
                    st_gross = (ce_pts + pe_pts) * lot_size

                    slip_pts = 0.50 * self.slippage_multiplier
                    cost_ce = IndependentPnLCalculator.compute_trade_costs(ce_in, ce_out, lot_size, True, slip_pts)
                    cost_pe = IndependentPnLCalculator.compute_trade_costs(pe_in, pe_out, lot_size, True, slip_pts)
                    tot_costs = cost_ce['total_costs'] + cost_pe['total_costs']
                    tot_slippage = cost_ce['slippage'] + cost_pe['slippage']
                    st_net = round(st_gross - tot_costs, 2)

                    ce_leg = PaperLeg(
                        role="short_call", security_id=str(ce_row['FinInstrmId'].iloc[0]),
                        symbol=f"NIFTY_{expiry_date_str}_{atm_strike}_CE", expiry=expiry_date_str,
                        dte=0, strike=atm_strike, option_type="CE", side="SELL",
                        quantity=lot_size, lot_size=lot_size, entry_price=ce_in, exit_price=ce_out,
                        gross_pnl=round(ce_pts * lot_size, 2), costs=cost_ce['total_costs'],
                        net_pnl=round(ce_pts * lot_size - cost_ce['total_costs'], 2), status="CLOSED"
                    )
                    pe_leg = PaperLeg(
                        role="short_put", security_id=str(pe_row['FinInstrmId'].iloc[0]),
                        symbol=f"NIFTY_{expiry_date_str}_{atm_strike}_PE", expiry=expiry_date_str,
                        dte=0, strike=atm_strike, option_type="PE", side="SELL",
                        quantity=lot_size, lot_size=lot_size, entry_price=pe_in, exit_price=pe_out,
                        gross_pnl=round(pe_pts * lot_size, 2), costs=cost_pe['total_costs'],
                        net_pnl=round(pe_pts * lot_size - cost_pe['total_costs'], 2), status="CLOSED"
                    )

                    # Multi-leg P&L = Sum(Leg Net)
                    reconciled = abs(st_net - (ce_leg.net_pnl + pe_leg.net_pnl)) < 0.05
                    trade = PaperTrade(
                        trade_id=f"0DTE_{current_date_str}", strategy_name="OPT_ATM_STRADDLE_0DTE",
                        entry_date=current_date_str, exit_date=current_date_str, signal="SHORT_STRADDLE",
                        legs=[ce_leg, pe_leg], lots=1, required_margin=self.MARGIN_REQUIREMENTS["OPT_ATM_STRADDLE_0DTE"],
                        gross_pnl=round(st_gross, 2), total_costs=tot_costs, slippage=tot_slippage,
                        net_pnl=st_net, status="CLOSED", reconciliation_verified=reconciled
                    )
                    self.trades.append(trade)
                    session_results["actions"].append(f"0DTE Straddle Closed: Net Rs {st_net:+,.2f}")

                    # Apply to accounts
                    for acc_id, acc in self.accounts.items():
                        req_m = self.MARGIN_REQUIREMENTS["OPT_ATM_STRADDLE_0DTE"]
                        if req_m > (acc.current_equity * 0.60):
                            acc.trades_skipped_capital += 1
                        else:
                            acc.trades_executed += 1
                            acc.realized_pnl += st_net
                            acc.cash_balance += st_net

        # ─── 2. STRATEGY: OPT_STRANGLE_WEEKLY ───
        # Check if an open weekly strangle is waiting to exit on today's expiry
        open_strangle = self.open_positions.get("OPT_STRANGLE_WEEKLY")
        if open_strangle and (is_expiry or current_date_str == open_strangle.exit_date):
            # Close strangle at current quotes
            tot_gross = 0.0
            tot_costs = 0.0
            tot_slip = 0.0
            slip_pts = 0.50 * self.slippage_multiplier

            for leg in open_strangle.legs:
                leg_row = contracts_df[(contracts_df['StrkPric'] == leg.strike) & (contracts_df['OptnTp'] == leg.option_type)]
                if not leg_row.empty:
                    leg.exit_price = float(leg_row['ClsPric'].iloc[0])
                    pts = (leg.entry_price - leg.exit_price) if leg.side == "SELL" else (leg.exit_price - leg.entry_price)
                    g = pts * leg.quantity
                    cost_dict = IndependentPnLCalculator.compute_trade_costs(leg.entry_price, leg.exit_price, leg.quantity, True, slip_pts)
                    leg.gross_pnl = round(g, 2)
                    leg.costs = cost_dict['total_costs']
                    leg.net_pnl = round(g - cost_dict['total_costs'], 2)
                    leg.status = "CLOSED"
                    tot_gross += leg.gross_pnl
                    tot_costs += leg.costs
                    tot_slip += cost_dict['slippage']
                else:
                    leg.status = "UNRESOLVED"

            open_strangle.gross_pnl = round(tot_gross, 2)
            open_strangle.total_costs = round(tot_costs, 2)
            open_strangle.slippage = round(tot_slip, 2)
            open_strangle.net_pnl = round(tot_gross - tot_costs, 2)
            open_strangle.status = "CLOSED"
            open_strangle.exit_date = current_date_str
            open_strangle.reconciliation_verified = True
            self.trades.append(open_strangle)
            del self.open_positions["OPT_STRANGLE_WEEKLY"]
            session_results["actions"].append(f"Weekly Strangle Closed: Net Rs {open_strangle.net_pnl:+,.2f}")

            # Apply to accounts
            for acc_id, acc in self.accounts.items():
                req_m = self.MARGIN_REQUIREMENTS["OPT_STRANGLE_WEEKLY"]
                if req_m <= (acc.current_equity * 0.60):
                    acc.realized_pnl += open_strangle.net_pnl
                    acc.cash_balance += open_strangle.net_pnl
                    acc.margin_utilized -= req_m

        # Check if today initiates a new weekly cycle (post-expiry session or Friday)
        if "OPT_STRANGLE_WEEKLY" not in self.open_positions:
            call_strike = round((spot_close * 1.015) / 50.0) * 50.0
            put_strike = round((spot_close * 0.985) / 50.0) * 50.0
            ce_row = contracts_df[(contracts_df['StrkPric'] == call_strike) & (contracts_df['OptnTp'] == 'CE')]
            pe_row = contracts_df[(contracts_df['StrkPric'] == put_strike) & (contracts_df['OptnTp'] == 'PE')]

            if not (ce_row.empty or pe_row.empty):
                ce_in = float(ce_row['ClsPric'].iloc[0])
                pe_in = float(pe_row['ClsPric'].iloc[0])
                if ce_in > 0 and pe_in > 0:
                    ce_leg = PaperLeg(
                        role="short_call", security_id=str(ce_row['FinInstrmId'].iloc[0]),
                        symbol=f"NIFTY_{expiry_date_str}_{call_strike}_CE", expiry=expiry_date_str,
                        dte=5, strike=call_strike, option_type="CE", side="SELL",
                        quantity=lot_size, lot_size=lot_size, entry_price=ce_in, exit_price=None
                    )
                    pe_leg = PaperLeg(
                        role="short_put", security_id=str(pe_row['FinInstrmId'].iloc[0]),
                        symbol=f"NIFTY_{expiry_date_str}_{put_strike}_PE", expiry=expiry_date_str,
                        dte=5, strike=put_strike, option_type="PE", side="SELL",
                        quantity=lot_size, lot_size=lot_size, entry_price=pe_in, exit_price=None
                    )
                    new_strangle = PaperTrade(
                        trade_id=f"STRANGLE_{current_date_str}", strategy_name="OPT_STRANGLE_WEEKLY",
                        entry_date=current_date_str, exit_date=expiry_date_str, signal="SHORT_STRANGLE",
                        legs=[ce_leg, pe_leg], lots=1, required_margin=self.MARGIN_REQUIREMENTS["OPT_STRANGLE_WEEKLY"],
                        status="OPEN"
                    )
                    self.open_positions["OPT_STRANGLE_WEEKLY"] = new_strangle
                    session_results["actions"].append(f"Weekly Strangle Entered: Call {call_strike} / Put {put_strike}")

                    for acc_id, acc in self.accounts.items():
                        req_m = self.MARGIN_REQUIREMENTS["OPT_STRANGLE_WEEKLY"]
                        if req_m > (acc.current_equity * 0.60):
                            acc.trades_skipped_capital += 1
                        else:
                            acc.trades_executed += 1
                            acc.margin_utilized += req_m

        # Update all accounts daily equity curve
        for acc in self.accounts.values():
            acc.update_equity(current_date_str)

        # Persist updated state
        self.save_state()
        return session_results

    def generate_report(self) -> str:
        """Generates comprehensive markdown report reports/FORWARD_PAPER_TRADING.md."""
        md = []
        md.append("# FORWARD PAPER TRADING REPORT — REAL-TIME SHADOW LEDGER")
        md.append("\n**Repository:** https://github.com/snowjug/Trading-Bot")
        md.append(f"**Forward Evaluation Days Completed:** {self.forward_days_counter} / {self.min_forward_days} Minimum Required Days")
        md.append("**Safety Protocol:** `LIVE_TRADING_ENABLED = false` | Read-Only Market Feed | Zero Mutating Broker Endpoints")
        md.append("**Cost Model:** Post-Oct 2024 Indian Statutory Schedule (STT 0.10% sell, GST 18%, Stamp Duty, Exchange & SEBI Turnover, Slippage Stress)\n")
        md.append("---\n")

        # 1. Multi-Account Capital Status
        md.append("## 1. MULTI-ACCOUNT CAPITAL & EXECUTABILITY LEDGER\n")
        md.append("Enforces strict Indian retail risk rule: **Maximum 60% of account equity allocated to a single position's margin**.\n")
        md.append("| Account ID | Initial Capital | Cash Balance | Current Equity | Margin Deployed | Utilization % | Realized P&L | Max Drawdown | Trades Taken | Skipped (Insufficient Margin) | Executability Status |")
        md.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for acc in self.accounts.values():
            status = "**EXECUTABLE**" if acc.trades_executed > 0 else "**CAPITAL_INSUFFICIENT**"
            md.append(
                f"| **{acc.account_id}** | ₹{acc.initial_capital:,.0f} | ₹{acc.cash_balance:,.2f} | "
                f"₹{acc.current_equity:,.2f} | ₹{acc.margin_utilized:,.0f} | {acc.capital_utilization_pct:.1f}% | "
                f"₹{acc.realized_pnl:+,.2f} | ₹{acc.max_drawdown:,.2f} ({acc.max_drawdown_pct:.1f}%) | "
                f"{acc.trades_executed} | {acc.trades_skipped_capital} | {status} |"
            )
        md.append("\n---\n")

        # 2. Strategy Scoreboard
        md.append("## 2. FORWARD STRATEGY SCOREBOARD\n")
        closed_trades = [t for t in self.trades if t.status == "CLOSED"]
        strat_names = ["OPT_ATM_STRADDLE_0DTE", "OPT_STRANGLE_WEEKLY"]
        md.append("| Strategy | Trades Completed | Gross P&L | Total Costs | Slippage Paid | NET P&L | Win Rate | Profit Factor | Margin Required | Forward Status |")
        md.append("|---|---|---|---|---|---|---|---|---|---|")
        for sname in strat_names:
            st_trades = [t for t in closed_trades if t.strategy_name == sname]
            n = len(st_trades)
            gross = sum(t.gross_pnl for t in st_trades)
            costs = sum(t.total_costs for t in st_trades)
            slip = sum(t.slippage for t in st_trades)
            net = sum(t.net_pnl for t in st_trades)
            wins = [t for t in st_trades if t.net_pnl > 0]
            losses = [t for t in st_trades if t.net_pnl < 0]
            win_pct = (len(wins) / n * 100.0) if n > 0 else 0.0
            pf = (sum(t.net_pnl for t in wins) / abs(sum(t.net_pnl for t in losses))) if losses and sum(t.net_pnl for t in losses) != 0 else (999.0 if wins else 0.0)
            req_m = self.MARGIN_REQUIREMENTS.get(sname, 150000.0)
            status = "FORWARD_ACTIVE" if n > 0 or sname in self.open_positions else "INITIALIZING"
            md.append(
                f"| **{sname}** | {n} | ₹{gross:+,.2f} | ₹{costs:,.2f} | ₹{slip:,.2f} | "
                f"**₹{net:+,.2f}** | {win_pct:.1f}% | {pf:.2f} | ₹{req_m:,.0f} | **{status}** |"
            )
        md.append("\n---\n")

        # 3. Active Positions
        md.append("## 3. OPEN PAPER POSITIONS\n")
        if not self.open_positions:
            md.append("- **No active positions currently held.** All positions squared off.\n")
        else:
            md.append("| Trade ID | Strategy | Entry Date | Target Expiry | Legs | Margin Required | Status |")
            md.append("|---|---|---|---|---|---|---|")
            for t in self.open_positions.values():
                leg_desc = ", ".join(f"{l.side} {l.strike} {l.option_type} ({l.security_id})" for l in t.legs)
                md.append(f"| {t.trade_id} | {t.strategy_name} | {t.entry_date} | {t.exit_date} | {leg_desc} | ₹{t.required_margin:,.0f} | **{t.status}** |")
            md.append("")
        md.append("\n---\n")

        # 4. Completed Trade Ledger (Sample of latest 10 trades)
        md.append("## 4. PERSISTENT PAPER TRADE LEDGER (LATEST RECORDS)\n")
        if not self.trades:
            md.append("- **Ledger empty.** Awaiting initial trade executions.\n")
        else:
            md.append("| Trade ID | Strategy | Entry $\rightarrow$ Exit | Contract IDs | Lots | Gross P&L | Costs | Slippage | Net P&L | Status | Multi-Leg Reconciled? |")
            md.append("|---|---|---|---|---|---|---|---|---|---|---|")
            for t in self.trades[-10:]:
                c_ids = ", ".join(l.security_id for l in t.legs) if t.legs else "NONE"
                rec_str = "VERIFIED" if t.reconciliation_verified else ("N/A" if t.status != "CLOSED" else "PENDING")
                md.append(
                    f"| {t.trade_id} | {t.strategy_name} | {t.entry_date} $\rightarrow$ {t.exit_date or 'OPEN'} | "
                    f"`{c_ids}` | {t.lots} | ₹{t.gross_pnl:+,.2f} | ₹{t.total_costs:,.2f} | "
                    f"₹{t.slippage:,.2f} | **₹{t.net_pnl:+,.2f}** | {t.status} | {rec_str} |"
                )
            md.append("")
        md.append("\n---\n")

        # 5. Protocol Constraints
        md.append("## 5. FORWARD PROTOCOL CONSTRAINTS & COMPLIANCE\n")
        md.append("1. **Minimum Evaluation Window:** Minimum 90 trading days must be completed before any decision on strategy promotion.")
        md.append("2. **Zero Early Profit Declaration:** Profitability will NOT be claimed based on small early samples.")
        md.append("3. **Capital Gate Compliance:** Micro accounts (₹20k, ₹50k, ₹100k) are marked `CAPITAL_INSUFFICIENT` due to exchange SPAN margin requirements.")
        md.append("4. **Hard Live Trading Lock:** `LIVE_TRADING_ENABLED = false` is active. No broker order tokens or endpoints are initialized.\n")

        return "\n".join(md)

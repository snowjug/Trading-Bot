"""
Authentic option-chain access. Resolves and prices legs, or refuses.

The one rule this module exists to enforce: **a leg is priced from a bar that
actually traded, or it is not priced at all.** There is no interpolation, no
Black-Scholes fallback, no fixed delta, no "nearest available" strike substitution
and no carried-forward stale quote. A leg that cannot be priced makes its whole
structure UNPRICEABLE, and the caller records that rather than filling it.

Two sources, both authentic:

  ReplayChain    the 5-minute option grid (Dhan `/charts/rollingoption`), which
                 carries per-strike traded OHLC with volume, OI and IV. Covers
                 ATM+-6, which is the vendor's ladder ceiling and is recorded as
                 such — a structure needing a strike outside it is UNPRICEABLE, not
                 approximated.

  LiveChain      the live read-only option chain, which carries top bid/ask so the
                 spread is measured rather than assumed.

Historical bid/ask does not exist anywhere in this repository, so ReplayChain
models execution as `traded price +- (half-spread + slippage)` and says so. That is
a modelling choice, stated, not a data claim.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, time as dtime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.options.structures import Leg
from src.risk.structure_risk import PricedLeg

TICK = 0.05
DEFAULT_SPREAD_PCT = 0.0030      # half-spread per side when bid/ask is unavailable
DEFAULT_SLIP_TICKS = 2


@dataclass(frozen=True)
class Quote:
    strike: float
    option_type: str
    price: float                 # traded price (replay) or mid (live)
    volume: float
    oi: Optional[float] = None
    iv: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    source: str = ""
    observed_at: Optional[datetime] = None

    @property
    def spread_pct(self) -> Optional[float]:
        """Measured spread as a fraction of mid, or None when bid/ask is absent."""
        if self.bid is None or self.ask is None:
            return None
        if self.bid <= 0 or self.ask <= 0 or self.ask < self.bid:
            return None
        mid = (self.bid + self.ask) / 2.0
        return None if mid <= 0 else float((self.ask - self.bid) / mid)


def fill_price(q: Quote, side: str, spread_pct: float = DEFAULT_SPREAD_PCT,
               slip_ticks: float = DEFAULT_SLIP_TICKS, mult: float = 1.0) -> float:
    """
    The price actually paid or received, always in the direction that costs money.

    When real bid/ask exists we cross it: a BUY pays the ask, a SELL receives the bid,
    plus slippage. Otherwise the traded price is penalised by a modelled half-spread.
    """
    if q.bid is not None and q.ask is not None and q.bid > 0 and q.ask >= q.bid:
        base = q.ask if side == "BUY" else q.bid
        slip = slip_ticks * TICK * mult
        return max(TICK, base + slip) if side == "BUY" else max(TICK, base - slip)
    pen = max(TICK, q.price * spread_pct) * mult + slip_ticks * TICK * mult
    return (q.price + pen) if side == "BUY" else max(TICK, q.price - pen)


class ReplayChain:
    """
    The 5-minute option grid, indexed for point-in-time lookup.

    `price_legs` returns either a full list of `PricedLeg` or None with a reason. It
    never returns a partial structure: a spread with one leg priced is not a spread.
    """

    def __init__(self, ce_path: str, pe_path: str, ladder_half_width: int = 6):
        self.ladder_half_width = int(ladder_half_width)
        cols = ["datetime", "sess", "strike", "close", "volume", "oi", "iv", "spot"]
        frames = {}
        for side, path in (("CE", ce_path), ("PE", pe_path)):
            d = pd.read_parquet(path, columns=[c for c in cols])
            d["t"] = d["datetime"].dt.time
            frames[side] = d
        self._idx: Dict[Tuple[date, dtime, str, float], Tuple[float, float, float, float]] = {}
        for side, d in frames.items():
            for sess, t, k, c, v, oi, iv in zip(d["sess"], d["t"], d["strike"],
                                                d["close"], d["volume"],
                                                d.get("oi", pd.Series([np.nan] * len(d))),
                                                d.get("iv", pd.Series([np.nan] * len(d)))):
                self._idx[(sess, t, side, float(k))] = (float(c), float(v),
                                                        float(oi), float(iv))
        self._spot: Dict[Tuple[date, dtime], float] = {}
        for side, d in frames.items():
            for sess, t, s in zip(d["sess"], d["t"], d["spot"]):
                self._spot.setdefault((sess, t), float(s))
        self.sessions = sorted({k[0] for k in self._spot})

    def spot(self, sess: date, t: dtime) -> Optional[float]:
        return self._spot.get((sess, t))

    def quote(self, sess: date, t: dtime, option_type: str, strike: float
              ) -> Optional[Quote]:
        r = self._idx.get((sess, t, option_type, float(strike)))
        if r is None:
            return None
        px, vol, oi, iv = r
        if not np.isfinite(px) or px <= 0:
            return None
        return Quote(strike=float(strike), option_type=option_type, price=px,
                     volume=vol, oi=(oi if np.isfinite(oi) else None),
                     iv=(iv if np.isfinite(iv) else None),
                     source="REPLAY_GRID_5M",
                     observed_at=datetime.combine(sess, t))

    def atm_straddle(self, sess: date, t: dtime) -> Optional[float]:
        """ATM straddle price, for the options-volatility setup family."""
        s = self.spot(sess, t)
        if s is None:
            return None
        k = round(s / 50.0) * 50.0
        ce, pe = self.quote(sess, t, "CE", k), self.quote(sess, t, "PE", k)
        if ce is None or pe is None:
            return None
        return float(ce.price + pe.price)

    def price_legs(self, legs: List[Leg], sess: date, t: dtime,
                   cost_mult: float = 1.0, min_volume: float = 1.0
                   ) -> Tuple[Optional[List[PricedLeg]], str]:
        """
        Price every leg, or refuse and say why.

        The ladder check is explicit: a strike beyond the vendor's ATM+-N window is
        reported as OUTSIDE_LADDER rather than silently dropped, because the sessions
        where wide strikes are missing are exactly the volatile ones, and dropping
        them is how a backtest invents an edge.
        """
        s = self.spot(sess, t)
        if s is None:
            return None, "NO_SPOT_AT_TIME"
        atm = round(s / 50.0) * 50.0
        out: List[PricedLeg] = []
        for L in legs:
            steps = abs(int(round((L.strike - atm) / 50.0)))
            if steps > self.ladder_half_width:
                return None, (f"OUTSIDE_LADDER:{L.option_type}{L.strike:.0f}"
                              f"(ATM{steps:+d} > +-{self.ladder_half_width})")
            q = self.quote(sess, t, L.option_type, L.strike)
            if q is None:
                return None, f"NO_QUOTE:{L.option_type}{L.strike:.0f}"
            if q.volume < min_volume:
                return None, f"NO_VOLUME:{L.option_type}{L.strike:.0f}"
            out.append(PricedLeg(leg=L, price=q.price,
                                 fill=round(fill_price(q, L.side, mult=cost_mult), 2),
                                 volume=q.volume, spread_pct=q.spread_pct))
        return out, "OK"

    def settle_intrinsic(self, legs: List[Leg], settle: float) -> float:
        """Net amount owed at expiry, exactly, from the official settlement value."""
        tot = 0.0
        for L in legs:
            intr = (max(0.0, settle - L.strike) if L.option_type == "CE"
                    else max(0.0, L.strike - settle))
            tot += (-L.qty_sign) * intr
        return float(tot)


class LiveChain:
    """
    Live read-only chain wrapper. Carries real bid/ask, so spreads are measured.

    Used by the paper executor so that paper and any future sandbox run share one
    pricing path. It performs no order action of any kind.
    """

    def __init__(self, client, underlying_scrip: int = 13,
                 underlying_seg: str = "IDX_I", strike_step: float = 50.0):
        self.client = client
        self.scrip = int(underlying_scrip)
        self.seg = underlying_seg
        self.step = float(strike_step)
        self._snap: Optional[Dict[str, Any]] = None
        self._snap_at: Optional[datetime] = None

    def refresh(self, expiry: Optional[str] = None) -> bool:
        try:
            snap = self.client.fetch_option_chain(self.scrip, self.seg, expiry)
        except Exception:                                      # noqa: BLE001
            return False
        if not snap or not snap.get("strikes"):
            return False
        self._snap, self._snap_at = snap, datetime.now()
        return True

    @property
    def age_seconds(self) -> Optional[float]:
        if self._snap_at is None:
            return None
        return (datetime.now() - self._snap_at).total_seconds()

    def spot(self) -> Optional[float]:
        if not self._snap:
            return None
        v = self._snap.get("spot_last_price")
        return float(v) if v else None

    def quote(self, option_type: str, strike: float) -> Optional[Quote]:
        if not self._snap:
            return None
        oc = self._snap.get("strikes") or {}
        key = f"{float(strike):.6f}"
        row = oc.get(key) or oc.get(str(float(strike))) or oc.get(str(int(strike)))
        if not row:
            return None
        leg = row.get("ce" if option_type == "CE" else "pe") or {}
        ltp = leg.get("last_price")
        if not ltp or float(ltp) <= 0:
            return None
        return Quote(strike=float(strike), option_type=option_type, price=float(ltp),
                     volume=float(leg.get("volume") or 0.0),
                     oi=(float(leg["oi"]) if leg.get("oi") is not None else None),
                     iv=(float(leg["implied_volatility"])
                         if leg.get("implied_volatility") is not None else None),
                     bid=(float(leg["top_bid_price"])
                          if leg.get("top_bid_price") else None),
                     ask=(float(leg["top_ask_price"])
                          if leg.get("top_ask_price") else None),
                     source="DHAN_OPTION_CHAIN", observed_at=self._snap_at)

    def price_legs(self, legs: List[Leg], cost_mult: float = 1.0,
                   min_volume: float = 1.0) -> Tuple[Optional[List[PricedLeg]], str]:
        out: List[PricedLeg] = []
        for L in legs:
            q = self.quote(L.option_type, L.strike)
            if q is None:
                return None, f"NO_QUOTE:{L.option_type}{L.strike:.0f}"
            if q.volume < min_volume:
                return None, f"NO_VOLUME:{L.option_type}{L.strike:.0f}"
            out.append(PricedLeg(leg=L, price=q.price,
                                 fill=round(fill_price(q, L.side, mult=cost_mult), 2),
                                 volume=q.volume, spread_pct=q.spread_pct))
        return out, "OK"

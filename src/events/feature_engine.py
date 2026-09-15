"""
Event Feature Engine for Indian Financial Markets.
Transforms unstructured news & corporate actions into structured, quantifiable features.
Extracts: directional_score, sentiment_score, confidence, surprise_score, importance, event_type.
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import re

from src.events.collector import MarketEvent
from src.utils.logging import get_logger

logger = get_logger("events.features")


@dataclass
class EventFeature:
    event_id: str
    event_timestamp: datetime
    available_at: datetime
    symbol: Optional[str]
    sector: Optional[str]
    event_type: str
    directional_score: float  # -1.0 (bearish) to +1.0 (bullish)
    sentiment_score: float    # -1.0 to +1.0
    confidence: float         # 0.0 to 1.0
    surprise_score: float     # 0.0 to 1.0
    importance: float         # 0.0 to 1.0
    novelty: float            # 0.0 to 1.0
    summary: str

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["event_timestamp"] = self.event_timestamp.isoformat()
        d["available_at"] = self.available_at.isoformat()
        return d


class EventFeatureEngine:
    """Parses events into structured numerical features for quantitative modeling."""

    # Lexicon for directional sentiment in Indian market context
    BULLISH_KEYWORDS = [
        "beat", "profit surges", "profit jumps", "revenue up", "order win",
        "bags contract", "dividend declared", "bonus issue", "expansion",
        "guidance raised", "approval granted", "rate cut", "target raised",
        "upgrade", "record high", "outperform", "buy rating", "strong demand",
        "capex", "turnaround", "debt reduction", "growth acceleration"
    ]

    BEARISH_KEYWORDS = [
        "miss", "profit falls", "profit drops", "loss widens", "penalty",
        "regulatory restriction", "ban", "sebi order", "fraud", "probe",
        "resignation", "guidance cut", "downgrade", "target cut", "sell rating",
        "default", "rate hike", "inflation surges", "margin squeeze", "strike",
        "recall", "investigation", "slump", "drags"
    ]

    EVENT_PATTERNS = {
        "EARNINGS_BEAT": [r"profit surges", r"profit jumps", r"beats estimates", r"net jumps", r"q[1-4] profit up"],
        "EARNINGS_MISS": [r"profit falls", r"misses estimates", r"q[1-4] loss", r"profit drops", r"margin contraction"],
        "DIVIDEND": [r"interim dividend", r"final dividend", r"special dividend"],
        "ORDER_WIN": [r"bags order", r"wins contract", r"secures order", r"awarded contract"],
        "REGULATORY": [r"sebi", r"rbi", r"cci", r"penalty", r"show cause", r"enforcement"],
        "MANAGEMENT_CHANGE": [r"resigns", r"appointed as ceo", r"managing director steps down"],
        "RBI_POLICY": [r"repo rate", r"rbi mpc", r"monetary policy", r"shaktikanta das", r"interest rate"],
        "BUDGET_MACRO": [r"union budget", r"fiscal deficit", r"capex outlay", r"fm nirmala"],
    }

    NIFTY_SYMBOLS = {
        "RELIANCE": ["reliance", "ril", "jio"],
        "TCS": ["tcs", "tata consultancy"],
        "HDFCBANK": ["hdfc bank", "hdfc"],
        "INFY": ["infosys", "infy"],
        "ICICIBANK": ["icici bank", "icici"],
        "SBIN": ["sbi", "state bank of india"],
        "BHARTIARTL": ["bharti airtel", "airtel"],
        "ITC": ["itc"],
        "KOTAKBANK": ["kotak mahindra", "kotak bank"],
        "LT": ["l&t", "larsen & toubro", "larsen"],
        "AXISBANK": ["axis bank"],
        "WIPRO": ["wipro"],
        "HCLTECH": ["hcl tech", "hcl technologies"],
        "MARUTI": ["maruti", "maruti suzuki"],
        "BAJFINANCE": ["bajaj finance"],
        "TATASTEEL": ["tata steel"],
    }

    def extract_symbol(self, text: str) -> Optional[str]:
        text_lower = text.lower()
        for sym, aliases in self.NIFTY_SYMBOLS.items():
            for alias in aliases:
                if re.search(rf"\b{re.escape(alias)}\b", text_lower):
                    return sym
        return None

    def classify_event(self, text: str) -> Tuple[str, float]:
        text_lower = text.lower()
        for event_type, patterns in self.EVENT_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, text_lower):
                    importance = 0.8 if event_type in ["EARNINGS_BEAT", "EARNINGS_MISS", "REGULATORY", "RBI_POLICY"] else 0.5
                    return event_type, importance
        return "GENERAL_NEWS", 0.3

    def compute_sentiment(self, text: str) -> Tuple[float, float]:
        text_lower = text.lower()
        bull_count = sum(1 for kw in self.BULLISH_KEYWORDS if kw in text_lower)
        bear_count = sum(1 for kw in self.BEARISH_KEYWORDS if kw in text_lower)

        total = bull_count + bear_count
        if total == 0:
            return 0.0, 0.2

        score = (bull_count - bear_count) / total
        confidence = min(1.0, 0.4 + (total * 0.15))
        return score, confidence

    def process_event(self, event: MarketEvent) -> EventFeature:
        combined_text = f"{event.title} {event.summary}"
        symbol = event.symbol or self.extract_symbol(combined_text)
        event_type, importance = self.classify_event(combined_text)
        sentiment, confidence = self.compute_sentiment(combined_text)

        # Directional score integrates sentiment with event type
        directional = sentiment
        if event_type == "EARNINGS_BEAT":
            directional = max(directional, 0.6)
            importance = max(importance, 0.8)
        elif event_type == "EARNINGS_MISS":
            directional = min(directional, -0.6)
            importance = max(importance, 0.8)
        elif event_type == "ORDER_WIN":
            directional = max(directional, 0.5)
        elif event_type == "REGULATORY" and sentiment < 0:
            directional = -0.7
            importance = 0.9

        # Ensure point-in-time enforcement: available_at >= published_at
        available_at = max(event.retrieved_at, event.published_at)

        return EventFeature(
            event_id=event.event_id,
            event_timestamp=event.published_at,
            available_at=available_at,
            symbol=symbol,
            sector=event.sector or "ALL",
            event_type=event_type,
            directional_score=round(directional, 3),
            sentiment_score=round(sentiment, 3),
            confidence=round(confidence, 3),
            surprise_score=0.5,  # Baseline neutral surprise
            importance=round(importance, 3),
            novelty=0.8,
            summary=event.title[:150],
        )

    def process_batch(self, events: List[MarketEvent]) -> List[EventFeature]:
        return [self.process_event(ev) for ev in events]

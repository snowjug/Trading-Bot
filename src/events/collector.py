"""
Event & News Collector for Indian Markets.
Collects corporate announcements, RBI press releases, and financial news feeds
with strict point-in-time timestamp tagging.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, date
from typing import List, Dict, Optional
import feedparser
import requests
import json
import logging
from pathlib import Path

from src.config import Config
from src.utils.logging import get_logger

logger = get_logger("events.collector")


@dataclass
class MarketEvent:
    event_id: str
    published_at: datetime
    retrieved_at: datetime
    source: str
    title: str
    summary: str
    symbol: Optional[str] = None
    sector: Optional[str] = None
    url: Optional[str] = None
    raw_payload: Optional[str] = None

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["published_at"] = self.published_at.isoformat()
        d["retrieved_at"] = self.retrieved_at.isoformat()
        return d


class NewsEventCollector:
    """Collects news and announcements from public RSS and web endpoints."""

    DEFAULT_FEEDS = {
        "moneycontrol_market": "https://www.moneycontrol.com/rss/marketreports.xml",
        "moneycontrol_buzz": "https://www.moneycontrol.com/rss/buzzingstocks.xml",
        "economic_times_markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "economic_times_stocks": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
        "livemint_markets": "https://www.livemint.com/rss/markets",
    }

    # Known scheduled calendar events in Indian markets
    CALENDAR_EVENTS = [
        {"title": "Union Budget 2024", "date": "2024-02-01", "type": "BUDGET", "importance": 1.0},
        {"title": "Union Budget 2024 (Post-Election)", "date": "2024-07-23", "type": "BUDGET", "importance": 1.0},
        {"title": "RBI MPC Policy Rate Decision", "date": "2024-02-08", "type": "RBI_RATE", "importance": 0.9},
        {"title": "RBI MPC Policy Rate Decision", "date": "2024-04-05", "type": "RBI_RATE", "importance": 0.9},
        {"title": "RBI MPC Policy Rate Decision", "date": "2024-06-07", "type": "RBI_RATE", "importance": 0.9},
        {"title": "RBI MPC Policy Rate Decision", "date": "2024-08-08", "type": "RBI_RATE", "importance": 0.9},
        {"title": "RBI MPC Policy Rate Decision", "date": "2024-10-09", "type": "RBI_RATE", "importance": 0.9},
        {"title": "RBI MPC Policy Rate Decision", "date": "2024-12-06", "type": "RBI_RATE", "importance": 0.9},
        {"title": "RBI MPC Policy Rate Decision", "date": "2025-02-07", "type": "RBI_RATE", "importance": 0.9},
    ]

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or (Config.DATA_DIR / "news")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def fetch_rss_feed(self, feed_name: str, feed_url: str) -> List[MarketEvent]:
        """Fetch and parse an RSS feed with strict timestamping."""
        events = []
        try:
            logger.info(f"Fetching RSS feed: {feed_name} ({feed_url})")
            feed = feedparser.parse(feed_url)
            retrieved_at = datetime.now()

            for entry in feed.entries:
                pub_time = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        pub_time = datetime(*entry.published_parsed[:6])
                    except Exception:
                        pass

                if pub_time is None:
                    pub_time = retrieved_at

                event = MarketEvent(
                    event_id=f"{feed_name}_{hash(entry.link if hasattr(entry, 'link') else entry.title)}",
                    published_at=pub_time,
                    retrieved_at=retrieved_at,
                    source=feed_name,
                    title=entry.title if hasattr(entry, "title") else "",
                    summary=entry.summary if hasattr(entry, "summary") else "",
                    url=entry.link if hasattr(entry, "link") else None,
                )
                events.append(event)

            logger.info(f"Collected {len(events)} events from {feed_name}")
        except Exception as e:
            logger.warning(f"Failed to fetch RSS {feed_name}: {e}")

        return events

    def fetch_all_active_feeds(self) -> List[MarketEvent]:
        """Fetch all configured news feeds."""
        all_events = []
        for name, url in self.DEFAULT_FEEDS.items():
            evs = self.fetch_rss_feed(name, url)
            all_events.extend(evs)
        return all_events

    def get_macro_calendar_events(self) -> List[MarketEvent]:
        """Get known Indian macroeconomic and policy events."""
        events = []
        retrieved_at = datetime.now()
        for idx, item in enumerate(self.CALENDAR_EVENTS):
            pub_date = datetime.strptime(item["date"], "%Y-%m-%d")
            ev = MarketEvent(
                event_id=f"macro_{idx}_{item['date']}",
                published_at=pub_date,
                retrieved_at=retrieved_at,
                source="CALENDAR",
                title=item["title"],
                summary=f"Indian Macro Calendar Event: {item['type']}",
                sector="MACRO",
            )
            events.append(ev)
        return events

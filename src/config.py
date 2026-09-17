"""
Configuration management for the research platform.
Loads settings from .env and provides typed access.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Config:
    """Central configuration — reads from environment variables."""

    # SAFETY GATE
    LIVE_TRADING_ENABLED: bool = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"

    # Database
    DUCKDB_PATH: str = os.getenv("DUCKDB_PATH", "data/research.duckdb")

    # Research
    DEFAULT_UNIVERSE: str = os.getenv("DEFAULT_UNIVERSE", "NIFTY50")
    DEFAULT_TIMEFRAME: str = os.getenv("DEFAULT_TIMEFRAME", "daily")
    INITIAL_CAPITAL: float = float(os.getenv("INITIAL_CAPITAL", "1000000"))

    # Risk limits
    MAX_POSITION_PCT: float = float(os.getenv("MAX_POSITION_PCT", "0.10"))
    MAX_SECTOR_PCT: float = float(os.getenv("MAX_SECTOR_PCT", "0.30"))
    MAX_PORTFOLIO_DRAWDOWN: float = float(os.getenv("MAX_PORTFOLIO_DRAWDOWN", "0.15"))
    DAILY_LOSS_LIMIT: float = float(os.getenv("DAILY_LOSS_LIMIT", "0.03"))
    WEEKLY_LOSS_LIMIT: float = float(os.getenv("WEEKLY_LOSS_LIMIT", "0.05"))

    # Dashboard
    DASHBOARD_HOST: str = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    DASHBOARD_PORT: int = int(os.getenv("DASHBOARD_PORT", "8000"))

    # Paper trading
    PAPER_TRADING_ENABLED: bool = os.getenv("PAPER_TRADING_ENABLED", "true").lower() == "true"
    PAPER_INITIAL_CAPITAL: float = float(os.getenv("PAPER_INITIAL_CAPITAL", "1000000"))
    MAX_QUOTE_AGE_SECONDS: int = int(os.getenv("MAX_QUOTE_AGE_SECONDS", "300"))

    # Experiments
    EXPERIMENT_DIR: str = os.getenv("EXPERIMENT_DIR", "experiments")

    # Broker credentials
    ZERODHA_API_KEY: str = os.getenv("ZERODHA_API_KEY", "")
    ANGELONE_API_KEY: str = os.getenv("ANGELONE_API_KEY", "")
    UPSTOX_API_KEY: str = os.getenv("UPSTOX_API_KEY", "")
    DHAN_CLIENT_ID: str = os.getenv("DHAN_CLIENT_ID", "")
    DHAN_ACCESS_TOKEN: str = os.getenv("DHAN_ACCESS_TOKEN", "")


    # Paths
    DATA_RAW: Path = PROJECT_ROOT / "data" / "raw"
    DATA_PROCESSED: Path = PROJECT_ROOT / "data" / "processed"
    DATA_FEATURES: Path = PROJECT_ROOT / "data" / "features"
    DATA_NEWS: Path = PROJECT_ROOT / "data" / "news"
    DATA_EVENTS: Path = PROJECT_ROOT / "data" / "events"
    DATA_UNIVERSES: Path = PROJECT_ROOT / "data" / "universes"
    MODELS_DIR: Path = PROJECT_ROOT / "models"
    EXPERIMENTS_DIR: Path = PROJECT_ROOT / "experiments"
    REPORTS_DIR: Path = PROJECT_ROOT / "reports"
    LOGS_DIR: Path = PROJECT_ROOT / "logs"
    STATE_DIR: Path = PROJECT_ROOT / "state"

    @classmethod
    def assert_no_live_trading(cls):
        """Hard safety check — call before any execution."""
        if cls.LIVE_TRADING_ENABLED:
            raise RuntimeError(
                "LIVE_TRADING_ENABLED is True! This is NOT allowed. "
                "Set LIVE_TRADING_ENABLED=false in .env"
            )

    @classmethod
    def get_broker_credentials(cls, broker: str) -> dict:
        """Return credentials for a given broker, or empty dict."""
        creds = {
            "zerodha": {
                "api_key": os.getenv("ZERODHA_API_KEY", ""),
                "api_secret": os.getenv("ZERODHA_API_SECRET", ""),
                "access_token": os.getenv("ZERODHA_ACCESS_TOKEN", ""),
            },
            "angelone": {
                "api_key": os.getenv("ANGELONE_API_KEY", ""),
                "client_id": os.getenv("ANGELONE_CLIENT_ID", ""),
                "password": os.getenv("ANGELONE_PASSWORD", ""),
                "totp_secret": os.getenv("ANGELONE_TOTP_SECRET", ""),
            },
            "upstox": {
                "api_key": os.getenv("UPSTOX_API_KEY", ""),
                "api_secret": os.getenv("UPSTOX_API_SECRET", ""),
                "access_token": os.getenv("UPSTOX_ACCESS_TOKEN", ""),
            },
        }
        return creds.get(broker.lower(), {})


config = Config()

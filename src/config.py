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
    PAPER_INITIAL_CAPITAL: float = float(os.getenv("PAPER_INITIAL_CAPITAL", "100000"))
    MICRO_STRATEGY_CAPITAL: float = float(os.getenv("MICRO_STRATEGY_CAPITAL", "20000"))
    # Executable-quote freshness. The monitor loop polls every 30s behind a 10s
    # quote cache, so a quote older than 60s is already two poll cycles stale and
    # cannot be treated as executable for an intraday option. Tightened from 300s
    # as a fail-closed safety bound, not a performance parameter.
    MAX_QUOTE_AGE_SECONDS: int = int(os.getenv("MAX_QUOTE_AGE_SECONDS", "60"))

    # Maximum acceptable bid/ask spread as a fraction of the reference price.
    # Shared by every execution path so the live session and the sandbox order
    # path apply an identical microstructure gate.
    MAX_SPREAD_PCT_OF_PRICE: float = float(os.getenv("MAX_SPREAD_PCT_OF_PRICE", "0.50"))

    # Portfolio-level concentration limits. Strategy labels must not be able to
    # bypass portfolio risk: multiple bots buying the identical contract is one
    # concentrated position, not diversification.
    MAX_BOTS_PER_CONTRACT: int = int(os.getenv("MAX_BOTS_PER_CONTRACT", "1"))
    MAX_SINGLE_CONTRACT_EXPOSURE_PCT: float = float(
        os.getenv("MAX_SINGLE_CONTRACT_EXPOSURE_PCT", "0.20")
    )
    # Aggregate cap across all strategies. Must sit below (per-position cap x
    # number of strategies), otherwise it can never bind and is a dead control:
    # with MAX_POSITION_PCT=10% and six bots the reachable maximum is 60%, so a
    # 60% aggregate cap would never trigger.
    MAX_TOTAL_OPEN_EXPOSURE_PCT: float = float(
        os.getenv("MAX_TOTAL_OPEN_EXPOSURE_PCT", "0.40")
    )

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

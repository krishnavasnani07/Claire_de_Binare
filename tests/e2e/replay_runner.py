"""
E2E Replay Runner - Deterministic Market Data Replay
Sprint 2: Issue #224, #229, #354

Publishes fixture data to Redis market_data topic in deterministic order.
"""

import json
import os
import sys
import time
import logging
from pathlib import Path
from typing import List, Dict, Any

import redis

# Add repo root to path for imports
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from core.utils.redis_payload import sanitize_market_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("replay_runner")


class ReplayRunner:
    """Deterministic replay runner for E2E testing."""

    def __init__(
        self,
        fixture_path: str,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_password: str | None = None,
        redis_db: int = 0,
    ):
        """
        Initialize replay runner.

        Args:
            fixture_path: Path to JSON fixture file
            redis_host: Redis host
            redis_port: Redis port
            redis_password: Redis password (optional)
            redis_db: Redis database number
        """
        self.fixture_path = Path(fixture_path)
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_password = redis_password
        self.redis_db = redis_db
        self.redis_client: redis.Redis | None = None
        self.fixture_data: Dict[str, Any] = {}
        self.ticks: List[Dict[str, Any]] = []

    def load_fixture(self) -> None:
        """Load fixture from JSON file."""
        logger.info(f"Loading fixture: {self.fixture_path}")

        if not self.fixture_path.exists():
            raise FileNotFoundError(f"Fixture not found: {self.fixture_path}")

        with open(self.fixture_path, "r") as f:
            self.fixture_data = json.load(f)

        self.ticks = self.fixture_data.get("ticks", [])
        metadata = self.fixture_data.get("metadata", {})

        logger.info(f"Fixture loaded: {metadata.get('description', 'N/A')}")
        logger.info(f"Tick count: {len(self.ticks)}")
        logger.info(f"Expected signals: {metadata.get('expected_signals', 'unknown')}")

    def connect_redis(self) -> None:
        """Connect to Redis."""
        logger.info(f"Connecting to Redis: {self.redis_host}:{self.redis_port}")

        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                password=self.redis_password,
                db=self.redis_db,
                decode_responses=True,
            )
            self.redis_client.ping()
            logger.info("✅ Redis connected")
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            raise

    def publish_tick(self, tick: Dict[str, Any]) -> None:
        """
        Publish single tick to Redis market_data topic.

        Args:
            tick: Tick data from fixture
        """
        # Convert fixture format to market_data contract v1.0
        market_data = {
            "schema_version": "v1.0",
            "source": "replay_runner",
            "symbol": tick["symbol"],
            "ts_ms": tick["timestamp"],  # Fixture uses timestamp (ms)
            "price": str(tick["price"]),  # Convert to str for precision
            "trade_qty": str(tick["volume"]),  # Volume as trade_qty
            "side": tick["side"],
            "type": "market_data",
        }

        # Sanitize payload (Issue #349: contract enforcement)
        try:
            sanitized = sanitize_market_data(market_data)
        except ValueError as e:
            logger.error(f"❌ Payload validation failed for tick {tick.get('tick_id')}: {e}")
            raise

        # Publish to Redis
        message = json.dumps(sanitized)
        self.redis_client.publish("market_data", message)

        logger.debug(
            f"✅ Published tick #{tick.get('tick_id')}: "
            f"{tick['symbol']} @ ${tick['price']} ({tick.get('comment', '')})"
        )

    def run(self, tick_delay_ms: int = 0) -> Dict[str, int]:
        """
        Run replay: publish all ticks in deterministic order.

        Args:
            tick_delay_ms: Delay between ticks in milliseconds (default: 0 for instant)

        Returns:
            Statistics dict with counts
        """
        logger.info("=" * 60)
        logger.info("Starting deterministic replay")
        logger.info("=" * 60)

        stats = {
            "ticks_published": 0,
            "errors": 0,
            "duration_ms": 0,
        }

        start_time = time.time()

        for tick in self.ticks:
            try:
                self.publish_tick(tick)
                stats["ticks_published"] += 1

                # Optional tick delay (deterministic pacing)
                if tick_delay_ms > 0:
                    time.sleep(tick_delay_ms / 1000.0)

            except Exception as e:
                logger.error(f"❌ Error publishing tick {tick.get('tick_id')}: {e}")
                stats["errors"] += 1

        end_time = time.time()
        stats["duration_ms"] = int((end_time - start_time) * 1000)

        logger.info("=" * 60)
        logger.info("Replay complete")
        logger.info(f"  Ticks published: {stats['ticks_published']}")
        logger.info(f"  Errors: {stats['errors']}")
        logger.info(f"  Duration: {stats['duration_ms']}ms")
        logger.info("=" * 60)

        return stats

    def cleanup(self) -> None:
        """Cleanup resources."""
        if self.redis_client:
            self.redis_client.close()
            logger.info("Redis connection closed")


def main():
    """Main entry point for CLI usage."""
    # Get Redis credentials from environment
    redis_password = os.getenv("REDIS_PASSWORD")
    if not redis_password:
        # Try reading from secrets file (Docker pattern)
        secrets_path = os.getenv("SECRETS_PATH", os.path.expanduser("~/.secrets/.cdb"))
        password_file = Path(secrets_path) / "REDIS_PASSWORD"
        if password_file.exists():
            redis_password = password_file.read_text().strip()

    # Default fixture path
    fixture_path = Path(__file__).parent / "fixtures" / "mexc_btcusdt_replay.json"

    # Allow override via CLI arg
    if len(sys.argv) > 1:
        fixture_path = Path(sys.argv[1])

    try:
        runner = ReplayRunner(
            fixture_path=str(fixture_path),
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            redis_password=redis_password,
        )

        runner.load_fixture()
        runner.connect_redis()

        # Run replay (instant publishing, no delays)
        stats = runner.run(tick_delay_ms=0)

        runner.cleanup()

        # Exit code: 0 if no errors, 1 otherwise
        sys.exit(0 if stats["errors"] == 0 else 1)

    except Exception as e:
        logger.error(f"❌ Replay failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

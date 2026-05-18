"""
Async WebSocket Connector for Dhan Live Feed
=============================================
- Asyncio Queue for backpressure
- Redis Pub/Sub for horizontal scaling
- Exponential backoff reconnect
- Heartbeat handling
"""

import asyncio
import json
import logging
from typing import Callable, Dict, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime

import aiohttp
import redis.asyncio as redis
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Dhan WebSocket Constants
DHAN_WS_URL = "wss://api-feed.dhan.co"
DHAN_WS_VERSION = "2"

# Exchange-Segment Constants
EXCHANGE_NSE_EQ = "NSE_EQ"
EXCHANGE_NSE_FNO = "NSE_FNO"
EXCHANGE_BSE_EQ = "BSE_EQ"
EXCHANGE_BSE_FNO = "BSE_FNO"
EXCHANGE_MCX_FUT = "MCX_FUT"

# Feed Types
FEED_TICKER = "ticker"
FEED_QUOTE = "quote"
FEED_DEPTH = "depth"
FEED_OI = "oi"


@dataclass
class TickData:
    """Represents a single market tick."""
    security_id: int
    exchange_segment: str
    last_price: float
    bid_price: float = 0.0
    ask_price: float = 0.0
    bid_qty: int = 0
    ask_qty: int = 0
    volume: int = 0
    oi: int = 0
    iv: float = 0.0
    timestamp: Optional[datetime] = None

    @classmethod
    def from_dhan_packet(cls, packet: Dict) -> 'TickData':
        """Parse Dhan WebSocket packet."""
        return cls(
            security_id=packet.get('security_id', 0),
            exchange_segment=packet.get('exchange_segment', ''),
            last_price=packet.get('last_price', 0.0),
            bid_price=packet.get('bid_price', 0.0),
            ask_price=packet.get('ask_price', 0.0),
            bid_qty=packet.get('bid_qty', 0),
            ask_qty=packet.get('ask_qty', 0),
            volume=packet.get('volume', 0),
            oi=packet.get('oi', 0),
            iv=packet.get('iv', 0.0),
            timestamp=datetime.now()
        )


class DhanWebSocket:
    """
    Production-grade async WebSocket client for Dhan.

    Features:
    - Asyncio Queue with backpressure (maxsize=10000)
    - Redis Pub/Sub for multi-worker scaling
    - Exponential backoff reconnect (max 10 attempts)
    - Heartbeat/ping handling
    - Automatic resubscription after reconnect
    """

    def __init__(
        self,
        client_id: str,
        access_token: str,
        redis_client: redis.Redis,
        queue_maxsize: int = 10000,
        max_reconnect: int = 10
    ):
        self.client_id = client_id
        self.access_token = access_token
        self.redis = redis_client

        # Queue for backpressure handling
        self.tick_queue: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)

        # Connection state
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = False
        self.connected = False

        # Reconnect logic
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = max_reconnect

        # Subscriptions tracking
        self.subscribed_instruments: Set[Tuple[int, str]] = set()

        # Callbacks
        self.on_tick_callback: Optional[Callable[[TickData], None]] = None
        self.on_connect_callback: Optional[Callable[[], None]] = None
        self.on_disconnect_callback: Optional[Callable[[], None]] = None

        # Metrics
        self.ticks_received = 0
        self.ticks_dropped = 0
        self.last_tick_time: Optional[datetime] = None

    # ==================== CONNECTION ====================

    async def connect(self) -> bool:
        """
        Establish WebSocket connection with exponential backoff.
        """
        uri = (
            f"{DHAN_WS_URL}?"
            f"version={DHAN_WS_VERSION}&"
            f"token={self.access_token}&"
            f"clientId={self.client_id}&"
            f"authType=2"
        )

        while self.reconnect_attempts < self.max_reconnect_attempts:
            try:
                logger.info(
                    f"🔌 Connecting to Dhan WebSocket "
                    f"(attempt {self.reconnect_attempts + 1}/{self.max_reconnect_attempts})..."
                )

                # Create session with timeout
                timeout = aiohttp.ClientTimeout(total=30, sock_connect=10)
                self.session = aiohttp.ClientSession(timeout=timeout)

                # Connect with heartbeat
                self.ws = await self.session.ws_connect(
                    uri,
                    heartbeat=30.0,
                    autoping=True,
                    receive_timeout=25.0
                )

                self.connected = True
                self.reconnect_attempts = 0
                self.running = True

                logger.info("✅ WebSocket connected successfully")

                # Resubscribe to previous instruments
                if self.subscribed_instruments:
                    await self._resubscribe()

                # Trigger connect callback
                if self.on_connect_callback:
                    await self.on_connect_callback()

                return True

            except Exception as e:
                self.reconnect_attempts += 1
                wait_time = min(2 ** self.reconnect_attempts, 60)

                logger.warning(
                    f"⚠️ Connection failed: {e}. "
                    f"Retrying in {wait_time}s..."
                )

                if self.session:
                    await self.session.close()

                await asyncio.sleep(wait_time)

        logger.error("❌ Max reconnect attempts reached. Giving up.")
        return False

    async def disconnect(self):
        """Gracefully disconnect."""
        self.running = False
        self.connected = False

        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()

        logger.info("🔌 WebSocket disconnected")

        if self.on_disconnect_callback:
            await self.on_disconnect_callback()

    # ==================== SUBSCRIPTION ====================

    async def subscribe(
        self, 
        instruments: List[Tuple[int, str]], 
        feed_type: str = FEED_QUOTE
    ) -> bool:
        """
        Subscribe to instruments.

        Args:
            instruments: List of (security_id, exchange_segment) tuples
            feed_type: "ticker", "quote", "depth", or "oi"
        """
        if not self.connected or not self.ws:
            logger.error("❌ Cannot subscribe: WebSocket not connected")
            return False

        try:
            # Dhan subscription format
            subscribe_msg = {
                "action": "subscribe",
                "instruments": [
                    [self._get_exchange_code(seg), sid]
                    for sid, seg in instruments
                ],
                "feed": feed_type
            }

            await self.ws.send_json(subscribe_msg)

            # Track subscriptions
            for sid, seg in instruments:
                self.subscribed_instruments.add((sid, seg))

            logger.info(f"📡 Subscribed to {len(instruments)} instruments ({feed_type})")
            return True

        except Exception as e:
            logger.error(f"❌ Subscribe failed: {e}")
            return False

    async def unsubscribe(self, instruments: List[Tuple[int, str]]) -> bool:
        """Unsubscribe from instruments."""
        if not self.connected:
            return False

        try:
            unsubscribe_msg = {
                "action": "unsubscribe",
                "instruments": [
                    [self._get_exchange_code(seg), sid]
                    for sid, seg in instruments
                ]
            }

            await self.ws.send_json(unsubscribe_msg)

            for sid, seg in instruments:
                self.subscribed_instruments.discard((sid, seg))

            logger.info(f"📡 Unsubscribed from {len(instruments)} instruments")
            return True

        except Exception as e:
            logger.error(f"❌ Unsubscribe failed: {e}")
            return False

    async def _resubscribe(self):
        """Resubscribe to all tracked instruments after reconnect."""
        if self.subscribed_instruments:
            instruments = list(self.subscribed_instruments)
            await self.subscribe(instruments)
            logger.info(f"🔄 Resubscribed to {len(instruments)} instruments")

    def _get_exchange_code(self, segment: str) -> int:
        """Convert exchange segment string to Dhan code."""
        codes = {
            EXCHANGE_NSE_EQ: 1,
            EXCHANGE_NSE_FNO: 11,
            EXCHANGE_BSE_EQ: 2,
            EXCHANGE_BSE_FNO: 12,
            EXCHANGE_MCX_FUT: 21
        }
        return codes.get(segment, 11)  # Default to NSE_FNO

    # ==================== LISTENING ====================

    async def listen(self):
        """
        Main listen loop.
        Reads messages and puts them in queue.
        """
        if not self.ws:
            logger.error("❌ Cannot listen: WebSocket not initialized")
            return

        try:
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._process_message(data)
                    except json.JSONDecodeError:
                        logger.warning(f"⚠️ Invalid JSON received: {msg.data[:100]}")

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"💥 WebSocket error: {msg.data}")
                    break

                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                    logger.info("🔌 WebSocket closed by server")
                    break

        except asyncio.CancelledError:
            logger.info("🛑 Listen loop cancelled")
            raise
        except Exception as e:
            logger.error(f"💥 Listen loop error: {e}")
        finally:
            self.connected = False

            # Attempt reconnect if still running
            if self.running:
                logger.info("🔄 Attempting reconnect...")
                await self.connect()

    async def _process_message(self, data: Dict):
        """
        Process incoming WebSocket message.
        """
        # Check if it's a tick data packet
        if 'security_id' in data:
            tick = TickData.from_dhan_packet(data)

            # Try to put in queue (non-blocking)
            try:
                self.tick_queue.put_nowait(tick)
                self.ticks_received += 1
                self.last_tick_time = datetime.now()
            except asyncio.QueueFull:
                self.ticks_dropped += 1
                if self.ticks_dropped % 1000 == 0:
                    logger.warning(f"⚠️ Queue full. Dropped {self.ticks_dropped} ticks")

            # Also publish to Redis for other workers
            await self._publish_to_redis(tick)

            # Call user callback
            if self.on_tick_callback:
                try:
                    await self.on_tick_callback(tick)
                except Exception as e:
                    logger.error(f"❌ Tick callback error: {e}")

    async def _publish_to_redis(self, tick: TickData):
        """Publish tick to Redis Pub/Sub."""
        try:
            channel = f"ticks:{tick.exchange_segment}:{tick.security_id}"
            await self.redis.publish(channel, json.dumps({
                'security_id': tick.security_id,
                'last_price': tick.last_price,
                'volume': tick.volume,
                'oi': tick.oi,
                'timestamp': tick.timestamp.isoformat() if tick.timestamp else None
            }))
        except Exception as e:
            logger.debug(f"Redis publish error: {e}")

    # ==================== QUEUE CONSUMER ====================

    async def start_queue_consumer(self, processor: Callable[[TickData], None]):
        """
        Start consuming from tick queue.
        Run this in a separate task.
        """
        logger.info("🚀 Queue consumer started")

        while self.running:
            try:
                # Wait for tick with timeout
                tick = await asyncio.wait_for(
                    self.tick_queue.get(), 
                    timeout=1.0
                )

                # Process tick
                await processor(tick)
                self.tick_queue.task_done()

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"❌ Queue consumer error: {e}")

    # ==================== CALLBACKS ====================

    def on_tick(self, callback: Callable[[TickData], None]):
        """Register tick callback."""
        self.on_tick_callback = callback

    def on_connect(self, callback: Callable[[], None]):
        """Register connect callback."""
        self.on_connect_callback = callback

    def on_disconnect(self, callback: Callable[[], None]):
        """Register disconnect callback."""
        self.on_disconnect_callback = callback

    # ==================== METRICS ====================

    def get_metrics(self) -> Dict:
        """Get WebSocket metrics."""
        return {
            'connected': self.connected,
            'running': self.running,
            'ticks_received': self.ticks_received,
            'ticks_dropped': self.ticks_dropped,
            'queue_size': self.tick_queue.qsize(),
            'queue_maxsize': self.tick_queue.maxsize,
            'subscribed_count': len(self.subscribed_instruments),
            'last_tick_time': self.last_tick_time.isoformat() if self.last_tick_time else None,
            'reconnect_attempts': self.reconnect_attempts
        }

    async def health_check(self) -> Dict:
        """Health check."""
        return {
            'status': 'connected' if self.connected else 'disconnected',
            'metrics': self.get_metrics(),
            'redis_connected': await self.redis.ping()
        }

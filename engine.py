"""
Institutional Risk Management Engine
====================================
- Daily loss limits
- Circuit breaker
- Consecutive loss tracking
- Volatility filters
- Event-based filters
- Position sizing
"""

import json
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk severity levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TradeAction(Enum):
    """Trade actions."""
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    WARN = "WARN"
    REDUCE_SIZE = "REDUCE_SIZE"


@dataclass
class RiskCheck:
    """Result of a risk check."""
    allowed: bool
    action: TradeAction
    reason: str
    risk_level: RiskLevel
    metadata: Dict = field(default_factory=dict)


class RiskEngine:
    """
    Production-grade risk management system.

    Features:
    - Daily loss limits (configurable per user)
    - Circuit breaker (auto-reset after timeout)
    - Consecutive loss tracking
    - Volatility-based filters
    - Event-based trading halts
    - Position sizing limits
    - Drawdown tracking
    """

    # Default limits
    DEFAULT_DAILY_LOSS_LIMIT = 50000  # ₹50,000
    DEFAULT_MAX_TRADES_PER_DAY = 20
    DEFAULT_MAX_CONSECUTIVE_LOSSES = 3
    DEFAULT_VOLATILITY_LIMIT = 50  # IV > 50% = caution
    DEFAULT_CIRCUIT_BREAKER_TIMEOUT = 900  # 15 minutes
    DEFAULT_MAX_POSITION_SIZE = 10  # Max lots per trade
    DEFAULT_MAX_DRAWDOWN_PCT = 5.0  # 5% max drawdown

    def __init__(
        self,
        redis_client: redis.Redis,
        daily_loss_limit: float = DEFAULT_DAILY_LOSS_LIMIT,
        max_trades_per_day: int = DEFAULT_MAX_TRADES_PER_DAY,
        max_consecutive_losses: int = DEFAULT_MAX_CONSECUTIVE_LOSSES,
        volatility_limit: float = DEFAULT_VOLATILITY_LIMIT,
        circuit_breaker_timeout: int = DEFAULT_CIRCUIT_BREAKER_TIMEOUT,
        max_position_size: int = DEFAULT_MAX_POSITION_SIZE,
        max_drawdown_pct: float = DEFAULT_MAX_DRAWDOWN_PCT
    ):
        self.redis = redis_client
        self.daily_loss_limit = daily_loss_limit
        self.max_trades_per_day = max_trades_per_day
        self.max_consecutive_losses = max_consecutive_losses
        self.volatility_limit = volatility_limit
        self.circuit_breaker_timeout = circuit_breaker_timeout
        self.max_position_size = max_position_size
        self.max_drawdown_pct = max_drawdown_pct

        # Redis key prefixes
        self.KEY_DAILY_PNL = "risk:daily_pnl"
        self.KEY_TRADE_COUNT = "risk:trade_count"
        self.KEY_CONSECUTIVE_LOSSES = "risk:consecutive_losses"
        self.KEY_CIRCUIT_BREAKER = "risk:circuit_breaker"
        self.KEY_TRADE_HISTORY = "risk:trade_history"
        self.KEY_DRAWDOWN = "risk:drawdown"
        self.KEY_ALERTS = "risk:alerts"
        self.KEY_DAILY_HIGH = "risk:daily_high"

    # ==================== PRE-TRADE CHECKS ====================

    async def check_before_trade(
        self,
        user_id: str,
        trade: Dict
    ) -> RiskCheck:
        """
        Comprehensive pre-trade risk check.

        Args:
            user_id: User identifier
            trade: Trade details dict
                {
                    'symbol': 'NIFTY',
                    'option_type': 'CE',
                    'strike': 22500,
                    'expiry': '2026-05-22',
                    'action': 'BUY',
                    'quantity': 50,
                    'price': 150.5,
                    'iv': 22.5
                }

        Returns:
            RiskCheck object
        """
        checks = []

        # 1. Circuit breaker check
        cb_check = await self._check_circuit_breaker(user_id)
        checks.append(cb_check)

        # 2. Daily loss limit
        loss_check = await self._check_daily_loss(user_id)
        checks.append(loss_check)

        # 3. Trade count limit
        count_check = await self._check_trade_count(user_id)
        checks.append(count_check)

        # 4. Consecutive losses
        consecutive_check = await self._check_consecutive_losses(user_id)
        checks.append(consecutive_check)

        # 5. Volatility filter
        vol_check = self._check_volatility(trade)
        checks.append(vol_check)

        # 6. Position sizing
        size_check = self._check_position_size(trade)
        checks.append(size_check)

        # 7. Drawdown check
        dd_check = await self._check_drawdown(user_id)
        checks.append(dd_check)

        # 8. Event filter
        event_check = await self._check_events()
        checks.append(event_check)

        # Aggregate results
        blocked = [c for c in checks if c.action == TradeAction.BLOCK]
        warnings = [c for c in checks if c.action == TradeAction.WARN]
        reduces = [c for c in checks if c.action == TradeAction.REDUCE_SIZE]

        if blocked:
            # Return most critical block
            critical = max(blocked, key=lambda x: list(RiskLevel).index(x.risk_level))
            return critical

        if reduces:
            return reduces[0]

        if warnings:
            return RiskCheck(
                allowed=True,
                action=TradeAction.WARN,
                reason="; ".join([w.reason for w in warnings]),
                risk_level=RiskLevel.MEDIUM,
                metadata={'warnings': [w.to_dict() for w in warnings]}
            )

        return RiskCheck(
            allowed=True,
            action=TradeAction.ALLOW,
            reason="All risk checks passed",
            risk_level=RiskLevel.LOW
        )

    async def _check_circuit_breaker(self, user_id: str) -> RiskCheck:
        """Check if circuit breaker is active."""
        key = f"{self.KEY_CIRCUIT_BREAKER}:{user_id}"
        cb_status = await self.redis.get(key)

        if cb_status and cb_status.decode() == "ACTIVE":
            # Get remaining time
            ttl = await self.redis.ttl(key)
            return RiskCheck(
                allowed=False,
                action=TradeAction.BLOCK,
                reason=f"Circuit breaker active. Wait {ttl} seconds.",
                risk_level=RiskLevel.CRITICAL
            )

        return RiskCheck(
            allowed=True,
            action=TradeAction.ALLOW,
            reason="Circuit breaker inactive",
            risk_level=RiskLevel.LOW
        )

    async def _check_daily_loss(self, user_id: str) -> RiskCheck:
        """Check daily loss limit."""
        daily_pnl = await self.get_daily_pnl(user_id)

        if daily_pnl <= -self.daily_loss_limit:
            return RiskCheck(
                allowed=False,
                action=TradeAction.BLOCK,
                reason=f"Daily loss limit exceeded: ₹{abs(daily_pnl):,.2f} / ₹{self.daily_loss_limit:,.2f}",
                risk_level=RiskLevel.CRITICAL,
                metadata={'daily_pnl': daily_pnl, 'limit': self.daily_loss_limit}
            )

        # Warning at 80% of limit
        if daily_pnl <= -self.daily_loss_limit * 0.8:
            return RiskCheck(
                allowed=True,
                action=TradeAction.WARN,
                reason=f"Daily loss at 80% limit: ₹{abs(daily_pnl):,.2f}",
                risk_level=RiskLevel.HIGH,
                metadata={'daily_pnl': daily_pnl, 'limit': self.daily_loss_limit}
            )

        return RiskCheck(
            allowed=True,
            action=TradeAction.ALLOW,
            reason="Daily loss within limit",
            risk_level=RiskLevel.LOW
        )

    async def _check_trade_count(self, user_id: str) -> RiskCheck:
        """Check daily trade count."""
        count = await self.get_daily_trade_count(user_id)

        if count >= self.max_trades_per_day:
            return RiskCheck(
                allowed=False,
                action=TradeAction.BLOCK,
                reason=f"Max trades reached: {count}/{self.max_trades_per_day}",
                risk_level=RiskLevel.HIGH
            )

        if count >= self.max_trades_per_day * 0.9:
            return RiskCheck(
                allowed=True,
                action=TradeAction.WARN,
                reason=f"Trade count at 90%: {count}/{self.max_trades_per_day}",
                risk_level=RiskLevel.MEDIUM
            )

        return RiskCheck(
            allowed=True,
            action=TradeAction.ALLOW,
            reason="Trade count within limit",
            risk_level=RiskLevel.LOW
        )

    async def _check_consecutive_losses(self, user_id: str) -> RiskCheck:
        """Check consecutive loss streak."""
        losses = await self.get_consecutive_losses(user_id)

        if losses >= self.max_consecutive_losses:
            return RiskCheck(
                allowed=False,
                action=TradeAction.BLOCK,
                reason=f"Max consecutive losses: {losses}/{self.max_consecutive_losses}",
                risk_level=RiskLevel.CRITICAL
            )

        if losses >= self.max_consecutive_losses - 1:
            return RiskCheck(
                allowed=True,
                action=TradeAction.WARN,
                reason=f"Consecutive losses: {losses}/{self.max_consecutive_losses}. Caution advised.",
                risk_level=RiskLevel.HIGH
            )

        return RiskCheck(
            allowed=True,
            action=TradeAction.ALLOW,
            reason="No consecutive loss streak",
            risk_level=RiskLevel.LOW
        )

    def _check_volatility(self, trade: Dict) -> RiskCheck:
        """Check IV/volatility levels."""
        iv = trade.get('iv', 0)

        if iv > self.volatility_limit:
            return RiskCheck(
                allowed=True,
                action=TradeAction.REDUCE_SIZE,
                reason=f"High IV: {iv}% > {self.volatility_limit}%. Reduce position size by 50%.",
                risk_level=RiskLevel.HIGH,
                metadata={'iv': iv, 'limit': self.volatility_limit}
            )

        if iv > self.volatility_limit * 0.8:
            return RiskCheck(
                allowed=True,
                action=TradeAction.WARN,
                reason=f"Elevated IV: {iv}%",
                risk_level=RiskLevel.MEDIUM
            )

        return RiskCheck(
            allowed=True,
            action=TradeAction.ALLOW,
            reason="Volatility within normal range",
            risk_level=RiskLevel.LOW
        )

    def _check_position_size(self, trade: Dict) -> RiskCheck:
        """Check position size limits."""
        quantity = trade.get('quantity', 0)
        lots = quantity // 50  # Assuming 50 qty per lot

        if lots > self.max_position_size:
            return RiskCheck(
                allowed=False,
                action=TradeAction.BLOCK,
                reason=f"Position size too large: {lots} lots > {self.max_position_size} max",
                risk_level=RiskLevel.HIGH
            )

        if lots > self.max_position_size * 0.8:
            return RiskCheck(
                allowed=True,
                action=TradeAction.WARN,
                reason=f"Large position: {lots} lots",
                risk_level=RiskLevel.MEDIUM
            )

        return RiskCheck(
            allowed=True,
            action=TradeAction.ALLOW,
            reason="Position size within limit",
            risk_level=RiskLevel.LOW
        )

    async def _check_drawdown(self, user_id: str) -> RiskCheck:
        """Check portfolio drawdown."""
        dd = await self.get_drawdown(user_id)

        if dd >= self.max_drawdown_pct:
            return RiskCheck(
                allowed=False,
                action=TradeAction.BLOCK,
                reason=f"Max drawdown reached: {dd:.2f}% / {self.max_drawdown_pct}%",
                risk_level=RiskLevel.CRITICAL
            )

        if dd >= self.max_drawdown_pct * 0.8:
            return RiskCheck(
                allowed=True,
                action=TradeAction.WARN,
                reason=f"High drawdown: {dd:.2f}%",
                risk_level=RiskLevel.HIGH
            )

        return RiskCheck(
            allowed=True,
            action=TradeAction.ALLOW,
            reason="Drawdown within limit",
            risk_level=RiskLevel.LOW
        )

    async def _check_events(self) -> RiskCheck:
        """Check for major economic events."""
        # TODO: Integrate with economic calendar API
        # For now, manual check via Redis flag
        event_flag = await self.redis.get("market:major_event")

        if event_flag and event_flag.decode() == "ACTIVE":
            return RiskCheck(
                allowed=True,
                action=TradeAction.WARN,
                reason="Major economic event today. Reduced position sizing recommended.",
                risk_level=RiskLevel.MEDIUM
            )

        return RiskCheck(
            allowed=True,
            action=TradeAction.ALLOW,
            reason="No major events",
            risk_level=RiskLevel.LOW
        )

    # ==================== POST-TRADE TRACKING ====================

    async def record_trade_result(
        self,
        user_id: str,
        trade: Dict,
        pnl: float
    ):
        """
        Record trade result for risk tracking.
        """
        today = date.today().isoformat()

        # Update daily P&L
        await self.redis.incrbyfloat(
            f"{self.KEY_DAILY_PNL}:{user_id}:{today}",
            pnl
        )

        # Update consecutive losses
        if pnl < 0:
            await self.redis.incr(f"{self.KEY_CONSECUTIVE_LOSSES}:{user_id}")
        else:
            await self.redis.delete(f"{self.KEY_CONSECUTIVE_LOSSES}:{user_id}")

        # Update trade count
        await self.redis.incr(f"{self.KEY_TRADE_COUNT}:{user_id}:{today}")

        # Update drawdown
        await self._update_drawdown(user_id, pnl)

        # Store trade history
        trade_record = {
            'timestamp': datetime.now().isoformat(),
            'trade': trade,
            'pnl': pnl,
            'date': today
        }
        await self.redis.lpush(
            f"{self.KEY_TRADE_HISTORY}:{user_id}:{today}",
            json.dumps(trade_record)
        )

        # Trim history (keep last 100)
        await self.redis.ltrim(
            f"{self.KEY_TRADE_HISTORY}:{user_id}:{today}",
            0, 99
        )

        # Check if circuit breaker should activate
        await self._check_circuit_breaker_threshold(user_id)

        logger.info(f"📊 Trade recorded for {user_id}: P&L ₹{pnl:,.2f}")

    async def _update_drawdown(self, user_id: str, pnl: float):
        """Update running drawdown calculation."""
        today = date.today().isoformat()

        # Get current high
        high_key = f"{self.KEY_DAILY_HIGH}:{user_id}:{today}"
        current_high = await self.redis.get(high_key)

        if current_high is None:
            current_high = 0.0
        else:
            current_high = float(current_high.decode())

        # Update high if P&L improved
        new_high = max(current_high, current_high + pnl)
        await self.redis.set(high_key, str(new_high))

        # Calculate drawdown
        current_pnl = await self.get_daily_pnl(user_id)
        if new_high > 0:
            drawdown = ((new_high - current_pnl) / new_high) * 100
        else:
            drawdown = 0

        await self.redis.set(
            f"{self.KEY_DRAWDOWN}:{user_id}:{today}",
            str(drawdown)
        )

    async def _check_circuit_breaker_threshold(self, user_id: str):
        """Check if circuit breaker should activate."""
        daily_pnl = await self.get_daily_pnl(user_id)

        # Activate if daily loss > 2x limit
        if daily_pnl <= -self.daily_loss_limit * 2:
            await self.activate_circuit_breaker(
                user_id,
                f"Daily loss exceeded 2x limit: ₹{abs(daily_pnl):,.2f}"
            )

    async def activate_circuit_breaker(self, user_id: str, reason: str):
        """
        Manually activate circuit breaker.
        """
        key = f"{self.KEY_CIRCUIT_BREAKER}:{user_id}"
        await self.redis.setex(key, self.circuit_breaker_timeout, "ACTIVE")

        # Log event
        alert = {
            'type': 'CIRCUIT_BREAKER',
            'user_id': user_id,
            'reason': reason,
            'timestamp': datetime.now().isoformat(),
            'duration': self.circuit_breaker_timeout
        }
        await self.redis.lpush(self.KEY_ALERTS, json.dumps(alert))

        logger.critical(f"🚨 Circuit breaker activated for {user_id}: {reason}")

    async def deactivate_circuit_breaker(self, user_id: str):
        """Manually deactivate circuit breaker."""
        key = f"{self.KEY_CIRCUIT_BREAKER}:{user_id}"
        await self.redis.delete(key)
        logger.info(f"✅ Circuit breaker deactivated for {user_id}")

    # ==================== GETTERS ====================

    async def get_daily_pnl(self, user_id: str) -> float:
        """Get today's P&L."""
        today = date.today().isoformat()
        pnl = await self.redis.get(f"{self.KEY_DAILY_PNL}:{user_id}:{today}")
        return float(pnl.decode()) if pnl else 0.0

    async def get_daily_trade_count(self, user_id: str) -> int:
        """Get today's trade count."""
        today = date.today().isoformat()
        count = await self.redis.get(f"{self.KEY_TRADE_COUNT}:{user_id}:{today}")
        return int(count.decode()) if count else 0

    async def get_consecutive_losses(self, user_id: str) -> int:
        """Get current consecutive loss streak."""
        losses = await self.redis.get(f"{self.KEY_CONSECUTIVE_LOSSES}:{user_id}")
        return int(losses.decode()) if losses else 0

    async def get_drawdown(self, user_id: str) -> float:
        """Get current drawdown %."""
        today = date.today().isoformat()
        dd = await self.redis.get(f"{self.KEY_DRAWDOWN}:{user_id}:{today}")
        return float(dd.decode()) if dd else 0.0

    async def get_trade_history(self, user_id: str, limit: int = 50) -> List[Dict]:
        """Get recent trade history."""
        today = date.today().isoformat()
        trades = await self.redis.lrange(
            f"{self.KEY_TRADE_HISTORY}:{user_id}:{today}",
            0, limit - 1
        )
        return [json.loads(t.decode()) for t in trades]

    async def get_risk_summary(self, user_id: str) -> Dict:
        """Get complete risk summary for user."""
        return {
            'daily_pnl': await self.get_daily_pnl(user_id),
            'daily_loss_limit': self.daily_loss_limit,
            'daily_loss_used_pct': abs(await self.get_daily_pnl(user_id)) / self.daily_loss_limit * 100,
            'trade_count': await self.get_daily_trade_count(user_id),
            'max_trades': self.max_trades_per_day,
            'consecutive_losses': await self.get_consecutive_losses(user_id),
            'max_consecutive': self.max_consecutive_losses,
            'drawdown_pct': await self.get_drawdown(user_id),
            'max_drawdown': self.max_drawdown_pct,
            'circuit_breaker': await self._is_circuit_breaker_active(user_id),
            'status': 'HEALTHY' if await self.get_drawdown(user_id) < self.max_drawdown_pct * 0.5 else 'CAUTION'
        }

    async def _is_circuit_breaker_active(self, user_id: str) -> bool:
        """Check if circuit breaker is active."""
        key = f"{self.KEY_CIRCUIT_BREAKER}:{user_id}"
        cb = await self.redis.get(key)
        return cb and cb.decode() == "ACTIVE"

    async def reset_daily_metrics(self, user_id: str):
        """Reset all daily metrics (run at day start)."""
        today = date.today().isoformat()

        # Delete today's keys
        keys = [
            f"{self.KEY_DAILY_PNL}:{user_id}:{today}",
            f"{self.KEY_TRADE_COUNT}:{user_id}:{today}",
            f"{self.KEY_DRAWDOWN}:{user_id}:{today}",
            f"{self.KEY_DAILY_HIGH}:{user_id}:{today}",
            f"{self.KEY_TRADE_HISTORY}:{user_id}:{today}"
        ]

        for key in keys:
            await self.redis.delete(key)

        # Reset consecutive losses
        await self.redis.delete(f"{self.KEY_CONSECUTIVE_LOSSES}:{user_id}")

        logger.info(f"🔄 Daily metrics reset for {user_id}")

    async def health_check(self) -> Dict:
        """Risk engine health check."""
        return {
            'status': 'healthy',
            'daily_loss_limit': self.daily_loss_limit,
            'max_trades': self.max_trades_per_day,
            'max_consecutive_losses': self.max_consecutive_losses,
            'volatility_limit': self.volatility_limit,
            'circuit_breaker_timeout': self.circuit_breaker_timeout,
            'max_position_size': self.max_position_size,
            'max_drawdown_pct': self.max_drawdown_pct,
            'redis_connected': await self.redis.ping()
        }

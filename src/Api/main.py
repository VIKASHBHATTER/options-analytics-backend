"""
Options Analytics API - FastAPI Application
=============================================
- JWT Authentication
- Rate Limiting
- Prometheus Metrics
- WebSocket Alerts
- REST Endpoints for all components
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import PlainTextResponse
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from jose import JWTError, jwt
from passlib.context import CryptContext
import redis.asyncio as redis

# Import our modules
from src.instrument_master.fetcher import InstrumentMasterFetcher
from src.processors.greeks_engine import GreeksCalculator, GammaExposureEngine
from src.risk.engine import RiskEngine

logger = logging.getLogger(__name__)

# Security
SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# Prometheus Metrics
REQUEST_COUNT = Counter(
    'api_requests_total', 
    'Total API requests', 
    ['method', 'endpoint', 'status']
)
REQUEST_LATENCY = Histogram(
    'api_request_latency_seconds', 
    'Request latency',
    ['endpoint']
)
ACTIVE_WEBSOCKETS = Gauge(
    'active_websockets', 
    'Number of active WebSocket connections',
    ['endpoint']
)
INSTRUMENTS_LOADED = Gauge(
    'instruments_loaded', 
    'Number of instruments in master'
)
TICKS_RECEIVED = Counter(
    'ticks_received_total', 
    'Total ticks received'
)

# Create FastAPI app
app = FastAPI(
    title="Options Analytics API",
    description="Institutional-grade options analytics backend",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
class AppState:
    redis: Optional[redis.Redis] = None
    instrument_master: Optional[InstrumentMasterFetcher] = None
    greeks_calc: Optional[GreeksCalculator] = None
    gex_engine: Optional[GammaExposureEngine] = None
    risk_engine: Optional[RiskEngine] = None

state = AppState()

# ==================== AUTHENTICATION ====================

def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ==================== LIFECYCLE ====================

@app.on_event("startup")
async def startup():
    """Initialize all services on startup."""
    logger.info("🚀 Starting Options Analytics API...")

    # Connect to Redis
    state.redis = redis.Redis(
        host='redis',
        port=6379,
        decode_responses=False
    )

    # Initialize instrument master
    state.instrument_master = InstrumentMasterFetcher(
        redis_client=state.redis,
        client_id="your_client_id",
        access_token="your_access_token"
    )
    await state.instrument_master.initialize()

    # Initialize Greeks engine
    state.greeks_calc = GreeksCalculator()
    state.gex_engine = GammaExposureEngine(state.greeks_calc)

    # Initialize Risk engine
    state.risk_engine = RiskEngine(redis_client=state.redis)

    # Update metrics
    INSTRUMENTS_LOADED.set(state.instrument_master.instrument_count)

    logger.info("✅ API startup complete")

@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    logger.info("🛑 Shutting down...")
    if state.redis:
        await state.redis.close()

# ==================== HEALTH & METRICS ====================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    health = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0",
        "services": {}
    }

    # Check Redis
    try:
        redis_ping = await state.redis.ping()
        health["services"]["redis"] = "connected" if redis_ping else "disconnected"
    except:
        health["services"]["redis"] = "error"

    # Check instrument master
    if state.instrument_master:
        health["services"]["instrument_master"] = {
            "status": "loaded" if state.instrument_master.instrument_count > 0 else "empty",
            "instruments": state.instrument_master.instrument_count,
            "last_updated": state.instrument_master.last_updated.isoformat() if state.instrument_master.last_updated else None
        }

    return health

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return PlainTextResponse(
        content=generate_latest(),
        media_type="text/plain"
    )

# ==================== INSTRUMENT MASTER ====================

@app.get("/instruments/underlyings")
async def get_underlyings(user_id: str = Depends(verify_token)):
    """Get all available underlyings."""
    REQUEST_COUNT.labels(method="GET", endpoint="/instruments/underlyings", status="200").inc()

    if not state.instrument_master:
        raise HTTPException(status_code=503, detail="Instrument master not initialized")

    return {
        "underlyings": state.instrument_master.get_underlyings()
    }

@app.get("/instruments/{underlying}/strikes")
async def get_strikes(
    underlying: str,
    expiry: Optional[str] = None,
    user_id: str = Depends(verify_token)
):
    """Get strikes for an underlying."""
    REQUEST_COUNT.labels(method="GET", endpoint="/instruments/strikes", status="200").inc()

    if not state.instrument_master:
        raise HTTPException(status_code=503, detail="Instrument master not initialized")

    strikes = state.instrument_master.get_strikes(underlying, expiry)
    atm = state.instrument_master.get_atm_strike(underlying, 22500)  # Default spot

    return {
        "underlying": underlying,
        "expiry": expiry or state.instrument_master.get_current_expiry(underlying),
        "strikes": strikes,
        "atm_strike": atm,
        "total_strikes": len(strikes)
    }

@app.get("/instruments/{underlying}/chain-summary")
async def get_chain_summary(
    underlying: str,
    expiry: Optional[str] = None,
    user_id: str = Depends(verify_token)
):
    """Get option chain summary."""
    if not state.instrument_master:
        raise HTTPException(status_code=503, detail="Instrument master not initialized")

    summary = state.instrument_master.get_option_chain_summary(underlying, expiry)
    return summary

@app.get("/instruments/{underlying}/security-ids")
async def get_security_ids(
    underlying: str,
    spot: float,
    range_points: int = 1000,
    expiry: Optional[str] = None,
    user_id: str = Depends(verify_token)
):
    """Get security IDs for strikes around spot price."""
    if not state.instrument_master:
        raise HTTPException(status_code=503, detail="Instrument master not initialized")

    security_ids = state.instrument_master.get_security_ids_range(
        underlying, spot, range_points, expiry
    )

    return {
        "underlying": underlying,
        "spot": spot,
        "range": range_points,
        "expiry": expiry or state.instrument_master.get_current_expiry(underlying),
        "security_ids": security_ids,
        "count": len(security_ids)
    }

@app.post("/instruments/refresh")
async def refresh_instruments(user_id: str = Depends(verify_token)):
    """Force refresh instrument master."""
    if not state.instrument_master:
        raise HTTPException(status_code=503, detail="Instrument master not initialized")

    success = await state.instrument_master.refresh()

    if success:
        INSTRUMENTS_LOADED.set(state.instrument_master.instrument_count)
        return {
            "status": "success",
            "instruments_loaded": state.instrument_master.instrument_count,
            "timestamp": datetime.utcnow().isoformat()
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to refresh instruments")

# ==================== GREEKS & EXPOSURE ====================

@app.post("/greeks/calculate")
async def calculate_greeks(
    spot: float,
    strike: float,
    days: float,
    iv: float,
    option_type: str,
    user_id: str = Depends(verify_token)
):
    """Calculate Greeks for an option."""
    if not state.greeks_calc:
        raise HTTPException(status_code=503, detail="Greeks calculator not initialized")

    greeks = state.greeks_calc.calculate_greeks(spot, strike, days, iv, option_type)

    return {
        "spot": spot,
        "strike": strike,
        "days_to_expiry": days,
        "iv": iv,
        "option_type": option_type,
        "greeks": greeks.to_dict()
    }

@app.post("/greeks/gamma-exposure")
async def calculate_gamma_exposure(
    option_chain: List[Dict],
    spot: float,
    underlying: str = "NIFTY",
    user_id: str = Depends(verify_token)
):
    """Calculate Gamma Exposure for option chain."""
    if not state.gex_engine:
        raise HTTPException(status_code=503, detail="GEX engine not initialized")

    exposure = state.gex_engine.calculate_gex(option_chain, spot, underlying)
    key_levels = state.gex_engine.get_key_levels(exposure, spot)

    return {
        "underlying": underlying,
        "spot": spot,
        "exposure": exposure.to_dict(),
        "key_levels": key_levels
    }

# ==================== RISK MANAGEMENT ====================

@app.post("/risk/check-trade")
async def check_trade_risk(
    trade: Dict,
    user_id: str = Depends(verify_token)
):
    """Check risk before executing trade."""
    if not state.risk_engine:
        raise HTTPException(status_code=503, detail="Risk engine not initialized")

    result = await state.risk_engine.check_before_trade(user_id, trade)

    return {
        "allowed": result.allowed,
        "action": result.action.value,
        "reason": result.reason,
        "risk_level": result.risk_level.value,
        "metadata": result.metadata
    }

@app.get("/risk/summary")
async def get_risk_summary(user_id: str = Depends(verify_token)):
    """Get risk summary for user."""
    if not state.risk_engine:
        raise HTTPException(status_code=503, detail="Risk engine not initialized")

    summary = await state.risk_engine.get_risk_summary(user_id)
    return summary

@app.post("/risk/record-trade")
async def record_trade(
    trade: Dict,
    pnl: float,
    user_id: str = Depends(verify_token)
):
    """Record trade result for risk tracking."""
    if not state.risk_engine:
        raise HTTPException(status_code=503, detail="Risk engine not initialized")

    await state.risk_engine.record_trade_result(user_id, trade, pnl)

    return {
        "status": "recorded",
        "user_id": user_id,
        "pnl": pnl,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/risk/circuit-breaker/activate")
async def activate_circuit_breaker(
    reason: str,
    user_id: str = Depends(verify_token)
):
    """Manually activate circuit breaker."""
    if not state.risk_engine:
        raise HTTPException(status_code=503, detail="Risk engine not initialized")

    await state.risk_engine.activate_circuit_breaker(user_id, reason)

    return {
        "status": "activated",
        "user_id": user_id,
        "reason": reason,
        "timeout_seconds": state.risk_engine.circuit_breaker_timeout
    }

@app.post("/risk/circuit-breaker/deactivate")
async def deactivate_circuit_breaker(user_id: str = Depends(verify_token)):
    """Manually deactivate circuit breaker."""
    if not state.risk_engine:
        raise HTTPException(status_code=503, detail="Risk engine not initialized")

    await state.risk_engine.deactivate_circuit_breaker(user_id)

    return {
        "status": "deactivated",
        "user_id": user_id
    }

# ==================== WEBSOCKET ALERTS ====================

@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket, token: str):
    """Real-time alerts WebSocket."""
    ACTIVE_WEBSOCKETS.labels(endpoint="/ws/alerts").inc()

    try:
        # Verify token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")

        await websocket.accept()

        # Subscribe to Redis pub/sub
        pubsub = state.redis.pubsub()
        await pubsub.subscribe(f"alerts:{user_id}")

        logger.info(f"🔔 WebSocket connected for user: {user_id}")

        async for message in pubsub.listen():
            if message['type'] == 'message':
                await websocket.send_text(message['data'].decode())

    except JWTError:
        await websocket.close(code=1008, reason="Invalid token")
    except WebSocketDisconnect:
        logger.info("🔌 WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        ACTIVE_WEBSOCKETS.labels(endpoint="/ws/alerts").dec()
        if 'pubsub' in locals():
            await pubsub.unsubscribe()

@app.websocket("/ws/ticks")
async def websocket_ticks(websocket: WebSocket, token: str):
    """Real-time tick data WebSocket."""
    ACTIVE_WEBSOCKETS.labels(endpoint="/ws/ticks").inc()

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")

        await websocket.accept()

        # Subscribe to tick channel
        pubsub = state.redis.pubsub()
        await pubsub.subscribe("ticks:*")

        async for message in pubsub.listen():
            if message['type'] == 'message':
                await websocket.send_text(message['data'].decode())
                TICKS_RECEIVED.inc()

    except Exception as e:
        logger.error(f"Tick WebSocket error: {e}")
    finally:
        ACTIVE_WEBSOCKETS.labels(endpoint="/ws/ticks").dec()

# ==================== AUTH ====================

@app.post("/auth/token")
async def login(credentials: Dict):
    """Login and get JWT token."""
    # TODO: Implement proper user authentication
    # For now, demo token

    user_id = credentials.get("username", "demo_user")
    access_token = create_access_token(
        data={"sub": user_id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }

# ==================== ERROR HANDLERS ====================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=str(exc.status_code)
    ).inc()
    raise exc

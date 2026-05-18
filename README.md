# 🏛️ Options Analytics Backend

Institutional-grade options analytics platform for Indian markets (NSE F&O).

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        DHAN API                              │
│              (WebSocket V2 + REST + Instrument Master)       │
└─────────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            │                                   │
      WebSocket Feed                     REST Poller
            │                                   │
            ▼                                   ▼
┌───────────────────────┐           ┌───────────────────┐
│   Redis Pub/Sub        │           │  Instrument Cache  │
│   (Tick Queue)         │           │   (Redis)          │
└───────────┬───────────┘           └───────────────────┘
            │
┌───────────┴───────────┐
│                       │
▼                       ▼
┌───────────────┐       ┌───────────────┐
│  Worker 1     │       │  Worker 2     │
│  OI + Volume  │       │  PCR Engine   │
└───────┬───────┘       └───────┬───────┘
        │                       │
        └───────────┬───────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
        ▼                       ▼
┌───────────────┐       ┌───────────────┐
│  PostgreSQL   │       │  Redis Cache  │
│ (Partitioned) │       │  (Metrics)    │
└───────────────┘       └───────────────┘
                │
                ▼
    ┌───────────────────────┐
    │     FastAPI + JWT      │
    │   Rate Limiting + WS   │
    └───────────┬───────────┘
                │
    ┌───────────┴───────────┐
    │                       │
    ▼                       ▼
Frontend/Webhook        TradingView
```

## 🚀 Quick Start (GitHub Codespaces)

### Step 1: Create Repository
1. GitHub पर new repo बनाओ
2. ये सारी files upload करो

### Step 2: Open in Codespaces
1. Repo page पर `Code` → `Codespaces` → `Create codespace`
2. Browser में VS Code open होगा

### Step 3: Start Services
```bash
# Copy environment file
cp .env.example .env

# Edit .env with your Dhan credentials
nano .env

# Start all services
docker-compose up -d

# Check status
docker-compose ps
```

### Step 4: Verify
```bash
# Health check
curl http://localhost:8000/health

# API docs
open http://localhost:8000/docs

# Prometheus metrics
curl http://localhost:8000/metrics

# Grafana dashboard
open http://localhost:3000 (admin/admin)
```

## 📋 Task-wise Implementation

### ✅ Task 1: Instrument Master
- [x] CSV fetch from Dhan
- [x] Redis caching (24h TTL)
- [x] Strike mapping
- [x] ATM detection
- [x] Range builder

### ✅ Task 2: WebSocket Connector
- [x] Async queue (backpressure)
- [x] Redis Pub/Sub
- [x] Exponential reconnect
- [x] Heartbeat handling

### ✅ Task 3: Database
- [x] PostgreSQL 15 partitioned schema
- [x] Weekly partitions
- [x] All tables (strikes, greeks, alerts, trades)

### ✅ Task 4: Greeks Engine
- [x] Black-Scholes model
- [x] All Greeks (delta, gamma, theta, vega, rho)
- [x] Gamma Exposure (GEX)
- [x] Key levels detection

### ✅ Task 5: Risk Engine
- [x] Daily loss limits
- [x] Circuit breaker
- [x] Consecutive loss tracking
- [x] Volatility filters
- [x] Drawdown monitoring

### ✅ Task 6: FastAPI
- [x] JWT authentication
- [x] Rate limiting
- [x] Prometheus metrics
- [x] WebSocket alerts
- [x] REST endpoints

## 🔧 Services

| Service | Port | Description |
|---------|------|-------------|
| FastAPI | 8000 | Main API server |
| PostgreSQL | 5432 | Partitioned database |
| Redis | 6379 | Cache + Pub/Sub |
| Prometheus | 9090 | Metrics collection |
| Grafana | 3000 | Dashboards |

## 📡 API Endpoints

### Authentication
- `POST /auth/token` - Get JWT token

### Instrument Master
- `GET /instruments/underlyings` - List underlyings
- `GET /instruments/{underlying}/strikes` - Get strikes
- `GET /instruments/{underlying}/security-ids` - Get security IDs
- `POST /instruments/refresh` - Refresh master

### Greeks
- `POST /greeks/calculate` - Calculate Greeks
- `POST /greeks/gamma-exposure` - Calculate GEX

### Risk
- `POST /risk/check-trade` - Pre-trade check
- `GET /risk/summary` - Risk summary
- `POST /risk/record-trade` - Record trade

### WebSocket
- `ws://localhost:8000/ws/alerts` - Real-time alerts
- `ws://localhost:8000/ws/ticks` - Real-time ticks

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Async HTTP | httpx + tenacity |
| Queue | Redis Pub/Sub + asyncio.Queue |
| Database | PostgreSQL 15+ (Partitioned) |
| Cache | Redis 7+ |
| ORM | SQLAlchemy 2.0 (async) |
| API | FastAPI + JWT + RateLimit |
| Monitoring | Prometheus + Grafana |
| Container | Docker + Docker Compose |

## 📊 Monitoring

### Prometheus Metrics
- `api_requests_total` - API request counter
- `api_request_latency_seconds` - Request latency
- `active_websockets` - Active WebSocket connections
- `instruments_loaded` - Instruments in master
- `ticks_received_total` - Ticks received

### Grafana Dashboards
Access at `http://localhost:3000`
- Default login: admin/admin

## 🔐 Security

- JWT token authentication
- Rate limiting (100 req/min)
- Circuit breaker for risk
- Environment variable secrets

## 📝 Next Steps

1. Add your Dhan credentials in `.env`
2. Test instrument master refresh
3. Connect WebSocket feed
4. Start receiving ticks
5. Monitor in Grafana

## 🆘 Support

Issues? Check:
1. `docker-compose logs api`
2. `docker-compose logs postgres`
3. `docker-compose logs redis`

---
Built with ❤️ for Indian options traders

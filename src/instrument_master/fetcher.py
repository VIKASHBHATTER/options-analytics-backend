"""
Instrument Master Fetcher Module
================================
Fetches and caches Dhan instrument master data.

Dhan API Sources:
- CSV: https://images.dhan.co/api-data/api-scrip-master.csv
- Detailed CSV: https://images.dhan.co/api-data/api-scrip-master-detailed.csv
- API: https://api.dhan.co/v2/instrument/{exchangeSegment}

Author: Options Analytics Backend
"""

import asyncio
import csv
import json
import logging
from datetime import datetime, timedelta
from io import StringIO
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, asdict

import httpx
import pandas as pd
import redis.asyncio as redis
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Dhan API Constants
DHAN_CSV_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
DHAN_DETAILED_CSV_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
DHAN_API_BASE = "https://api.dhan.co/v2"

# Redis Keys
REDIS_KEY_MASTER = "instrument:master:data"
REDIS_KEY_METADATA = "instrument:master:metadata"
REDIS_KEY_EXPIRY = "instrument:master:expiry_list"
REDIS_TTL_SECONDS = 86400  # 24 hours


@dataclass
class Instrument:
    """Represents a single instrument from Dhan master."""
    security_id: int
    symbol: str
    underlying: str
    strike_price: Optional[float] = None
    option_type: Optional[str] = None  # 'CE' or 'PE'
    expiry: Optional[str] = None
    segment: str = "NSE_FNO"
    exchange: str = "NSE"
    instrument_type: str = "OPTIDX"
    lot_size: int = 50
    tick_size: float = 0.05

    def to_dict(self) -> Dict:
        return asdict(self)

    @property
    def is_option(self) -> bool:
        return self.option_type in ('CE', 'PE')

    @property
    def is_call(self) -> bool:
        return self.option_type == 'CE'

    @property
    def is_put(self) -> bool:
        return self.option_type == 'PE'


@dataclass
class ExpiryInfo:
    """Expiry information for an underlying."""
    underlying: str
    expiry_dates: List[str]
    current_expiry: Optional[str] = None
    next_expiry: Optional[str] = None
    monthly_expiry: Optional[str] = None


class InstrumentMasterFetcher:
    """
    Production-grade instrument master fetcher.

    Features:
    - Async CSV fetch from Dhan
    - Redis caching with TTL
    - Automatic refresh
    - Strike mapping
    - ATM detection
    - Range building
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        client_id: Optional[str] = None,
        access_token: Optional[str] = None,
        cache_ttl: int = REDIS_TTL_SECONDS
    ):
        self.redis = redis_client
        self.client_id = client_id
        self.access_token = access_token
        self.cache_ttl = cache_ttl
        self._instruments: Dict[int, Instrument] = {}
        self._strike_map: Dict[str, int] = {}  # "NIFTY_22500_CE" -> security_id
        self._underlying_strikes: Dict[str, List[float]] = {}  # "NIFTY" -> [22000, 22500, ...]
        self._expiry_map: Dict[str, List[str]] = {}  # "NIFTY" -> ["2026-05-22", ...]
        self._last_updated: Optional[datetime] = None

    async def initialize(self) -> bool:
        """
        Initialize instrument master.
        Try cache first, then fetch from Dhan.
        """
        # Try loading from Redis cache
        cached = await self._load_from_cache()
        if cached:
            logger.info("✅ Instrument master loaded from Redis cache")
            return True

        # Fetch from Dhan API
        success = await self.refresh()
        return success

    async def refresh(self) -> bool:
        """
        Force refresh instrument master from Dhan.
        """
        try:
            logger.info("🔄 Fetching instrument master from Dhan...")

            # Fetch CSV data
            instruments = await self._fetch_csv()

            if not instruments:
                logger.error("❌ No instruments fetched")
                return False

            # Build lookup structures
            self._build_lookups(instruments)

            # Save to Redis
            await self._save_to_cache()

            self._last_updated = datetime.now()
            logger.info(f"✅ Instrument master refreshed: {len(instruments)} instruments")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to refresh instrument master: {e}")
            return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _fetch_csv(self) -> List[Instrument]:
        """
        Fetch instrument master CSV from Dhan.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(DHAN_CSV_URL)
            response.raise_for_status()

        # Parse CSV
        csv_content = response.text
        instruments = []

        # Dhan CSV columns (approximate, may vary):
        # SEM_EXM_EXCH_ID, SEM_SEGMENT, SEM_SMST_SECURITY_ID, SEM_INSTRUMENT_NAME,
        # SEM_EXPIRY_CODE, SEM_TRADING_SYMBOL, SEM_LOT_UNITS, SEM_TICK_SIZE, etc.

        reader = csv.DictReader(StringIO(csv_content))

        for row in reader:
            try:
                # Map Dhan CSV columns to our Instrument model
                # Note: Adjust column names based on actual Dhan CSV format
                instrument = self._parse_csv_row(row)
                if instrument:
                    instruments.append(instrument)
            except Exception as e:
                logger.warning(f"⚠️ Failed to parse row: {e}")
                continue

        return instruments

    def _parse_csv_row(self, row: Dict[str, str]) -> Optional[Instrument]:
        """
        Parse a single CSV row into Instrument object.
        """
        try:
            # Dhan CSV column mappings (verify with actual CSV)
            security_id = int(row.get('SEM_SMST_SECURITY_ID', 0))
            if not security_id:
                return None

            symbol = row.get('SEM_TRADING_SYMBOL', '').strip()
            segment = row.get('SEM_SEGMENT', 'NSE_FNO')

            # Only process NSE F&O segment
            if segment not in ('NSE_FNO', 'BSE_FNO', 'MCX_FUT'):
                return None

            # Parse strike and option type from symbol
            # Example: NIFTY26MAY22500CE -> strike=22500, type=CE
            strike_price = None
            option_type = None
            underlying = None
            expiry = None

            # Extract from symbol pattern
            if 'CE' in symbol[-2:]:
                option_type = 'CE'
                strike_str = symbol[symbol.rfind('CE')-5:symbol.rfind('CE')]
                try:
                    strike_price = float(strike_str)
                except:
                    pass
            elif 'PE' in symbol[-2:]:
                option_type = 'PE'
                strike_str = symbol[symbol.rfind('PE')-5:symbol.rfind('PE')]
                try:
                    strike_price = float(strike_str)
                except:
                    pass

            # Extract underlying (first few chars before date)
            # NIFTY26MAY... -> NIFTY
            if symbol:
                underlying = ''.join([c for c in symbol[:10] if c.isalpha()])
                if not underlying:
                    underlying = symbol.split()[0]

            # Parse expiry from SEM_EXPIRY_DATE or symbol
            expiry_raw = row.get('SEM_EXPIRY_DATE', '')
            if expiry_raw:
                try:
                    expiry = datetime.strptime(expiry_raw, '%Y-%m-%d').strftime('%Y-%m-%d')
                except:
                    expiry = None

            lot_size = int(row.get('SEM_LOT_UNITS', 50))
            tick_size = float(row.get('SEM_TICK_SIZE', 0.05))

            return Instrument(
                security_id=security_id,
                symbol=symbol,
                underlying=underlying or symbol,
                strike_price=strike_price,
                option_type=option_type,
                expiry=expiry,
                segment=segment,
                exchange=segment.split('_')[0] if '_' in segment else 'NSE',
                lot_size=lot_size,
                tick_size=tick_size
            )

        except Exception as e:
            logger.debug(f"Parse error for row: {e}")
            return None

    def _build_lookups(self, instruments: List[Instrument]) -> None:
        """
        Build fast lookup structures from instrument list.
        """
        self._instruments = {}
        self._strike_map = {}
        self._underlying_strikes = {}
        self._expiry_map = {}

        for inst in instruments:
            # Main lookup by security_id
            self._instruments[inst.security_id] = inst

            # Only for options
            if inst.is_option and inst.strike_price and inst.expiry:
                # Strike map: "NIFTY_2026-05-22_22500_CE" -> security_id
                key = f"{inst.underlying}_{inst.expiry}_{inst.strike_price}_{inst.option_type}"
                self._strike_map[key] = inst.security_id

                # Underlying strikes list
                if inst.underlying not in self._underlying_strikes:
                    self._underlying_strikes[inst.underlying] = []
                if inst.strike_price not in self._underlying_strikes[inst.underlying]:
                    self._underlying_strikes[inst.underlying].append(inst.strike_price)

                # Expiry map
                if inst.underlying not in self._expiry_map:
                    self._expiry_map[inst.underlying] = []
                if inst.expiry not in self._expiry_map[inst.underlying]:
                    self._expiry_map[inst.underlying].append(inst.expiry)

        # Sort strikes and expiries
        for underlying in self._underlying_strikes:
            self._underlying_strikes[underlying].sort()
        for underlying in self._expiry_map:
            self._expiry_map[underlying].sort()

    async def _save_to_cache(self) -> None:
        """
        Save instrument data to Redis.
        """
        try:
            # Serialize instruments
            instruments_data = {
                str(sid): inst.to_dict() 
                for sid, inst in self._instruments.items()
            }

            # Save to Redis as hash
            await self.redis.hset(REDIS_KEY_MASTER, mapping={
                'data': json.dumps(instruments_data),
                'strike_map': json.dumps(self._strike_map),
                'underlying_strikes': json.dumps(self._underlying_strikes),
                'expiry_map': json.dumps(self._expiry_map),
                'last_updated': datetime.now().isoformat(),
                'count': str(len(self._instruments))
            })

            # Set TTL
            await self.redis.expire(REDIS_KEY_MASTER, self.cache_ttl)

            logger.info(f"💾 Saved {len(self._instruments)} instruments to Redis")

        except Exception as e:
            logger.error(f"❌ Failed to save to cache: {e}")

    async def _load_from_cache(self) -> bool:
        """
        Load instrument data from Redis cache.
        """
        try:
            cached = await self.redis.hgetall(REDIS_KEY_MASTER)
            if not cached:
                return False

            # Parse data
            data = json.loads(cached.get(b'data', b'{}').decode())
            self._instruments = {
                int(sid): Instrument(**inst_data)
                for sid, inst_data in data.items()
            }

            self._strike_map = json.loads(cached.get(b'strike_map', b'{}').decode())
            self._underlying_strikes = json.loads(cached.get(b'underlying_strikes', b'{}').decode())
            self._expiry_map = json.loads(cached.get(b'expiry_map', b'{}').decode())

            last_updated_str = cached.get(b'last_updated', b'').decode()
            if last_updated_str:
                self._last_updated = datetime.fromisoformat(last_updated_str)

            logger.info(f"📂 Loaded {len(self._instruments)} instruments from cache")
            return True

        except Exception as e:
            logger.warning(f"⚠️ Failed to load from cache: {e}")
            return False

    # ==================== PUBLIC API ====================

    def get_instrument(self, security_id: int) -> Optional[Instrument]:
        """Get instrument by security ID."""
        return self._instruments.get(security_id)

    def get_security_id(
        self, 
        underlying: str, 
        strike: float, 
        option_type: str,
        expiry: Optional[str] = None
    ) -> Optional[int]:
        """
        Get security ID for a specific option contract.

        Args:
            underlying: e.g., 'NIFTY', 'BANKNIFTY'
            strike: Strike price
            option_type: 'CE' or 'PE'
            expiry: Expiry date (YYYY-MM-DD). If None, uses current expiry.

        Returns:
            Security ID or None
        """
        if expiry is None:
            expiry = self.get_current_expiry(underlying)

        key = f"{underlying}_{expiry}_{strike}_{option_type}"
        return self._strike_map.get(key)

    def get_strikes(
        self, 
        underlying: str, 
        expiry: Optional[str] = None
    ) -> List[float]:
        """Get all available strikes for an underlying."""
        strikes = self._underlying_strikes.get(underlying, [])
        return sorted(strikes)

    def get_atm_strike(self, underlying: str, spot_price: float) -> Optional[float]:
        """
        Get ATM (At-The-Money) strike for given spot price.

        NIFTY: 50 point steps
        BANKNIFTY: 100 point steps
        """
        strikes = self.get_strikes(underlying)
        if not strikes:
            return None

        # Find closest strike
        atm_strike = min(strikes, key=lambda x: abs(x - spot_price))
        return atm_strike

    def get_strikes_range(
        self,
        underlying: str,
        spot_price: float,
        range_points: int = 1000,
        step: Optional[int] = None
    ) -> List[float]:
        """
        Get strikes around spot price within range.

        Args:
            underlying: 'NIFTY' or 'BANKNIFTY'
            spot_price: Current spot price
            range_points: +/- range from spot (default 1000)
            step: Strike step (auto-detected if None)

        Returns:
            List of strike prices
        """
        if step is None:
            step = 50 if 'NIFTY' in underlying and 'BANK' not in underlying else 100

        strikes = self.get_strikes(underlying)
        if not strikes:
            return []

        # Filter strikes within range
        min_strike = spot_price - range_points
        max_strike = spot_price + range_points

        return [s for s in strikes if min_strike <= s <= max_strike]

    def get_security_ids_range(
        self,
        underlying: str,
        spot_price: float,
        range_points: int = 1000,
        expiry: Optional[str] = None
    ) -> List[int]:
        """
        Get security IDs for CE and PE options around spot price.

        Returns:
            List of security IDs [CE1, PE1, CE2, PE2, ...]
        """
        strikes = self.get_strikes_range(underlying, spot_price, range_points)
        if not strikes:
            return []

        if expiry is None:
            expiry = self.get_current_expiry(underlying)

        security_ids = []
        for strike in strikes:
            ce_id = self.get_security_id(underlying, strike, 'CE', expiry)
            pe_id = self.get_security_id(underlying, strike, 'PE', expiry)

            if ce_id:
                security_ids.append(ce_id)
            if pe_id:
                security_ids.append(pe_id)

        return security_ids

    def get_current_expiry(self, underlying: str) -> Optional[str]:
        """Get current (nearest) expiry date."""
        expiries = self._expiry_map.get(underlying, [])
        if not expiries:
            return None

        today = datetime.now().strftime('%Y-%m-%d')

        # Find nearest future expiry
        for expiry in expiries:
            if expiry >= today:
                return expiry

        return expiries[-1] if expiries else None

    def get_next_expiry(self, underlying: str) -> Optional[str]:
        """Get next expiry after current."""
        expiries = self._expiry_map.get(underlying, [])
        current = self.get_current_expiry(underlying)

        if not current or not expiries:
            return None

        try:
            idx = expiries.index(current)
            return expiries[idx + 1] if idx + 1 < len(expiries) else None
        except ValueError:
            return None

    def get_monthly_expiry(self, underlying: str) -> Optional[str]:
        """Get monthly expiry (last Thursday of month)."""
        expiries = self._expiry_map.get(underlying, [])
        if not expiries:
            return None

        # Monthly expiry is usually the last one in the month
        # Simple heuristic: find expiry closest to month end
        today = datetime.now()
        month_end = (today.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        monthly = None
        for expiry in expiries:
            exp_date = datetime.strptime(expiry, '%Y-%m-%d')
            if exp_date.month == today.month and exp_date.year == today.year:
                if monthly is None or exp_date > datetime.strptime(monthly, '%Y-%m-%d'):
                    monthly = expiry

        return monthly

    def get_expiries(self, underlying: str) -> List[str]:
        """Get all expiry dates for an underlying."""
        return self._expiry_map.get(underlying, [])

    def get_underlyings(self) -> List[str]:
        """Get all available underlyings."""
        return list(self._underlying_strikes.keys())

    def get_option_chain_summary(self, underlying: str, expiry: Optional[str] = None) -> Dict:
        """
        Get summary of option chain for an underlying.
        """
        if expiry is None:
            expiry = self.get_current_expiry(underlying)

        strikes = self.get_strikes(underlying)

        ce_count = 0
        pe_count = 0

        for strike in strikes:
            if self.get_security_id(underlying, strike, 'CE', expiry):
                ce_count += 1
            if self.get_security_id(underlying, strike, 'PE', expiry):
                pe_count += 1

        return {
            'underlying': underlying,
            'expiry': expiry,
            'total_strikes': len(strikes),
            'ce_contracts': ce_count,
            'pe_contracts': pe_count,
            'spot_range_available': f"{min(strikes)} - {max(strikes)}" if strikes else "N/A"
        }

    @property
    def last_updated(self) -> Optional[datetime]:
        """When was instrument master last updated."""
        return self._last_updated

    @property
    def instrument_count(self) -> int:
        """Total number of instruments loaded."""
        return len(self._instruments)

    async def health_check(self) -> Dict:
        """Health check for instrument master."""
        return {
            'status': 'healthy' if self._instruments else 'uninitialized',
            'instruments_loaded': len(self._instruments),
            'underlyings': len(self._underlying_strikes),
            'last_updated': self._last_updated.isoformat() if self._last_updated else None,
            'cache_ttl': self.cache_ttl,
            'redis_connected': await self.redis.ping()
        }

"""
Greeks Calculator & Gamma Exposure Engine
==========================================
- Black-Scholes model for Greeks
- Gamma Exposure (GEX) calculation
- Delta Exposure calculation
- Institutional-grade risk metrics

Risk-free rate: India 10-year bond ~6.5%
"""

import math
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, date

import numpy as np
from scipy.stats import norm

logger = logging.getLogger(__name__)

# Constants
RISK_FREE_RATE = 0.065  # 6.5% India 10-year bond
NIFTY_LOT_SIZE = 50
BANKNIFTY_LOT_SIZE = 25


@dataclass
class Greeks:
    """Option Greeks for a single contract."""
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    iv: float
    d1: float
    d2: float

    def to_dict(self) -> Dict:
        return {
            'delta': round(self.delta, 6),
            'gamma': round(self.gamma, 6),
            'theta': round(self.theta, 6),
            'vega': round(self.vega, 6),
            'rho': round(self.rho, 6),
            'iv': round(self.iv, 4),
            'd1': round(self.d1, 6),
            'd2': round(self.d2, 6)
        }


@dataclass
class ExposureMetrics:
    """Gamma/Delta exposure metrics."""
    total_gex: float  # In Crores
    total_dex: float  # In Crores
    total_vex: float  # In Crores
    strike_exposures: List[Dict]
    signal: str  # BULLISH / BEARISH / NEUTRAL
    zero_gamma_level: Optional[float] = None

    def to_dict(self) -> Dict:
        return {
            'total_gex': round(self.total_gex, 2),
            'total_dex': round(self.total_dex, 2),
            'total_vex': round(self.total_vex, 2),
            'strike_exposures': self.strike_exposures,
            'signal': self.signal,
            'zero_gamma_level': self.zero_gamma_level
        }


class GreeksCalculator:
    """
    Institutional-grade Greeks calculator.

    Uses Black-Scholes model with continuous dividend yield = 0
    (simplified for Indian index options).
    """

    def __init__(self, risk_free_rate: float = RISK_FREE_RATE):
        self.rfr = risk_free_rate

    def calculate_greeks(
        self,
        spot: float,
        strike: float,
        days_to_expiry: float,
        iv: float,
        option_type: str
    ) -> Greeks:
        """
        Calculate all Greeks for an option.

        Args:
            spot: Current spot price
            strike: Option strike price
            days_to_expiry: Days until expiry
            iv: Implied volatility (in %, e.g., 20 for 20%)
            option_type: 'CE' or 'PE'

        Returns:
            Greeks object
        """
        # Convert inputs
        t = max(days_to_expiry / 365, 0.0001)  # Avoid division by zero
        iv_decimal = iv / 100

        # Calculate d1 and d2
        d1 = self._calculate_d1(spot, strike, t, iv_decimal)
        d2 = d1 - iv_decimal * math.sqrt(t)

        # Calculate Greeks
        if option_type == 'CE':
            delta = norm.cdf(d1)
            theta = (
                -spot * norm.pdf(d1) * iv_decimal / (2 * math.sqrt(t))
                - self.rfr * strike * math.exp(-self.rfr * t) * norm.cdf(d2)
            ) / 365
            rho = strike * t * math.exp(-self.rfr * t) * norm.cdf(d2) / 100
        else:  # PE
            delta = -norm.cdf(-d1)
            theta = (
                -spot * norm.pdf(d1) * iv_decimal / (2 * math.sqrt(t))
                + self.rfr * strike * math.exp(-self.rfr * t) * norm.cdf(-d2)
            ) / 365
            rho = -strike * t * math.exp(-self.rfr * t) * norm.cdf(-d2) / 100

        gamma = norm.pdf(d1) / (spot * iv_decimal * math.sqrt(t))
        vega = spot * norm.pdf(d1) * math.sqrt(t) / 100

        return Greeks(
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            rho=rho,
            iv=iv,
            d1=d1,
            d2=d2
        )

    def _calculate_d1(
        self, 
        spot: float, 
        strike: float, 
        t: float, 
        iv: float
    ) -> float:
        """Calculate d1 parameter for Black-Scholes."""
        return (
            math.log(spot / strike) + 
            (self.rfr + 0.5 * iv ** 2) * t
        ) / (iv * math.sqrt(t))

    def calculate_iv(
        self,
        spot: float,
        strike: float,
        days_to_expiry: float,
        option_price: float,
        option_type: str
    ) -> float:
        """
        Calculate implied volatility using Newton-Raphson method.

        Args:
            spot: Current spot price
            strike: Option strike
            days_to_expiry: Days to expiry
            option_price: Market price of option
            option_type: 'CE' or 'PE'

        Returns:
            Implied volatility (%)
        """
        t = days_to_expiry / 365

        # Initial guess
        iv = 0.3  # 30%

        for _ in range(100):  # Max iterations
            greeks = self.calculate_greeks(spot, strike, days_to_expiry, iv * 100, option_type)

            # Theoretical price (simplified)
            if option_type == 'CE':
                theoretical = (
                    spot * norm.cdf(greeks.d1) - 
                    strike * math.exp(-self.rfr * t) * norm.cdf(greeks.d2)
                )
            else:
                theoretical = (
                    strike * math.exp(-self.rfr * t) * norm.cdf(-greeks.d2) - 
                    spot * norm.cdf(-greeks.d1)
                )

            diff = theoretical - option_price

            if abs(diff) < 0.01:
                return iv * 100

            # Newton-Raphson update
            vega = greeks.vega / 100  # Convert back
            if abs(vega) < 1e-10:
                break

            iv = iv - diff / vega
            iv = max(0.01, min(2.0, iv))  # Bounds

        return iv * 100


class GammaExposureEngine:
    """
    Gamma Exposure (GEX) Calculator.

    Institutional indicator:
    - Positive GEX = Dealers long gamma → Market stabilization (mean reversion)
    - Negative GEX = Dealers short gamma → Market acceleration (trend continuation)
    """

    def __init__(self, greeks_calc: GreeksCalculator):
        self.greeks = greeks_calc

    def calculate_gex(
        self,
        option_chain: List[Dict],
        spot: float,
        underlying: str = 'NIFTY'
    ) -> ExposureMetrics:
        """
        Calculate total Gamma Exposure for option chain.

        Args:
            option_chain: List of strike data with OI, IV, etc.
            spot: Current spot price
            underlying: 'NIFTY' or 'BANKNIFTY'

        Returns:
            ExposureMetrics object
        """
        lot_size = NIFTY_LOT_SIZE if 'BANK' not in underlying else BANKNIFTY_LOT_SIZE

        total_gex = 0.0
        total_dex = 0.0
        total_vex = 0.0
        strike_exposures = []

        for strike_data in option_chain:
            strike = strike_data.get('strike_price', 0)
            if not strike:
                continue

            days = strike_data.get('days_to_expiry', 7)

            for opt_type in ['CE', 'PE']:
                oi = strike_data.get(f'{opt_type.lower()}_oi', 0)
                iv = strike_data.get(f'{opt_type.lower()}_iv', 20)
                ltp = strike_data.get(f'{opt_type.lower()}_ltp', 0)

                if oi <= 0 or iv <= 0:
                    continue

                # Calculate Greeks
                greeks = self.greeks.calculate_greeks(
                    spot, strike, days, iv, opt_type
                )

                # Calculate exposures
                # GEX = Gamma * OI * Lot Size * Spot * 100 (in Rs)
                # Convert to Crores (divide by 10^7)
                gex = greeks.gamma * oi * lot_size * spot * 100 / 1e7
                dex = greeks.delta * oi * lot_size * spot / 1e7
                vex = greeks.vega * oi * lot_size * spot / 1e7

                # PE options have negative delta exposure
                if opt_type == 'PE':
                    dex = -abs(dex)
                    gex = -abs(gex) if greeks.gamma > 0 else abs(gex)

                total_gex += gex
                total_dex += dex
                total_vex += vex

                strike_exposures.append({
                    'strike': strike,
                    'type': opt_type,
                    'oi': oi,
                    'iv': iv,
                    'ltp': ltp,
                    'delta': round(greeks.delta, 4),
                    'gamma': round(greeks.gamma, 6),
                    'gex': round(gex, 2),
                    'dex': round(dex, 2),
                    'vex': round(vex, 2)
                })

        # Determine signal
        if total_gex > 100:  # Positive threshold in Crores
            signal = 'BULLISH'
        elif total_gex < -100:  # Negative threshold
            signal = 'BEARISH'
        else:
            signal = 'NEUTRAL'

        # Find zero gamma level (approximate)
        zero_gamma = self._find_zero_gamma_level(strike_exposures, spot)

        return ExposureMetrics(
            total_gex=total_gex,
            total_dex=total_dex,
            total_vex=total_vex,
            strike_exposures=strike_exposures,
            signal=signal,
            zero_gamma_level=zero_gamma
        )

    def _find_zero_gamma_level(
        self, 
        strike_exposures: List[Dict], 
        spot: float
    ) -> Optional[float]:
        """
        Find strike where gamma exposure crosses zero.
        This is a key support/resistance level.
        """
        # Sort by strike
        sorted_exposures = sorted(strike_exposures, key=lambda x: x['strike'])

        # Find where GEX changes sign
        for i in range(len(sorted_exposures) - 1):
            curr = sorted_exposures[i]
            next_exp = sorted_exposures[i + 1]

            if curr['gex'] * next_exp['gex'] < 0:  # Sign change
                # Linear interpolation
                if abs(next_exp['gex'] - curr['gex']) > 0:
                    ratio = abs(curr['gex']) / abs(next_exp['gex'] - curr['gex'])
                    return curr['strike'] + ratio * (next_exp['strike'] - curr['strike'])

        return None

    def get_key_levels(
        self, 
        exposure: ExposureMetrics,
        spot: float
    ) -> Dict:
        """
        Get key support/resistance levels from GEX data.
        """
        strike_exposures = exposure.strike_exposures

        if not strike_exposures:
            return {}

        # Find max positive and negative GEX strikes
        positive_gex = [s for s in strike_exposures if s['gex'] > 0]
        negative_gex = [s for s in strike_exposures if s['gex'] < 0]

        max_positive = max(positive_gex, key=lambda x: x['gex'], default=None)
        max_negative = min(negative_gex, key=lambda x: x['gex'], default=None)

        # Find strikes with highest OI
        ce_oi = [s for s in strike_exposures if s['type'] == 'CE']
        pe_oi = [s for s in strike_exposures if s['type'] == 'PE']

        max_ce_oi = max(ce_oi, key=lambda x: x['oi'], default=None)
        max_pe_oi = max(pe_oi, key=lambda x: x['oi'], default=None)

        return {
            'spot': spot,
            'max_gamma_resistance': max_positive['strike'] if max_positive else None,
            'max_gamma_support': max_negative['strike'] if max_negative else None,
            'max_call_oi_strike': max_ce_oi['strike'] if max_ce_oi else None,
            'max_put_oi_strike': max_pe_oi['strike'] if max_pe_oi else None,
            'zero_gamma_level': exposure.zero_gamma_level,
            'signal': exposure.signal
        }

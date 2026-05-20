#!/usr/bin/env python3
"""
Dhan API - Historical Daily Data
Daily OHLCV for backtesting
"""

import requests
from datetime import datetime, timedelta
from typing import Dict, List

try:
    from config import CLIENT_ID, ACCESS_TOKEN, BASE_URL, HEADERS
except ImportError:
    import os
    CLIENT_ID = os.getenv('DHAN_CLIENT_ID', '1106299230')
    ACCESS_TOKEN = os.getenv('DHAN_ACCESS_TOKEN', '')
    BASE_URL = 'https://api.dhan.co/v2'
    HEADERS = {
        'access-token': ACCESS_TOKEN,
        'client-id': CLIENT_ID,
        'Content-Type': 'application/json'
    }

def get_historical_data(
    security_id: str,
    from_date: str,
    to_date: str,
    exchange_segment: str = "NSE_EQ",
    instrument: str = "EQUITY"
) -> Dict:
    """Fetch daily historical candles"""
    url = f"{BASE_URL}/charts/historical"
    payload = {
        "securityId": str(security_id),
        "exchangeSegment": exchange_segment,
        "instrument": instrument,
        "expiryCode": 0,
        "fromDate": from_date,
        "toDate": to_date,
        "oi": False
    }
    
    try:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=60)
        return r.json() if r.status_code == 200 else {}
    except Exception as e:
        print(f"Historical Error: {e}")
        return {}

def format_historical(data: Dict) -> List[Dict]:
    """Format historical data"""
    if not data or 'open' not in data:
        return []
    
    candles = []
    for i in range(len(data['open'])):
        candles.append({
            "timestamp": data.get('timestamp', [])[i] if i < len(data.get('timestamp', [])) else 0,
            "date": datetime.fromtimestamp(data.get('timestamp', [])[i]).strftime('%Y-%m-%d') if i < len(data.get('timestamp', [])) else '',
            "open": data['open'][i],
            "high": data.get('high', [])[i] if i < len(data.get('high', [])) else data['open'][i],
            "low": data.get('low', [])[i] if i < len(data.get('low', [])) else data['open'][i],
            "close": data.get('close', [])[i] if i < len(data.get('close', [])) else data['open'][i],
            "volume": data.get('volume', [])[i] if i < len(data.get('volume', [])) else 0,
        })
    return candles

def test_historical():
    """Test historical API"""
    print("=" * 60)
    print("HISTORICAL DAILY DATA")
    print("=" * 60)
    
    security_id = "11536"  # TCS
    
    # Last 5 days
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    
    print(f"\nFetching from {from_date} to {to_date}")
    
    data = get_historical_data(security_id, from_date, to_date)
    candles = format_historical(data)
    
    if candles:
        print(f"   Status: OK ({len(candles)} days)")
        for c in candles:
            print(f"   {c['date']}: O={c['open']} H={c['high']} L={c['low']} C={c['close']} VOL={c['volume']}")
    else:
        print("   Status: FAIL")
    
    print("\n" + "=" * 60)
    print("DONE!")
    print("=" * 60)

if __name__ == '__main__':
    test_historical()

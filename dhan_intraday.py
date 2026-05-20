#!/usr/bin/env python3
"""
Dhan API - Intraday Candles
1min, 5min, 15min, 30min, 60min data
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

INTERVALS = {
    "1min": "1",
    "5min": "5",
    "15min": "15",
    "30min": "30",
    "60min": "60"
}

def get_intraday_data(
    security_id: str,
    interval: str = "5",
    exchange_segment: str = "NSE_EQ",
    instrument: str = "EQUITY",
    from_date: str = None,
    to_date: str = None
) -> Dict:
    """Fetch intraday historical candles"""
    if not from_date:
        today = datetime.now().strftime("%Y-%m-%d")
        from_date = f"{today} 09:15:00"
    if not to_date:
        today = datetime.now().strftime("%Y-%m-%d")
        to_date = f"{today} 15:30:00"
    
    url = f"{BASE_URL}/charts/intraday"
    payload = {
        "securityId": str(security_id),
        "exchangeSegment": exchange_segment,
        "instrument": instrument,
        "interval": interval,
        "fromDate": from_date,
        "toDate": to_date
    }
    
    try:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=60)
        return r.json() if r.status_code == 200 else {}
    except Exception as e:
        print(f"Intraday Error: {e}")
        return {}

def format_candles(data: Dict) -> List[Dict]:
    """Format raw candle data"""
    if not data or 'open' not in data:
        return []
    
    candles = []
    for i in range(len(data['open'])):
        candles.append({
            "timestamp": data.get('timestamp', [])[i] if i < len(data.get('timestamp', [])) else 0,
            "open": data['open'][i],
            "high": data.get('high', [])[i] if i < len(data.get('high', [])) else data['open'][i],
            "low": data.get('low', [])[i] if i < len(data.get('low', [])) else data['open'][i],
            "close": data.get('close', [])[i] if i < len(data.get('close', [])) else data['open'][i],
            "volume": data.get('volume', [])[i] if i < len(data.get('volume', [])) else 0,
            "oi": data.get('oi', [])[i] if i < len(data.get('oi', [])) else 0,
        })
    return candles

def test_intraday():
    """Test intraday APIs"""
    print("=" * 60)
    print("INTRADAY CANDLES")
    print("=" * 60)
    
    security_id = "11536"  # TCS
    
    for name, interval in INTERVALS.items():
        print(f"\n{name} Candles:")
        data = get_intraday_data(security_id, interval)
        candles = format_candles(data)
        
        if candles:
            print(f"   Status: OK ({len(candles)} candles)")
            if len(candles) > 0:
                print(f"   First: O={candles[0]['open']} H={candles[0]['high']} L={candles[0]['low']} C={candles[0]['close']} VOL={candles[0]['volume']}")
                if len(candles) > 1:
                    print(f"   Last:  O={candles[-1]['open']} H={candles[-1]['high']} L={candles[-1]['low']} C={candles[-1]['close']} VOL={candles[-1]['volume']}")
        else:
            print(f"   Status: FAIL (Market might be closed)")
    
    print("\n" + "=" * 60)
    print("DONE!")
    print("=" * 60)

if __name__ == '__main__':
    test_intraday()

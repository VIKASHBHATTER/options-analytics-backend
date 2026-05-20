#!/usr/bin/env python3
"""
Dhan API - All Indices Data
Fetches LTP, OHLC, OI for all major indices
"""

import requests
import json
from typing import Dict, List

# Import unified config
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

# All major indices with their security IDs
INDICES = {
    "NIFTY 50": {"id": 35001, "segment": "IDX_I"},
    "BANKNIFTY": {"id": 35002, "segment": "IDX_I"},
    "FINNIFTY": {"id": 35003, "segment": "IDX_I"},
    "MIDCAPNIFTY": {"id": 35004, "segment": "IDX_I"},
    "SENSEX": {"id": 35005, "segment": "IDX_I"},
    "NIFTY NEXT 50": {"id": 35006, "segment": "IDX_I"},
    "NIFTY 100": {"id": 35007, "segment": "IDX_I"},
    "NIFTY 200": {"id": 35008, "segment": "IDX_I"},
    "NIFTY 500": {"id": 35009, "segment": "IDX_I"},
    "INDIA VIX": {"id": 35010, "segment": "IDX_I"},
}

def get_indices_ltp(indices: Dict = None) -> Dict:
    """Fetch LTP for all indices"""
    if not indices:
        indices = INDICES
    
    url = f"{BASE_URL}/marketfeed/ltp"
    payload = {"IDX_I": [idx["id"] for idx in indices.values()]}
    
    try:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        return r.json() if r.status_code == 200 else {}
    except Exception as e:
        print(f"LTP Error: {e}")
        return {}

def get_indices_ohlc(indices: Dict = None) -> Dict:
    """Fetch OHLC for all indices"""
    if not indices:
        indices = INDICES
    
    url = f"{BASE_URL}/marketfeed/ohlc"
0    payload = {"IDX_I": [idx["id"] for idx in indices.values()]}
    
    try:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        return r.json() if r.status_code == 200 else {}
    except Exception as e:
        print(f"OHLC Error: {e}")
        return {}

def get_indices_quote(indices: Dict = None) -> Dict:
    """Fetch full quote (LTP + OI + Volume) for all indices"""
    if not indices:
        indices = INDICES
    
    url = f"{BASE_URL}/marketfeed/quote"
    payload = {"IDX_I": [idx["id"] for idx in indices.values()]}
    
    try:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        return r.json() if r.status_code == 200 else {}
    except Exception as e:
        print(f"Quote Error: {e}")
        return {}

def format_index_data(data: Dict) -> List[Dict]:
    """Format raw API data into readable list"""
    results = []
    if 'data' not in data:
        return results
    
    for segment, indices in data['data'].items():
        for idx_id, info in indices.items():
            # Find index name by ID
            name = next((k for k, v in INDICES.items() if v["id"] == int(idx_id)), f"ID:{idx_id}")
            results.append({
                "name": name,
                "ltp": info.get('last_price', 0),
                "open": info.get('open', 0),
                "high": info.get('high', 0),
                "low": info.get('low', 0),
                "close": info.get('close', 0),
                "change": info.get('change', 0),
                "volume": info.get('volume', 0),
                "oi": info.get('oi', 0),
            })
    return results

def test_indices():
    """Test all index APIs"""
    print("=" * 60)
    print("ALL INDICES DATA")
    print("=" * 60)
    
    # 1. LTP
    print("\n1. LAST TRADED PRICE (LTP)")
    ltp_data = get_indices_ltp()
    if ltp_data and 'data' in ltp_data:
        for idx in format_index_data(ltp_data):
            print(f"   {idx['name']}: {idx['ltp']}")
    else:
        print("   Status: FAIL")
    
    # 2. OHLC
    print("\n2. OHLC DATA")
    ohlc_data = get_indices_ohlc()
    if ohlc_data and 'data' in ohlc_data:
        for idx in format_index_data(ohlc_data)[:3]:
            print(f"   {idx['name']}: O={idx['open']} H={idx['high']} L={idx['low']} C={idx['close']}")
    else:
        print("   Status: FAIL")
    
    # 3. Full Quote
    print("\n3. FULL QUOTE (LTP + OI + Volume)")
    quote_data = get_indices_quote()
    if quote_data and 'data' in quote_data:
        for idx in format_index_data(quote_data)[:3]:
            print(f"   {idx['name']}: LTP={idx['ltp']}, OI={idx['oi']}, VOL={idx['volume']}")
    else:
        print("   Status: FAIL")
    
    print("\n" + "=" * 60)
    print("DONE!")
    print("=" * 60)

if __name__ == '__main__':
    test_indices()

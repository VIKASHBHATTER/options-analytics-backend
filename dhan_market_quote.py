#!/usr/bin/env python3
"""
Dhan API - Market Quote + Depth
Full market quote and depth for any security
"""

import requests
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

def get_full_quote(security_ids: List[int], exchange: str = "NSE_EQ") -> Dict:
    """Full quote: LTP, OI, Volume, Change, etc."""
    url = f"{BASE_URL}/marketfeed/quote"
    try:
        r = requests.post(url, headers=HEADERS, json={exchange: security_ids}, timeout=30)
        return r.json() if r.status_code == 200 else {}
    except Exception as e:
        print(f"Quote Error: {e}")
        return {}

def get_market_depth(security_ids: List[int], exchange: str = "NSE_EQ") -> Dict:
    """Market depth: Best 5 bid/ask"""
    url = f"{BASE_URL}/marketfeed/depth"
    try:
        r = requests.post(url, headers=HEADERS, json={exchange: security_ids}, timeout=30)
        return r.json() if r.status_code == 200 else {}
    except Exception as e:
        print(f"Depth Error: {e}")
        return {}

def get_ohlc(security_ids: List[int], exchange: str = "NSE_EQ") -> Dict:
    """OHLC data"""
    url = f"{BASE_URL}/marketfeed/ohlc"
    try:
        r = requests.post(url, headers=HEADERS, json={exchange: security_ids}, timeout=30)
        return r.json() if r.status_code == 200 else {}
    except Exception as e:
        print(f"OHLC Error: {e}")
        return {}

def get_ltps(security_ids: List[int], exchange: str = "NSE_EQ") -> Dict:
    """Just LTP (fastest)"""
    url = f"{BASE_URL}/marketfeed/ltp"
    try:
        r = requests.post(url, headers=HEADERS, json={exchange: security_ids}, timeout=30)
        return r.json() if r.status_code == 200 else {}
    except Exception as e:
        print(f"LTP Error: {e}")
        return {}

def test_market_quote():
    """Test market quote APIs"""
    print("=" * 60)
    print("MARKET QUOTE + DEPTH")
    print("=" * 60)
    
    test_ids = [11536, 2885, 341]  # TCS, Reliance, HDFCBANK
    
    # 1. LTP
    print("\n1. LTP (Fast)")
    ltp = get_ltps(test_ids)
    if ltp and 'data' in ltp:
        for seg, data in ltp['data'].items():
            for sid, info in data.items():
                print(f"   ID {sid}: LTP = {info.get('last_price')}")
    else:
        print("   Status: FAIL")
    
    # 2. Full Quote
    print("\n2. FULL QUOTE")
    quote = get_full_quote(test_ids)
    if quote and 'data' in quote:
        for seg, data in quote['data'].items():
            for sid, info in data.items():
                print(f"   ID {sid}: LTP={info.get('last_price')}, OI={info.get('oi')}, VOL={info.get('volume')}")
    else:
        print("   Status: FAIL")
    
    # 3. OHLC
    print("\n3. OHLC")
    ohlc = get_ohlc(test_ids)
    if ohlc and 'data' in ohlc:
        print(f"   Status: OK")
    else:
        print("   Status: FAIL")
    
    # 4. Market Depth
    print("\n4. MARKET DEPTH (Bid/Ask)")
    depth = get_market_depth([11536])
    if depth and 'data' in depth:
        print(f"   Status: OK")
        # Try to show top bid/ask
        try:
            d = depth['data']['NSE_EQ']['11536']
            bids = d.get('bids', [])
            asks = d.get('asks', [])
            if bids:
                print(f"   Top Bid: {bids[0].get('price')} x {bids[0].get('quantity')}")
            if asks:
                print(f"   Top Ask: {asks[0].get('price')} x {asks[0].get('quantity')}")
        except:
            print(f"   Raw: {json.dumps(depth, indent=2)[:200]}")
    else:
        print("   Status: FAIL")
    
    print("\n" + "=" * 60)
    print("DONE!")
    print("=" * 60)

if __name__ == '__main__':
    test_market_quote()

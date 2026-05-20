#!/usr/bin/env python3
"""
Dhan API - Expired/Rolling Options Data
NEW Endpoint: /v2/charts/rollingoption
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

def get_expired_options(
    security_id: int = 13,           # NIFTY = 13
    exchange_segment: str = "NSE_FNO",
    instrument: str = "OPTIDX",      # OPTIDX or OPTSTK
    expiry_flag: str = "MONTH",      # WEEK or MONTH
    expiry_code: int = 1,            # 0=Current, 1=Next, etc.
    strike: str = "ATM",             # ATM, ATM+1, ATM-1, ..., ATM+10
    option_type: str = "CALL",       # CALL or PUT
    interval: str = "1",            # 1, 5, 15, 25, 60 min
    from_date: str = "2021-08-01",
    to_date: str = "2021-09-01",
    required_data: List[str] = None
) -> Dict:
    """
    Fetch expired options data on rolling basis
    Upto last 5 years of data
    """
    if required_data is None:
        required_data = ["open", "high", "low", "close", "volume"]
    
    url = f"{BASE_URL}/charts/rollingoption"
    payload = {
        "exchangeSegment": exchange_segment,
        "interval": interval,
        "securityId": security_id,
        "instrument": instrument,
        "expiryFlag": expiry_flag,
        "expiryCode": expiry_code,
        "strike": strike,
        "drvOptionType": option_type,
        "requiredData": required_data,
        "fromDate": from_date,
        "toDate": to_date
    }
    
    try:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=120)
        return r.json() if r.status_code == 200 else {}
    except Exception as e:
        print(f"Expired Options Error: {e}")
        return {}

def format_expired_data(data: Dict) -> Dict:
    """Format expired options data"""
    if not data or 'data' not in data:
        return {}
    
    result = {"ce": None, "pe": None}
    
    for opt_type in ['ce', 'pe']:
        if data['data'].get(opt_type):
            opt_data = data['data'][opt_type]
            result[opt_type] = {
                "iv": opt_data.get('iv', []),
                "oi": opt_data.get('oi', []),
                "strike": opt_data.get('strike', []),
                "spot": opt_data.get('spot', []),
                "open": opt_data.get('open', []),
                "high": opt_data.get('high', []),
                "low": opt_data.get('low', []),
                "close": opt_data.get('close', []),
                "volume": opt_data.get('volume', []),
                "timestamp": opt_data.get('timestamp', []),
            }
    return result

def test_expired_options():
    """Test expired options API"""
    print("=" * 60)
    print("EXPIRED/ROLLING OPTIONS DATA")
    print("=" * 60)
    
    # Test 1: NIFTY ATM CALL
    print("\n1. NIFTY ATM CALL (Monthly)")
    data = get_expired_options(
        security_id=13,
        expiry_flag="MONTH",
        expiry_code=1,
        strike="ATM",
        option_type="CALL",
        interval="5",
        from_date="2026-04-01",
        to_date="2026-05-01"
    )
    
    if data and 'data' in data:
        formatted = format_expired_data(data)
        if formatted['ce']:
            ce = formatted['ce']
            print(f"   Status: OK")
            print(f"   Data points: {len(ce['open'])}")
            if len(ce['open']) > 0:
                print(f"   First: O={ce['open'][0]} H={ce['high'][0]} L={ce['low'][0]} C={ce['close'][0]}")
                print(f"   IV: {ce['iv'][0] if ce['iv'] else 'N/A'}")
                print(f"   OI: {ce['oi'][0] if ce['oi'] else 'N/A'}")
        else:
            print("   Status: No CE data")
    else:
        print(f"   Status: FAIL - {data.get('error', 'Unknown error')}")
    
    # Test 2: NIFTY ATM PUT
    print("\n2. NIFTY ATM PUT (Monthly)")
    data = get_expired_options(
        security_id=13,
        expiry_flag="MONTH",
        expiry_code=1,
        strike="ATM",
        option_type="PUT",
        interval="5",
        from_date="2026-04-01",
        to_date="2026-05-01"
    )
    
    if data and 'data' in data:
        formatted = format_expired_data(data)
        if formatted['pe']:
            pe = formatted['pe']
            print(f"   Status: OK")
            print(f"   Data points: {len(pe['open'])}")
        else:
            print("   Status: No PE data")
    else:
        print(f"   Status: FAIL")
    
    # Test 3: Different strike
    print("\n3. NIFTY ATM+1 CALL")
    data = get_expired_options(
        security_id=13,
        expiry_flag="MONTH",
        expiry_code=1,
        strike="ATM+1",
        option_type="CALL",
        interval="5",
        from_date="2026-04-01",
        to_date="2026-05-01"
    )
    
    if data and 'data' in data:
        print(f"   Status: OK")
    else:
        print(f"   Status: FAIL")
    
    print("\n" + "=" * 60)
    print("DONE!")
    print("=" * 60)

if __name__ == '__main__':
    test_expired_options()

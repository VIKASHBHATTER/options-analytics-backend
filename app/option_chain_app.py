"""
Option Chain Application Module
Handles all option chain related operations
"""

import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DHAN_CLIENT_ID = os.getenv('DHAN_CLIENT_ID')
DHAN_ACCESS_TOKEN = os.getenv('DHAN_ACCESS_TOKEN')
DHAN_BASE_URL = "https://api.dhan.co"

HEADERS = {
    "access-token": DHAN_ACCESS_TOKEN,
    "client-id": DHAN_CLIENT_ID,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

INDEX_SECURITY_IDS = {
    'NIFTY': '13',
    'BANKNIFTY': '25',
    'FINNIFTY': '27',
    'MIDCPNIFTY': '442',
    'SENSEX': '51',
    'BANKEX': '69'
}

def dhan_post(endpoint, payload):
    """Make POST request to Dhan API"""
    url = f"{DHAN_BASE_URL}{endpoint}"
    try:
        if isinstance(payload, dict):
            payload["dhanClientId"] = DHAN_CLIENT_ID
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=10)
        return resp
    except Exception as e:
        return type('obj', (object,), {
            'status_code': 500, 
            'text': str(e), 
            'json': lambda: {"error": str(e)}
        })()

def get_option_chain(symbol, expiry):
    """Fetch option chain for given symbol and expiry"""
    sec_id = INDEX_SECURITY_IDS.get(symbol.upper())
    if not sec_id:
        return {"error": f"Unknown symbol: {symbol}"}, 400
    
    payload = {
        "UnderlyingScrip": int(sec_id),
        "UnderlyingSeg": "IDX_I",
        "Expiry": expiry
    }
    
    resp = dhan_post("/v2/optionchain", payload)
    
    if resp.status_code == 200:
        data = resp.json()
        
        if data.get('status') == 'success' and 'data' in data and 'oc' in data['data']:
            oc_data = data['data']['oc']
            underlying = data['data'].get('last_price')
            
            chain_list = []
            for strike, options in oc_data.items():
                ce = options.get('ce', {})
                pe = options.get('pe', {})
                
                chain_list.append({
                    'strikePrice': float(strike),
                    'CE': {
                        'lastPrice': ce.get('last_price'),
                        'openInterest': ce.get('oi'),
                        'volume': ce.get('volume'),
                        'impliedVolatility': ce.get('implied_volatility'),
                        'change': ce.get('last_price', 0) - ce.get('previous_close_price', 0),
                        'bid': ce.get('top_bid_price'),
                        'ask': ce.get('top_ask_price'),
                        'previousOI': ce.get('previous_oi'),
                        'previousVolume': ce.get('previous_volume'),
                        'securityId': ce.get('security_id')
                    },
                    'PE': {
                        'lastPrice': pe.get('last_price'),
                        'openInterest': pe.get('oi'),
                        'volume': pe.get('volume'),
                        'impliedVolatility': pe.get('implied_volatility'),
                        'change': pe.get('last_price', 0) - pe.get('previous_close_price', 0),
                        'bid': pe.get('top_bid_price'),
                        'ask': pe.get('top_ask_price'),
                        'previousOI': pe.get('previous_oi'),
                        'previousVolume': pe.get('previous_volume'),
                        'securityId': pe.get('security_id')
                    },
                    'underlyingPrice': underlying
                })
            
            return {
                "status": "success",
                "symbol": symbol.upper(),
                "expiry": expiry,
                "underlying": underlying,
                "strikes_count": len(chain_list),
                "data": chain_list
            }, 200
        else:
            return {
                "status": "error",
                "message": "Invalid response from Dhan API",
                "raw_response": data
            }, 500
    else:
        return {"error": resp.text}, resp.status_code

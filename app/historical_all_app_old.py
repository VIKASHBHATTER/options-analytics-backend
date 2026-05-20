"""
All Indices Historical Data Module
Fetches historical & intraday data for ALL indices
"""

import os
import time
import requests
from datetime import datetime, timedelta
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

# All indices with their security IDs
ALL_INDICES = {
    'NIFTY': {'id': '13', 'segment': 'IDX_I'},
    'BANKNIFTY': {'id': '25', 'segment': 'IDX_I'},
    'FINNIFTY': {'id': '27', 'segment': 'IDX_I'},
    'MIDCPNIFTY': {'id': '442', 'segment': 'IDX_I'},
    'SENSEX': {'id': '51', 'segment': 'IDX_I'},
    'BANKEX': {'id': '69', 'segment': 'IDX_I'}
}

def dhan_post(endpoint, payload):
    """Make POST request to Dhan API"""
    url = f"{DHAN_BASE_URL}{endpoint}"
    try:
        if isinstance(payload, dict):
            payload["dhanClientId"] = DHAN_CLIENT_ID
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=15)
        return resp
    except Exception as e:
        return type('obj', (object,), {
            'status_code': 500, 
            'text': str(e), 
            'json': lambda: {"error": str(e)}
        })()

def get_historical_data(security_id, from_date=None, to_date=None):
    """Fetch daily historical data"""
    # Default: last 30 days
    if not from_date:
        from_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    if not to_date:
        to_date = datetime.now().strftime('%Y-%m-%d')

    payload = {
        "securityId": str(security_id),
        "exchangeSegment": "NSE_EQ",
        "instrument": "INDEX",
        "expiryCode": 0,
        "oi": False,
        "fromDate": from_date,
        "toDate": to_date
    }

    resp = dhan_post("/v2/charts/historical", payload)

    if resp.status_code == 200:
        data = resp.json()
        return {
            "status": "success",
            "security_id": security_id,
            "from_date": from_date,
            "to_date": to_date,
            "candles": len(data.get('timestamp', [])),
            "data": data
        }, 200
    else:
        return {"error": resp.text}, resp.status_code

def get_intraday_data(security_id, interval="15", from_date=None, to_date=None):
    """Fetch intraday data"""
    # Default: today's market hours
    if not from_date:
        today = datetime.now().strftime('%Y-%m-%d')
        from_date = f"{today} 09:15:00"
    if not to_date:
        today = datetime.now().strftime('%Y-%m-%d')
        to_date = f"{today} 15:30:00"

    payload = {
        "securityId": str(security_id),
        "exchangeSegment": "NSE_EQ",
        "instrument": "INDEX",
        "interval": interval,
        "oi": False,
        "fromDate": from_date,
        "toDate": to_date
    }

    resp = dhan_post("/v2/charts/intraday", payload)

    if resp.status_code == 200:
        data = resp.json()
        return {
            "status": "success",
            "security_id": security_id,
            "interval": interval,
            "from_date": from_date,
            "to_date": to_date,
            "candles": len(data.get('timestamp', [])),
            "data": data
        }, 200
    else:
        return {"error": resp.text}, resp.status_code

def get_all_indices_historical(from_date=None, to_date=None):
    """Fetch historical data for ALL indices with delay"""
    results = {}
    errors = {}

    for symbol, info in ALL_INDICES.items():
        sec_id = info['id']

        result, status = get_historical_data(sec_id, from_date, to_date)

        if status == 200:
            results[symbol] = result
        else:
            errors[symbol] = result.get('error', 'Unknown error')

        # ADD DELAY to avoid rate limit (DH-904)
        time.sleep(0.3)  # 300ms delay between requests

    return {
        "status": "completed",
        "time": datetime.now().isoformat(),
        "indices_count": len(ALL_INDICES),
        "successful": len(results),
        "failed": len(errors),
        "data": results,
        "errors": errors
    }

def get_all_indices_intraday(interval="15"):
    """Fetch intraday data for ALL indices with delay"""
    results = {}
    errors = {}

    for symbol, info in ALL_INDICES.items():
        sec_id = info['id']

        result, status = get_intraday_data(sec_id, interval)

        if status == 200:
            results[symbol] = result
        else:
            errors[symbol] = result.get('error', 'Unknown error')

        # ADD DELAY to avoid rate limit
        time.sleep(0.3)  # 300ms delay between requests

    return {
        "status": "completed",
        "time": datetime.now().isoformat(),
        "indices_count": len(ALL_INDICES),
        "successful": len(results),
        "failed": len(errors),
        "data": results,
        "errors": errors
    }

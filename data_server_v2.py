import os
import requests
import time
from datetime import datetime
from flask import Flask, jsonify, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Dhan API Credentials
DHAN_CLIENT_ID = os.getenv('DHAN_CLIENT_ID')
DHAN_ACCESS_TOKEN = os.getenv('DHAN_ACCESS_TOKEN')

# Headers for Dhan API
HEADERS = {
    "access-token": DHAN_ACCESS_TOKEN,
    "client-id": DHAN_CLIENT_ID,
    "Content-Type": "application/json"
}

# Index Security IDs - VERIFIED
INDEX_IDS = {
    'NIFTY': '1',
    'BANKNIFTY': '25',
    'FINNIFTY': '27',
    'MIDCPNIFTY': '442',
    'SENSEX': '51',
    'BANKEX': '56'
}

ALL_INDICES = list(INDEX_IDS.keys())


def dhan_post(endpoint, payload):
    """Make POST request to Dhan API"""
    url = "https://api.dhan.co" + endpoint
    payload["dhanClientId"] = DHAN_CLIENT_ID
    try:
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        else:
            return {"error": resp.text}
    except Exception as e:
        return {"error": str(e)}


@app.route('/')
def home():
    return jsonify({
        "status": "running",
        "server": "Option Analytics Backend",
        "version": "3.0",
        "indices": ALL_INDICES
    })


@app.route('/health')
def health():
    return jsonify({"status": "healthy"})


@app.route('/data/historical-all')
def historical_all():
    """Fetch historical data for ALL indices"""
    from_date = request.args.get('from', '')
    to_date = request.args.get('to', '')

    if not from_date or not to_date:
        return jsonify({"error": "Missing from or to date"}), 400

    results = {
        "successful": 0,
        "failed": 0,
        "data": {},
        "errors": {}
    }

    for symbol in ALL_INDICES:
        # Build payload
        payload = {
            "securityId": INDEX_IDS[symbol],
            "exchangeSegment": "IDX_I",
            "instrument": "INDEX",
            "fromDate": from_date,
            "toDate": to_date
        }

        # Call API
        data = dhan_post("/v2/charts/historical", payload)

        # Check for error
        if "error" in data:
            results["errors"][symbol] = str(data["error"])[:100]
            results["failed"] += 1
        else:
            # Convert to candles
            candles = []
            timestamps = data.get("timestamp", [])
            opens = data.get("open", [])
            highs = data.get("high", [])
            lows = data.get("low", [])
            closes = data.get("close", [])
            volumes = data.get("volume", [])

            for i in range(len(timestamps)):
                candles.append({
                    "date": datetime.fromtimestamp(timestamps[i]).strftime("%Y-%m-%d"),
                    "open": opens[i] if i < len(opens) else 0,
                    "high": highs[i] if i < len(highs) else 0,
                    "low": lows[i] if i < len(lows) else 0,
                    "close": closes[i] if i < len(closes) else 0,
                    "volume": volumes[i] if i < len(volumes) else 0
                })

            results["data"][symbol] = {
                "candles": len(candles),
                "data": candles
            }
            results["successful"] += 1

        # Rate limit delay
        time.sleep(0.3)

    return jsonify(results)


@app.route('/data/historical')
def historical_single():
    """Fetch historical data for single index"""
    symbol = request.args.get("symbol", "").upper()
    from_date = request.args.get("from", "")
    to_date = request.args.get("to", "")

    if not symbol or not from_date or not to_date:
        return jsonify({"error": "Missing params"}), 400

    sec_id = INDEX_IDS.get(symbol)
    if not sec_id:
        return jsonify({"error": "Unknown symbol: " + symbol}), 400

    payload = {
        "securityId": sec_id,
        "exchangeSegment": "IDX_I",
        "instrument": "INDEX",
        "fromDate": from_date,
        "toDate": to_date
    }

    data = dhan_post("/v2/charts/historical", payload)

    if "error" in data:
        return jsonify({"error": data["error"]}), 500

    candles = []
    timestamps = data.get("timestamp", [])
    for i in range(len(timestamps)):
        candles.append({
            "date": datetime.fromtimestamp(timestamps[i]).strftime("%Y-%m-%d"),
            "open": data["open"][i],
            "high": data["high"][i],
            "low": data["low"][i],
            "close": data["close"][i],
            "volume": data["volume"][i]
        })

    return jsonify({
        "symbol": symbol,
        "candles": len(candles),
        "data": candles
    })


if __name__ == "__main__":
    print("=" * 50)
    print("Option Analytics Backend v3.0")
    print("Running on http://0.0.0.0:5000")
    print("=" * 50)
    print("Loaded " + str(len(ALL_INDICES)) + " indices:")
    for idx in ALL_INDICES:
        print("  - " + idx + ": " + INDEX_IDS[idx])
    print("=" * 50)

    app.run(host="0.0.0.0", port=5000, debug=False)

import os
import requests
from flask import Flask, jsonify, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

DHAN_CLIENT_ID = os.getenv('DHAN_CLIENT_ID')
DHAN_ACCESS_TOKEN = os.getenv('DHAN_ACCESS_TOKEN')

HEADERS = {
    "access-token": DHAN_ACCESS_TOKEN,
    "client-id": DHAN_CLIENT_ID,
    "Content-Type": "application/json"
}

INDEX_IDS = {
    'NIFTY': '1',
    'BANKNIFTY': '47',
    'FINNIFTY': '27',
    'MIDCPNIFTY': '128',
    'SENSEX': '51',
    'BANKEX': '56'
}

ALL_INDICES = list(INDEX_IDS.keys())

def dhan_post(endpoint, payload):
    url = f"https://api.dhan.co{endpoint}"
    payload["dhanClientId"] = DHAN_CLIENT_ID
    resp = requests.post(url, headers=HEADERS, json=payload, timeout=10)
    return resp

@app.route('/')
def home():
    return jsonify({"status": "running", "indices": ALL_INDICES})

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/data/historical-all', methods=['GET'])
def historical_all():
    from_date = request.args.get('from', '')
    to_date = request.args.get('to', '')
    
    results = {"successful": 0, "failed": 0, "data": {}, "errors": {}}
    
    for symbol in ALL_INDICES:
        payload = {
            "securityId": INDEX_IDS[symbol],
            "exchangeSegment": "IDX_I",
            "instrument": "INDEX",
            "fromDate": from_date,
            "toDate": to_date
        }
        resp = dhan_post("/v2/charts/historical", payload)
        
        if resp.status_code == 200:
            data = resp.json()
            candles = []
            ts = data.get('timestamp', [])
            for i in range(len(ts)):
                candles.append({
                    "date": __import__('datetime').datetime.fromtimestamp(ts[i]).strftime('%Y-%m-%d'),
                    "open": data['open'][i],
                    "high": data['high'][i],
                    "low": data['low'][i],
                    "close": data['close'][i],
                    "volume": data['volume'][i]
                })
            results["data"][symbol] = {"candles": len(candles), "data": candles}
            results["successful"] += 1
        else:
            results["errors"][symbol] = resp.text[:100]
            results["failed"] += 1
    
    return jsonify(results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

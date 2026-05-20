"""
data_server_v2.py - COMPLETE DhanHQ-py v2.2.0 Integration
All Features: Orders, Market Feed, Market Depth, Portfolio, Historical Data
"""
import os
import sys
import time
import json
import requests
from datetime import datetime
from flask import Flask, jsonify, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ============================================
# CONFIGURATION
# ============================================
DHAN_CLIENT_ID = os.getenv('DHAN_CLIENT_ID')
DHAN_ACCESS_TOKEN = os.getenv('DHAN_ACCESS_TOKEN')

HEADERS = {
    "access-token": DHAN_ACCESS_TOKEN,
    "client-id": DHAN_CLIENT_ID,
    "Content-Type": "application/json",
    "Accept": "application/json"
}

# Index mappings
INDEX_IDS = {
    'NIFTY': '1',
    'BANKNIFTY': '25',
    'FINNIFTY': '27',
    'MIDCPNIFTY': '442',
    'SENSEX': '51',
    'BANKEX': '56'
}

ALL_INDICES = list(INDEX_IDS.keys())

# ============================================
# DHANHQ-PY INTEGRATION (if available)
# ============================================
USE_DHANHQ = False
dhan = None

try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'dhanhq_src'))
    from dhanhq import DhanContext, dhanhq
    dhan_context = DhanContext(DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN)
    dhan = dhanhq(dhan_context)
    USE_DHANHQ = True
    print("✅ DhanHQ-py v2.2.0 loaded")
except Exception as e:
    print(f"⚠️ DhanHQ-py not available: {e}")
    print("⚠️ Using HTTP fallback")

# ============================================
# HTTP FALLBACK FUNCTIONS
# ============================================
def dhan_post(endpoint, payload):
    """POST request to Dhan API"""
    url = f"https://api.dhan.co{endpoint}"
    if isinstance(payload, dict):
        payload["dhanClientId"] = DHAN_CLIENT_ID
    try:
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=10)
        return resp.json() if resp.status_code == 200 else {"error": resp.text, "status": resp.status_code}
    except Exception as e:
        return {"error": str(e)}

def dhan_get(endpoint):
    """GET request to Dhan API"""
    url = f"https://api.dhan.co{endpoint}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        return resp.json() if resp.status_code == 200 else {"error": resp.text}
    except Exception as e:
        return {"error": str(e)}

# ============================================
# HELPER FUNCTIONS
# ============================================
def convert_to_candles(data):
    """Convert Dhan array response to candle format"""
    candles = []
    timestamps = data.get('start_Time', data.get('timestamp', []))
    opens = data.get('open', [])
    highs = data.get('high', [])
    lows = data.get('low', [])
    closes = data.get('close', [])
    volumes = data.get('volume', [])

    for i in range(len(timestamps)):
        candles.append({
            "date": datetime.fromtimestamp(timestamps[i]).strftime('%Y-%m-%d'),
            "open": opens[i] if i < len(opens) else 0,
            "high": highs[i] if i < len(highs) else 0,
            "low": lows[i] if i < len(lows) else 0,
            "close": closes[i] if i < len(closes) else 0,
            "volume": volumes[i] if i < len(volumes) else 0
        })
    return candles

# ============================================
# ROUTES: HOME & HEALTH
# ============================================

@app.route('/')
def home():
    return jsonify({
        "status": "running",
        "server": "Option Analytics Backend",
        "version": "4.0 (DhanHQ Complete)",
        "dhanhq": USE_DHANHQ,
        "indices": ALL_INDICES,
        "features": [
            "historical_data",
            "option_chain",
            "market_quote",
            "order_management",
            "portfolio",
            "market_depth"
        ]
    })

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "dhanhq": USE_DHANHQ,
        "time": datetime.now().isoformat()
    })

# ============================================
# ROUTES: HISTORICAL DATA (Already Working)
# ============================================

@app.route('/data/historical')
def historical_single():
    symbol = request.args.get('symbol', '').upper()
    from_date = request.args.get('from', '')
    to_date = request.args.get('to', '')

    if not symbol or not from_date or not to_date:
        return jsonify({"error": "Missing params"}), 400

    sec_id = INDEX_IDS.get(symbol)
    if not sec_id:
        return jsonify({"error": f"Unknown: {symbol}"}), 400

    data = dhan_post("/v2/charts/historical", {
        "securityId": sec_id,
        "exchangeSegment": "IDX_I",
        "instrument": "INDEX",
        "fromDate": from_date,
        "toDate": to_date
    })

    if 'error' in data:
        return jsonify(data), 500

    candles = convert_to_candles(data)
    return jsonify({
        "symbol": symbol,
        "candles": len(candles),
        "data": candles
    })

@app.route('/data/historical-all')
def historical_all():
    from_date = request.args.get('from', '')
    to_date = request.args.get('to', '')

    if not from_date or not to_date:
        return jsonify({"error": "Missing params"}), 400

    results = {"successful": 0, "failed": 0, "data": {}, "errors": {}}

    for symbol in ALL_INDICES:
        data = dhan_post("/v2/charts/historical", {
            "securityId": INDEX_IDS[symbol],
            "exchangeSegment": "IDX_I",
            "instrument": "INDEX",
            "fromDate": from_date,
            "toDate": to_date
        })

        if 'error' in data:
            results["errors"][symbol] = str(data['error'])[:100]
            results["failed"] += 1
        else:
            results["data"][symbol] = {
                "candles": len(convert_to_candles(data)),
                "data": convert_to_candles(data)
            }
            results["successful"] += 1

        time.sleep(0.3)

    return jsonify(results)

# ============================================
# ROUTES: OPTION CHAIN (Already Working)
# ============================================

@app.route('/data/expiry-list/<symbol>')
def expiry_list(symbol):
    sec_id = INDEX_IDS.get(symbol.upper())
    if not sec_id:
        return jsonify({"error": f"Unknown: {symbol}"}), 400

    data = dhan_post("/v2/optionchain/expirylist", {
        "UnderlyingScrip": int(sec_id),
        "UnderlyingSeg": "IDX_I"
    })
    return jsonify(data)

@app.route('/data/option-chain/<symbol>/<expiry>')
def option_chain(symbol, expiry):
    sec_id = INDEX_IDS.get(symbol.upper())
    if not sec_id:
        return jsonify({"error": f"Unknown: {symbol}"}), 400

    data = dhan_post("/v2/optionchain", {
        "UnderlyingScrip": int(sec_id),
        "UnderlyingSeg": "IDX_I",
        "Expiry": expiry
    })
    return jsonify(data)

# ============================================
# ROUTES: PORTFOLIO (Already Working)
# ============================================

@app.route('/data/funds')
def get_funds():
    if USE_DHANHQ:
        return jsonify(dhan.get_fund_limits())
    return jsonify(dhan_get("/v2/fundlimit"))

@app.route('/data/positions')
def get_positions():
    if USE_DHANHQ:
        return jsonify(dhan.get_positions())
    return jsonify(dhan_get("/v2/positions"))

@app.route('/data/holdings')
def get_holdings():
    if USE_DHANHQ:
        return jsonify(dhan.get_holdings())
    return jsonify(dhan_get("/v2/holdings"))

@app.route('/data/orders')
def get_orders():
    if USE_DHANHQ:
        return jsonify(dhan.get_order_list())
    return jsonify(dhan_get("/v2/orders"))

# ============================================
# ROUTES: MARKET QUOTE (NEW)
# ============================================

@app.route('/data/quote/<symbol>')
def market_quote(symbol):
    """Get real-time market quote for an index"""
    sec_id = INDEX_IDS.get(symbol.upper())
    if not sec_id:
        return jsonify({"error": f"Unknown: {symbol}"}), 400

    # Use DhanHQ-py if available
    if USE_DHANHQ:
        try:
            data = dhan.ohlc_data({
                " securities": {"IDX_I": [int(sec_id)]}
            })
            return jsonify(data)
        except:
            pass

    # Fallback to HTTP
    data = dhan_post("/v2/market/quote", {
        "securityId": sec_id,
        "exchangeSegment": "IDX_I",
        "instrument": "INDEX"
    })
    return jsonify(data)

@app.route('/data/quote-all')
def market_quote_all():
    """Get real-time quotes for ALL indices"""
    results = {"successful": 0, "failed": 0, "data": {}, "errors": {}}

    for symbol in ALL_INDICES:
        sec_id = INDEX_IDS[symbol]

        data = dhan_post("/v2/market/quote", {
            "securityId": sec_id,
            "exchangeSegment": "IDX_I",
            "instrument": "INDEX"
        })

        if 'error' in data:
            results["errors"][symbol] = str(data['error'])[:100]
            results["failed"] += 1
        else:
            results["data"][symbol] = data
            results["successful"] += 1

        time.sleep(0.2)

    return jsonify(results)

# ============================================
# ROUTES: ORDER MANAGEMENT (NEW)
# ============================================

@app.route('/order/place', methods=['POST'])
def place_order():
    """Place a new order"""
    data = request.json

    required = ['security_id', 'exchange', 'side', 'quantity', 'order_type', 'product']
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing: {field}"}), 400

    order_payload = {
        "dhanClientId": DHAN_CLIENT_ID,
        "transactionType": data['side'],  # BUY / SELL
        "exchangeSegment": data['exchange'],  # NSE_EQ / NSE_FNO / BSE_EQ / IDX_I
        "productType": data['product'],  # CNC / INTRADAY / MARGIN / CO / BO
        "orderType": data['order_type'],  # MARKET / LIMIT / SL / SL-M
        "validity": data.get('validity', 'DAY'),
        "securityId": str(data['security_id']),
        "quantity": int(data['quantity']),
        "disclosedQuantity": data.get('disclosed_quantity', 0),
        "price": float(data.get('price', 0)),
        "triggerPrice": float(data.get('trigger_price', 0)),
        "afterMarket": data.get('after_market', False),
        "boProfitValue": float(data.get('bo_profit', 0)),
        "boStopLossValue": float(data.get('bo_stoploss', 0))
    }

    # Use DhanHQ-py if available
    if USE_DHANHQ:
        try:
            result = dhan.place_order(**order_payload)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # Fallback to HTTP
    result = dhan_post("/v2/orders", order_payload)
    return jsonify(result)

@app.route('/order/modify', methods=['POST'])
def modify_order():
    """Modify existing order"""
    data = request.json

    if 'order_id' not in data:
        return jsonify({"error": "Missing order_id"}), 400

    modify_payload = {
        "dhanClientId": DHAN_CLIENT_ID,
        "orderId": data['order_id'],
        "orderType": data.get('order_type', 'LIMIT'),
        "quantity": int(data.get('quantity', 0)),
        "price": float(data.get('price', 0)),
        "disclosedQuantity": data.get('disclosed_quantity', 0),
        "triggerPrice": float(data.get('trigger_price', 0)),
        "validity": data.get('validity', 'DAY')
    }

    if USE_DHANHQ:
        try:
            result = dhan.modify_order(**modify_payload)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    result = dhan_post("/v2/orders", modify_payload)
    return jsonify(result)

@app.route('/order/cancel/<order_id>', methods=['DELETE'])
def cancel_order(order_id):
    """Cancel an order"""
    if USE_DHANHQ:
        try:
            result = dhan.cancel_order(order_id)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    result = dhan_post("/v2/orders", {
        "dhanClientId": DHAN_CLIENT_ID,
        "orderId": order_id
    })
    return jsonify(result)

@app.route('/order/<order_id>')
def get_order_by_id(order_id):
    """Get order details by ID"""
    if USE_DHANHQ:
        try:
            result = dhan.get_order_by_id(order_id)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    result = dhan_get(f"/v2/orders/{order_id}")
    return jsonify(result)

# ============================================
# ROUTES: MARKET DEPTH (NEW)
# ============================================

@app.route('/data/depth/<symbol>')
def market_depth(symbol):
    """Get full market depth (20 level) for an index"""
    sec_id = INDEX_IDS.get(symbol.upper())
    if not sec_id:
        return jsonify({"error": f"Unknown: {symbol}"}), 400

    if USE_DHANHQ:
        try:
            # DhanHQ-py full depth
            from dhanhq import FullDepth
            depth = FullDepth(dhan_context, [(1, int(sec_id))], 20)
            return jsonify(depth.get_data())
        except:
            pass

    # Fallback to HTTP
    data = dhan_post("/v2/market/depth", {
        "securityId": sec_id,
        "exchangeSegment": "IDX_I"
    })
    return jsonify(data)

# ============================================
# ROUTES: INTRADAY DATA (NEW)
# ============================================

@app.route('/data/intraday/<symbol>')
def intraday_data(symbol):
    """Get intraday minute data for an index"""
    sec_id = INDEX_IDS.get(symbol.upper())
    if not sec_id:
        return jsonify({"error": f"Unknown: {symbol}"}), 400

    interval = request.args.get('interval', '15')  # 1, 5, 15, 25, 60
    from_date = request.args.get('from', '')
    to_date = request.args.get('to', '')

    payload = {
        "securityId": sec_id,
        "exchangeSegment": "IDX_I",
        "instrument": "INDEX",
        "interval": interval
    }

    if from_date and to_date:
        payload["fromDate"] = from_date
        payload["toDate"] = to_date

    data = dhan_post("/v2/charts/intraday", payload)
    return jsonify(data)

# ============================================
# MAIN
# ============================================

if __name__ == '__main__':
    print("=" * 60)
    print("Option Analytics Backend v4.0 - COMPLETE")
    print("=" * 60)
    print(f"DhanHQ-py: {'✅' if USE_DHANHQ else '❌ Fallback'}")
    print(f"Indices: {len(ALL_INDICES)}")
    for idx in ALL_INDICES:
        print(f"  - {idx}: {INDEX_IDS[idx]}")
    print("=" * 60)
    print("Features:")
    print("  ✅ Historical Data")
    print("  ✅ Option Chain")
    print("  ✅ Market Quote")
    print("  ✅ Order Management")
    print("  ✅ Portfolio")
    print("  ✅ Market Depth")
    print("  ✅ Intraday Data")
    print("=" * 60)

    app.run(host='0.0.0.0', port=5000, debug=False)

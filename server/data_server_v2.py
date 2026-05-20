"""
Flask Server Module
Main API server - imports from app modules
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask, jsonify, request
from datetime import datetime
from dotenv import load_dotenv

# Import from app modules
from app.historical_all_app import get_all_indices_historical, get_all_indices_intraday

from app.option_chain_app import get_option_chain
from app.expiry_app import get_expiry_list
from database import (
    init_db, save_option_chain, save_expiry_list, save_oi_analysis,
    get_db_stats, get_latest_option_chain, get_oi_trend, get_pcr_history,
    get_latest_pcr, get_price_history, get_expiries, get_scans,
    save_scan, cleanup_old_data, INDICES
)

load_dotenv()

app = Flask(__name__)

# ─── HOME & HEALTH ─────────────────────────────────────────────

@app.route('/')
def home():
    return jsonify({
        "status": "running",
        "server": "Option Analytics Backend",
        "version": "2.1",
        "time": datetime.now().isoformat(),
        "tracking_indices": INDICES,
        "modules": {
            "option_chain": "/data/option-chain/<symbol>/<expiry>",
            "expiry_list": "/data/expiry-list/<symbol>",
            "fetch_all": "POST /data/fetch-all"
        }
    })

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "database": "connected",
        "time": datetime.now().isoformat()
    })

# ─── OPTION CHAIN ────────────────────────────────────────────────

@app.route('/data/option-chain/<symbol>/<expiry>', methods=['GET'])
def option_chain(symbol, expiry):
    """Get option chain - uses app/option_chain_app.py"""
    result, status_code = get_option_chain(symbol, expiry)
    
    if status_code == 200 and result.get('status') == 'success':
        # Save to database
        save_option_chain(result['data'], symbol.upper(), expiry, result.get('underlying'))
        
        # Calculate OI
        total_ce_oi = sum(item['CE']['openInterest'] or 0 for item in result['data'])
        total_pe_oi = sum(item['PE']['openInterest'] or 0 for item in result['data'])
        save_oi_analysis(symbol.upper(), expiry, total_ce_oi, total_pe_oi)
    
    return jsonify(result), status_code

# ─── EXPIRY LIST ─────────────────────────────────────────────────

@app.route('/data/expiry-list/<symbol>', methods=['GET'])
def expiry_list(symbol):
    """Get expiry list - uses app/expiry_app.py"""
    result, status_code = get_expiry_list(symbol)
    
    if status_code == 200 and result.get('status') == 'success':
        save_expiry_list(symbol.upper(), result['expiries'])
    
    return jsonify(result), status_code

# ─── FETCH ALL ───────────────────────────────────────────────────

@app.route('/data/fetch-all', methods=['POST'])
def fetch_all():
    """Fetch all indices and all expiries"""
    results = {}
    
    for symbol in INDICES:
        # Get expiries
        exp_result, exp_status = get_expiry_list(symbol)
        if exp_status != 200:
            results[symbol] = {"error": "Failed to get expiries"}
            continue
        
        expiries = exp_result.get('expiries', [])
        save_expiry_list(symbol, expiries)
        
        # Fetch option chain for each expiry
        chains = []
        for expiry in expiries[:3]:  # Limit to first 3 expiries
            chain_result, chain_status = get_option_chain(symbol, expiry)
            if chain_status == 200:
                chains.append({
                    "expiry": expiry,
                    "strikes": chain_result.get('strikes_count', 0)
                })
        
        results[symbol] = {
            "expiries_found": len(expiries),
            "chains_fetched": len(chains),
            "chains": chains
        }
    
    return jsonify({
        "status": "completed",
        "time": datetime.now().isoformat(),
        "results": results
    })

# ─── ANALYTICS ───────────────────────────────────────────────────

@app.route('/data/history/<symbol>/<expiry>', methods=['GET'])
def get_history(symbol, expiry):
    limit = request.args.get('limit', 1, type=int)
    data = get_latest_option_chain(symbol.upper(), expiry, limit)
    return jsonify({
        "symbol": symbol.upper(),
        "expiry": expiry,
        "records": len(data),
        "data": data
    })

@app.route('/data/oi-trend/<symbol>/<expiry>', methods=['GET'])
def oi_trend(symbol, expiry):
    minutes = request.args.get('minutes', 30, type=int)
    data = get_oi_trend(symbol.upper(), expiry, minutes)
    return jsonify({
        "symbol": symbol.upper(),
        "expiry": expiry,
        "minutes": minutes,
        "records": len(data),
        "data": data
    })

@app.route('/data/pcr/<symbol>/<expiry>', methods=['GET'])
def pcr_data(symbol, expiry):
    limit = request.args.get('limit', 50, type=int)
    history = get_pcr_history(symbol.upper(), expiry, limit)
    latest = get_latest_pcr(symbol.upper(), expiry)
    return jsonify({
        "symbol": symbol.upper(),
        "expiry": expiry,
        "latest_pcr": latest['pcr'] if latest else None,
        "records": len(history),
        "history": history
    })

@app.route('/data/price-history/<symbol>', methods=['GET'])
def price_history(symbol):
    minutes = request.args.get('minutes', 60, type=int)
    data = get_price_history(symbol.upper(), minutes)
    return jsonify({
        "symbol": symbol.upper(),
        "minutes": minutes,
        "records": len(data),
        "data": data
    })

@app.route('/data/expiries/<symbol>', methods=['GET'])
def get_symbol_expiries(symbol):
    current_only = request.args.get('current', 'false').lower() == 'true'
    data = get_expiries(symbol.upper(), current_only)
    return jsonify({
        "symbol": symbol.upper(),
        "current_month_only": current_only,
        "expiries": data
    })

# ─── SYSTEM ──────────────────────────────────────────────────────

@app.route('/data/stats', methods=['GET'])
def db_stats():
    stats = get_db_stats()
    return jsonify({
        "database_stats": stats,
        "tracking_indices": INDICES,
        "time": datetime.now().isoformat()
    })

@app.route('/data/indices', methods=['GET'])
def list_indices():
    return jsonify({
        "indices": INDICES,
        "security_ids": {
            'NIFTY': '13',
            'BANKNIFTY': '25',
            'FINNIFTY': '27',
            'MIDCPNIFTY': '442',
            'SENSEX': '51',
            'BANKEX': '69'
        }
    })

@app.route('/data/cleanup', methods=['POST'])
def cleanup():
    days = request.get_json().get('days', 7) if request.is_json else 7
    cleanup_old_data(days)
    return jsonify({"message": f"Cleaned data older than {days} days"})


@app.route('/data/historical-all', methods=['GET'])
def historical_all():
    """Get historical data for ALL indices"""
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    
    result = get_all_indices_historical(from_date, to_date)
    return jsonify(result)

@app.route('/data/intraday-all', methods=['GET'])
def intraday_all():
    """Get intraday data for ALL indices"""
    interval = request.args.get('interval', '15')
    
    result = get_all_indices_intraday(interval)
    return jsonify(result)

@app.route('/data/historical/<security_id>', methods=['GET'])
def historical_single(security_id):
    """Get historical data for single index"""
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    
    from app.historical_all_app import get_historical_data
    result, status = get_historical_data(security_id, from_date, to_date)
    return jsonify(result), status

@app.route('/data/intraday/<security_id>', methods=['GET'])
def intraday_single(security_id):
    """Get intraday data for single index"""
    interval = request.args.get('interval', '15')
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    
    from app.historical_all_app import get_intraday_data
    result, status = get_intraday_data(security_id, interval, from_date, to_date)
    return jsonify(result), status


# ─── MAIN ────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    print("=" * 50)
    print("  OPTION ANALYTICS BACKEND v2.1")
    print("  Modular Architecture")
    print("  Running on: http://0.0.0.0:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False)

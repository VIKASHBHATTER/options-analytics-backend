from flask import Flask, jsonify
import os
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)

class DhanData:
    BASE = "https://api.dhan.co/v2"
    
    def __init__(self):
        self.headers = {
            'access-token': os.getenv('DHAN_ACCESS_TOKEN'),
            'client-id': os.getenv('DHAN_CLIENT_ID'),
            'Content-type': 'application/json',
            'Accept': 'application/json'
        }
    
    def _get(self, endpoint):
        return requests.get(f"{self.BASE}{endpoint}", headers=self.headers, timeout=10).json()
    
    def _post(self, endpoint, payload):
        return requests.post(f"{self.BASE}{endpoint}", json=payload, headers=self.headers, timeout=10).json()

dhan = DhanData()

# ============ RAW DATA ENDPOINTS ============

@app.route('/data/funds')
def funds():
    """Raw fund limits"""
    return jsonify(dhan._get('/fundlimit'))

@app.route('/data/positions')
def positions():
    """Raw positions"""
    return jsonify(dhan._get('/positions'))

@app.route('/data/orders')
def orders():
    """Raw orders"""
    return jsonify(dhan._get('/orders'))

@app.route('/data/holdings')
def holdings():
    """Raw holdings"""
    return jsonify(dhan._get('/holdings'))

@app.route('/data/option-chain/<expiry>')
def option_chain(expiry):
    """Raw option chain"""
    payload = {
        "UnderlyingScrip": 13,
        "UnderlyingSeg": "IDX_I",
        "Expiry": expiry
    }
    return jsonify(dhan._post('/optionchain', payload))

@app.route('/data/expiry-list')
def expiry_list():
    """Raw expiry list"""
    payload = {
        "UnderlyingScrip": 13,
        "UnderlyingSeg": "IDX_I"
    }
    return jsonify(dhan._post('/optionchain/expirylist', payload))

@app.route('/data/intraday/<security_id>')
def intraday(security_id):
    """Raw intraday candles"""
    payload = {
        "securityId": security_id,
        "exchangeSegment": "IDX_I",
        "instrument": "INDEX",
        "interval": 1,
        "fromDate": (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),
        "toDate": datetime.now().strftime("%Y-%m-%d")
    }
    return jsonify(dhan._post('/charts/intraday', payload))

@app.route('/data/historical/<security_id>')
def historical(security_id):
    """Raw historical daily"""
    payload = {
        "securityId": security_id,
        "exchangeSegment": "IDX_I",
        "instrument": "INDEX",
        "fromDate": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
        "toDate": datetime.now().strftime("%Y-%m-%d")
    }
    return jsonify(dhan._post('/charts/historical', payload))

@app.route('/data/margin-calculator', methods=['POST'])
def margin_calculator():
    """Raw margin calc - pass JSON body"""
    return jsonify(dhan._post('/margincalculator', request.json))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

import os
import requests
from dotenv import load_dotenv

load_dotenv()

class DhanClient:
    BASE = "https://api.dhan.co/v2"
    
    def __init__(self):
        self.headers = {
            'access-token': os.getenv('DHAN_ACCESS_TOKEN'),
            'client-id': os.getenv('DHAN_CLIENT_ID'),
            'Content-type': 'application/json',
            'Accept': 'application/json'
        }
    
    def get_funds(self):
        """Get available balance, margin, collateral"""
        r = requests.get(f"{self.BASE}/fundlimit", headers=self.headers, timeout=10)
        return r.json()
    
    def get_positions(self):
        """Get all open positions"""
        r = requests.get(f"{self.BASE}/positions", headers=self.headers, timeout=10)
        return r.json()
    
    def get_orders(self):
        """Get order book"""
        r = requests.get(f"{self.BASE}/orders", headers=self.headers, timeout=10)
        return r.json()
    
    def get_holdings(self):
        """Get holdings (stocks in demat)"""
        r = requests.get(f"{self.BASE}/holdings", headers=self.headers, timeout=10)
        return r.json()
    
    def get_intraday_data(self, security_id, exchange="IDX_I", instrument="INDEX", interval=1):
        """Get intraday minute candles (last 5 days)"""
        from datetime import datetime, timedelta
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        
        payload = {
            "securityId": str(security_id),
            "exchangeSegment": exchange,
            "instrument": instrument,
            "interval": interval,
            "fromDate": from_date,
            "toDate": to_date
        }
        r = requests.post(f"{self.BASE}/charts/intraday", json=payload, headers=self.headers, timeout=10)
        return r.json()
    
    def get_historical_data(self, security_id, exchange="IDX_I", instrument="INDEX", from_date=None, to_date=None):
        """Get daily OHLC data"""
        if not to_date:
            from datetime import datetime
            to_date = datetime.now().strftime("%Y-%m-%d")
        if not from_date:
            from datetime import datetime, timedelta
            from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            
        payload = {
            "securityId": str(security_id),
            "exchangeSegment": exchange,
            "instrument": instrument,
            "fromDate": from_date,
            "toDate": to_date
        }
        r = requests.post(f"{self.BASE}/charts/historical", json=payload, headers=self.headers, timeout=10)
        return r.json()

# Test
if __name__ == "__main__":
    dhan = DhanClient()
    
    print("="*60)
    print("💰 FUNDS")
    print("="*60)
    funds = dhan.get_funds()
    print(f"Available Balance: ₹{funds.get('availableBalance', 'N/A')}")
    print(f"SOD Limit: ₹{funds.get('sodLimit', 'N/A')}")
    print(f"Withdrawable: ₹{funds.get('withdrawableBalance', 'N/A')}")
    
    print("\n" + "="*60)
    print("🎯 POSITIONS")
    print("="*60)
    positions = dhan.get_positions()
    if positions:
        for pos in positions:
            print(f"Symbol: {pos.get('tradingSymbol')}")
            print(f"Type: {pos.get('positionType')}")
            print(f"Realized P&L: ₹{pos.get('realizedProfit', 0)}")
            print("-"*40)
    else:
        print("No open positions")
    
    print("\n" + "="*60)
    print("📊 SENSEX INTRADAY (Security ID: 1)")
    print("="*60)
    data = dhan.get_intraday_data(1)
    if 'open' in data:
        print(f"Candles: {len(data['open'])}")
        print(f"Latest Close: {data['close'][-1] if data['close'] else 'N/A'}")

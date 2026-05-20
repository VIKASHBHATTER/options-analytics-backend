#!/usr/bin/env python3
"""
Dhan API - WebSocket Live Feed
Real-time ticks for LTP, Volume, OI
"""

import websocket
import json
import os
import time
import threading

try:
    from config import CLIENT_ID, ACCESS_TOKEN
except ImportError:
    CLIENT_ID = os.getenv('DHAN_CLIENT_ID', '1106299230')
    ACCESS_TOKEN = os.getenv('DHAN_ACCESS_TOKEN', '')

class DhanLiveFeed:
    def __init__(self):
        self.ws = None
        self.connected = False
        self.tick_count = 0
        self.subscriptions = []
    
    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            self.tick_count += 1
            
            # Parse tick data
            if 'LTP' in str(data):
                print(f"\n[TICK #{self.tick_count}] {json.dumps(data, indent=2)}")
            else:
                print(f"\n[MSG] {json.dumps(data, indent=2)}")
                
        except Exception as e:
            print(f"\n[RAW] {message}")
    
    def on_error(self, ws, error):
        print(f"\n[ERROR] {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        self.connected = False
        print(f"\n[CLOSED] Status: {close_status_code}, Reason: {close_msg}")
    
    def on_open(self, ws):
        self.connected = True
        print("\n[CONNECTED] Dhan WebSocket V2")
        
        # Subscribe to instruments
        if self.subscriptions:
            self.subscribe(self.subscriptions)
    
    def subscribe(self, instruments):
        """Subscribe to instruments"""
        msg = {
            "RequestCode": 15,
            "InstrumentCount": len(instruments),
            "InstrumentList": instruments
        }
        self.ws.send(json.dumps(msg))
        print(f"[SUBSCRIBED] {len(instruments)} instruments")
    
    def start(self, instruments=None):
        """Start WebSocket connection"""
        if instruments is None:
            # Default: NIFTY 50
            instruments = [{"ExchangeSegment": "NSE_FNO", "SecurityId": "35001"}]
        
        self.subscriptions = instruments
        
        ws_url = f"wss://api-feed.dhan.co?version=2&token={ACCESS_TOKEN}&clientId={CLIENT_ID}&authType=2"
        
        print(f"Connecting to Dhan WebSocket...")
        print(f"Token: {ACCESS_TOKEN[:20]}...")
        
        self.ws = websocket.WebSocketApp(
            ws_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        
        # Run in thread so it doesn't block
        wst = threading.Thread(target=self.ws.run_forever)
        wst.daemon = True
        wst.start()
        
        return wst
    
    def stop(self):
        """Stop WebSocket"""
        if self.ws:
            self.ws.close()
        self.connected = False
        print("[STOPPED]")

def test_live_feed():
    """Test WebSocket live feed"""
    print("=" * 60)
    print("LIVE WEBSOCKET FEED")
    print("=" * 60)
    
    feed = DhanLiveFeed()
    
    # Subscribe to NIFTY and BANKNIFTY
    instruments = [
        {"ExchangeSegment": "NSE_FNO", "SecurityId": "35001"},  # NIFTY
        {"ExchangeSegment": "NSE_FNO", "SecurityId": "35002"},  # BANKNIFTY
    ]
    
    thread = feed.start(instruments)
    
    print("\nWaiting for ticks... (Press CTRL+C to stop)")
    print("Note: Ticks only come during market hours (9:15 AM - 3:30 PM)")
    
    try:
        while True:
            time.sleep(1)
            if not feed.connected and feed.tick_count == 0:
                print("No connection yet, retrying...")
                time.sleep(5)
    except KeyboardInterrupt:
        print("\nStopping...")
        feed.stop()
    
    print("\n" + "=" * 60)
    print(f"Total ticks received: {feed.tick_count}")
    print("=" * 60)

if __name__ == '__main__':
    test_live_feed()

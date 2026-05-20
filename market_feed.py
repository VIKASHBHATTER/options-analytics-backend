import asyncio
import websockets
import json
import os

DHAN_CLIENT_ID = os.getenv('DHAN_CLIENT_ID')
DHAN_ACCESS_TOKEN = os.getenv('DHAN_ACCESS_TOKEN')

# Dhan WebSocket URL
WS_URL = f"wss://api-feed.dhan.co?version=2&token={DHAN_ACCESS_TOKEN}&clientId={DHAN_CLIENT_ID}&authType=2"

async def market_feed(instruments):
    """
    instruments = [(exchange, security_id, feed_type), ...]
    feed_type: 1=Ticker, 2=Quote, 3=Full
    """
    async with websockets.connect(WS_URL) as ws:
        # Subscribe
        subscribe_msg = {
            "RequestCode": 15,
            "InstrumentCount": len(instruments),
            "InstrumentList": [
                {
                    "ExchangeSegment": ex,
                    "SecurityId": sid,
                    "FeedType": ft
                } for ex, sid, ft in instruments
            ]
        }
        await ws.send(json.dumps(subscribe_msg))
        
        print(f"✅ Subscribed to {len(instruments)} instruments")
        
        while True:
            try:
                msg = await ws.recv()
                data = json.loads(msg)
                print(f"📊 {data}")
            except Exception as e:
                print(f"❌ Error: {e}")
                break

# Test
if __name__ == '__main__':
    # NIFTY 50 Ticker
    instruments = [(1, "1", 1)]  # Exchange=1 (NSE), SecurityId=1, FeedType=1 (Ticker)
    asyncio.run(market_feed(instruments))

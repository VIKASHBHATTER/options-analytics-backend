import asyncio
import websockets
import json
import os

DHAN_CLIENT_ID = os.getenv('DHAN_CLIENT_ID')
DHAN_ACCESS_TOKEN = os.getenv('DHAN_ACCESS_TOKEN')

# Order Update WebSocket
ORDER_WS_URL = f"wss://orders-update.dhan.co?version=2&token={DHAN_ACCESS_TOKEN}&clientId={DHAN_CLIENT_ID}"

async def order_updates():
    async with websockets.connect(ORDER_WS_URL) as ws:
        print("✅ Connected to Order Updates")
        
        while True:
            try:
                msg = await ws.recv()
                data = json.loads(msg)
                print(f"📢 Order Update: {data}")
            except Exception as e:
                print(f"❌ Error: {e}")
                break

if __name__ == '__main__':
    asyncio.run(order_updates())

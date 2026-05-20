import os
import json
import struct
import asyncio
import sqlite3
import threading
from datetime import datetime
from contextlib import contextmanager
import websocket
from dotenv import load_dotenv

# ─── LOAD ENV ──────────────────────────────────────────────────
load_dotenv()

DHAN_CLIENT_ID = os.getenv('DHAN_CLIENT_ID')
DHAN_ACCESS_TOKEN = os.getenv('DHAN_ACCESS_TOKEN')

# ─── CONFIG ────────────────────────────────────────────────────
WS_URL = f"wss://api-feed.dhan.co?version=2&token={DHAN_ACCESS_TOKEN}&clientId={DHAN_CLIENT_ID}&authType=2"

DB_PATH = os.path.join(os.path.dirname(__file__), 'option_analytics.db')

# Feed Request Codes
FEED_CODES = {
    'TICKER': 15,
    'QUOTE': 16,
    'FULL': 17,
}

# Feed Response Codes
RESPONSE_CODES = {
    2: 'TICKER',
    3: 'DEPTH',
    4: 'QUOTE',
    5: 'OI_DATA',
    6: 'PREV_CLOSE',
    7: 'MARKET_STATUS',
    8: 'FULL',
    50: 'DISCONNECT',
}

# Security IDs for indices
INDEX_SEC_IDS = {
    'NIFTY': {'id': '13', 'segment': 'IDX_I'},
    'BANKNIFTY': {'id': '25', 'segment': 'IDX_I'},
    'FINNIFTY': {'id': '27', 'segment': 'IDX_I'},
    'MIDCPNIFTY': {'id': '442', 'segment': 'IDX_I'},
    'SENSEX': {'id': '51', 'segment': 'IDX_I'},
    'BANKEX': {'id': '69', 'segment': 'IDX_I'},
}

# ─── DATABASE HELPERS ──────────────────────────────────────────

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def save_live_tick(symbol, ltp, ltt=None):
    timestamp = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute("""
            INSERT INTO price_history (timestamp, symbol, ltp, volume, oi, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (timestamp, symbol, ltp, 0, 0, timestamp))

def save_live_quote(symbol, data):
    timestamp = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute("""
            INSERT INTO price_history 
            (timestamp, symbol, ltp, change, volume, oi, vwap, high, low, open_price, close_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp, symbol,
            data.get('ltp'), data.get('change'),
            data.get('volume'), data.get('oi'),
            data.get('atp'), data.get('high'),
            data.get('low'), data.get('open'),
            data.get('close')
        ))

# ─── BINARY PACKET PARSER ──────────────────────────────────────

def parse_header(data):
    if len(data) < 8:
        return None
    feed_code = data[0]
    msg_length = struct.unpack('<H', data[1:3])[0]
    exchange_segment = data[3]
    security_id = struct.unpack('<I', data[4:8])[0]
    return {
        'feed_code': feed_code,
        'feed_type': RESPONSE_CODES.get(feed_code, 'UNKNOWN'),
        'msg_length': msg_length,
        'exchange_segment': exchange_segment,
        'security_id': security_id
    }

def parse_ticker(data):
    if len(data) < 16:
        return None
    ltp = struct.unpack('<f', data[8:12])[0]
    ltt = struct.unpack('<I', data[12:16])[0]
    return {'ltp': round(ltp, 2), 'ltt': ltt}

def parse_quote(data):
    if len(data) < 50:
        return None
    return {
        'ltp': round(struct.unpack('<f', data[8:12])[0], 2),
        'ltq': struct.unpack('<H', data[12:14])[0],
        'ltt': struct.unpack('<I', data[14:18])[0],
        'atp': round(struct.unpack('<f', data[18:22])[0], 2),
        'volume': struct.unpack('<I', data[22:26])[0],
        'total_sell_qty': struct.unpack('<I', data[26:30])[0],
        'total_buy_qty': struct.unpack('<I', data[30:34])[0],
        'open': round(struct.unpack('<f', data[34:38])[0], 2),
        'close': round(struct.unpack('<f', data[38:42])[0], 2),
        'high': round(struct.unpack('<f', data[42:46])[0], 2),
        'low': round(struct.unpack('<f', data[46:50])[0], 2),
    }

def parse_oi_data(data):
    if len(data) < 12:
        return None
    return {'oi': struct.unpack('<I', data[8:12])[0]}

def parse_full_packet(data):
    if len(data) < 62:
        return None
    result = {
        'ltp': round(struct.unpack('<f', data[8:12])[0], 2),
        'ltq': struct.unpack('<H', data[12:14])[0],
        'ltt': struct.unpack('<I', data[14:18])[0],
        'atp': round(struct.unpack('<f', data[18:22])[0], 2),
        'volume': struct.unpack('<I', data[22:26])[0],
        'total_sell_qty': struct.unpack('<I', data[26:30])[0],
        'total_buy_qty': struct.unpack('<I', data[30:34])[0],
        'oi': struct.unpack('<I', data[34:38])[0],
        'oi_high': struct.unpack('<I', data[38:42])[0],
        'oi_low': struct.unpack('<I', data[42:46])[0],
        'open': round(struct.unpack('<f', data[46:50])[0], 2),
        'close': round(struct.unpack('<f', data[50:54])[0], 2),
        'high': round(struct.unpack('<f', data[54:58])[0], 2),
        'low': round(struct.unpack('<f', data[58:62])[0], 2),
    }
    depth = []
    for i in range(5):
        offset = 62 + (i * 20)
        if offset + 20 <= len(data):
            depth.append({
                'bid_qty': struct.unpack('<I', data[offset:offset+4])[0],
                'ask_qty': struct.unpack('<I', data[offset+4:offset+8])[0],
                'bid_orders': struct.unpack('<H', data[offset+8:offset+10])[0],
                'ask_orders': struct.unpack('<H', data[offset+10:offset+12])[0],
                'bid_price': round(struct.unpack('<f', data[offset+12:offset+16])[0], 2),
                'ask_price': round(struct.unpack('<f', data[offset+16:offset+20])[0], 2),
            })
    result['depth'] = depth
    return result

def parse_disconnect(data):
    if len(data) < 10:
        return None
    return {'code': struct.unpack('<H', data[8:10])[0]}

# ─── WEBSOCKET CLIENT ──────────────────────────────────────────

class DhanWebSocketClient:
    def __init__(self, on_tick=None, on_quote=None, on_full=None, on_error=None, on_disconnect=None):
        self.ws = None
        self.subscribed = set()
        self.on_tick = on_tick
        self.on_quote = on_quote
        self.on_full = on_full
        self.on_error = on_error
        self.on_disconnect = on_disconnect
        self.running = False
        self.reconnect_delay = 5
        self.thread = None

    def subscribe_instruments(self, instruments, mode='FULL'):
        if not self.ws or not self.ws.sock or not self.ws.sock.connected:
            print("[WS] Not connected, cannot subscribe")
            return False

        request_code = FEED_CODES.get(mode, 17)

        for i in range(0, len(instruments), 100):
            chunk = instruments[i:i+100]
            msg = {
                "RequestCode": request_code,
                "InstrumentCount": len(chunk),
                "InstrumentList": chunk
            }
            self.ws.send(json.dumps(msg))
            for inst in chunk:
                self.subscribed.add((inst['ExchangeSegment'], inst['SecurityId']))
            print(f"[WS] Subscribed {len(chunk)} instruments in {mode} mode")

        return True

    def subscribe_indices(self, indices=None, mode='FULL'):
        if indices is None:
            indices = list(INDEX_SEC_IDS.keys())

        instruments = []
        for idx in indices:
            if idx in INDEX_SEC_IDS:
                info = INDEX_SEC_IDS[idx]
                instruments.append({
                    "ExchangeSegment": info['segment'],
                    "SecurityId": info['id']
                })

        return self.subscribe_instruments(instruments, mode)

    def unsubscribe_all(self):
        if self.ws and self.ws.sock and self.ws.sock.connected:
            self.ws.send(json.dumps({"RequestCode": 12}))
            self.subscribed.clear()
            print("[WS] Unsubscribed all instruments")

    def _on_message(self, ws, message):
        if isinstance(message, str):
            print(f"[WS] Text message: {message}")
            return

        header = parse_header(message)
        if not header:
            return

        feed_type = header['feed_type']
        sec_id = header['security_id']

        symbol = None
        for name, info in INDEX_SEC_IDS.items():
            if info['id'] == str(sec_id):
                symbol = name
                break

        if feed_type == 'TICKER':
            data = parse_ticker(message)
            if data and symbol:
                data['symbol'] = symbol
                data['sec_id'] = sec_id
                data['timestamp'] = datetime.now().isoformat()
                save_live_tick(symbol, data['ltp'], data.get('ltt'))
                if self.on_tick:
                    self.on_tick(data)

        elif feed_type == 'QUOTE':
            data = parse_quote(message)
            if data and symbol:
                data['symbol'] = symbol
                data['sec_id'] = sec_id
                data['timestamp'] = datetime.now().isoformat()
                save_live_quote(symbol, data)
                if self.on_quote:
                    self.on_quote(data)

        elif feed_type == 'FULL':
            data = parse_full_packet(message)
            if data and symbol:
                data['symbol'] = symbol
                data['sec_id'] = sec_id
                data['timestamp'] = datetime.now().isoformat()
                save_live_quote(symbol, data)
                if self.on_full:
                    self.on_full(data)

        elif feed_type == 'OI_DATA':
            data = parse_oi_data(message)
            if data and symbol:
                print(f"[WS] OI Update {symbol}: {data['oi']}")

        elif feed_type == 'PREV_CLOSE':
            prev_close = struct.unpack('<f', message[8:12])[0] if len(message) >= 12 else None
            if symbol and prev_close:
                print(f"[WS] Prev Close {symbol}: {prev_close}")

        elif feed_type == 'DISCONNECT':
            data = parse_disconnect(message)
            print(f"[WS] Disconnected! Code: {data['code'] if data else 'Unknown'}")
            if self.on_disconnect:
                self.on_disconnect(data)

        elif feed_type == 'MARKET_STATUS':
            print(f"[WS] Market Status update")

    def _on_error(self, ws, error):
        print(f"[WS] Error: {error}")
        if self.on_error:
            self.on_error(error)

    def _on_close(self, ws, close_status_code, close_msg):
        print(f"[WS] Connection closed: {close_status_code} - {close_msg}")
        self.running = False
        if self.on_disconnect:
            self.on_disconnect({'code': close_status_code, 'msg': close_msg})

    def _on_open(self, ws):
        print("[WS] ✅ Connected to Dhan Live Feed!")
        print(f"[WS] Subscribing to indices...")
        self.subscribe_indices(mode='FULL')

    def _run(self):
        self.ws = websocket.WebSocketApp(
            WS_URL,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )
        self.running = True
        self.ws.run_forever(ping_interval=10, ping_timeout=5)

    def start(self):
        if self.running:
            print("[WS] Already running")
            return

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        print("[WS] Starting connection...")

    def stop(self):
        self.running = False
        if self.ws:
            self.ws.close()
        if self.thread:
            self.thread.join(timeout=5)
        print("[WS] Stopped")

    def is_connected(self):
        return self.ws is not None and self.ws.sock and self.ws.sock.connected

# ─── AUTO-RECONNECT WRAPPER ────────────────────────────────────

class DhanWebSocketManager:
    def __init__(self, on_tick=None, on_quote=None, on_full=None):
        self.client = None
        self.on_tick = on_tick
        self.on_quote = on_quote
        self.on_full = on_full
        self.manager_thread = None
        self.stop_flag = threading.Event()

    def _manage(self):
        while not self.stop_flag.is_set():
            if self.client is None or not self.client.is_connected():
                print("[WS-MGR] Connection lost, reconnecting...")
                self.client = DhanWebSocketClient(
                    on_tick=self.on_tick,
                    on_quote=self.on_quote,
                    on_full=self.on_full,
                    on_disconnect=lambda x: print("[WS-MGR] Disconnect detected")
                )
                self.client.start()
                for _ in range(10):
                    if self.client.is_connected():
                        break
                    threading.Event().wait(1)
            threading.Event().wait(5)

    def start(self):
        self.stop_flag.clear()
        self.manager_thread = threading.Thread(target=self._manage, daemon=True)
        self.manager_thread.start()
        print("[WS-MGR] Auto-reconnect manager started")

    def stop(self):
        self.stop_flag.set()
        if self.client:
            self.client.stop()
        if self.manager_thread:
            self.manager_thread.join(timeout=5)
        print("[WS-MGR] Stopped")

# ─── STANDALONE RUN ────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 50)
    print("  DHAN WEBSOCKET LIVE FEED CLIENT")
    print(f"  Client ID: {DHAN_CLIENT_ID}")
    print(f"  Token: {DHAN_ACCESS_TOKEN[:20]}..." if DHAN_ACCESS_TOKEN else "  Token: NOT FOUND!")
    print("=" * 50)

    if not DHAN_ACCESS_TOKEN or DHAN_ACCESS_TOKEN == 'None':
        print("❌ ERROR: DHAN_ACCESS_TOKEN not found!")
        print("   Check your .env file")
        print("   Or set: export DHAN_ACCESS_TOKEN=your_token")
        exit(1)

    def on_tick(data):
        print(f"[TICK] {data['symbol']}: LTP={data['ltp']}")

    def on_full(data):
        print(f"[FULL] {data['symbol']}: LTP={data['ltp']} OI={data.get('oi')} Vol={data.get('volume')}")

    manager = DhanWebSocketManager(on_tick=on_tick, on_full=on_full)
    manager.start()

    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[MAIN] Stopping...")
        manager.stop()

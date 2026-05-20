import sqlite3
import os
import json
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), 'option_analytics.db')

# All indices you want to track
INDICES = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX', 'BANKEX']

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

def init_db():
    with get_db() as conn:
        conn.executescript("""
            -- Option chain snapshots
            CREATE TABLE IF NOT EXISTS option_chain (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                expiry TEXT NOT NULL,
                strike REAL NOT NULL,
                ce_ltp REAL,
                pe_ltp REAL,
                ce_oi INTEGER,
                pe_oi INTEGER,
                ce_volume INTEGER,
                pe_volume INTEGER,
                ce_iv REAL,
                pe_iv REAL,
                ce_change REAL,
                pe_change REAL,
                ce_bid REAL,
                ce_ask REAL,
                pe_bid REAL,
                pe_ask REAL,
                underlying REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_oc_symbol_expiry ON option_chain(symbol, expiry);
            CREATE INDEX IF NOT EXISTS idx_oc_timestamp ON option_chain(timestamp);
            CREATE INDEX IF NOT EXISTS idx_oc_symbol_expiry_ts ON option_chain(symbol, expiry, timestamp);

            -- OI Analysis / PCR calculations
            CREATE TABLE IF NOT EXISTS oi_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                expiry TEXT NOT NULL,
                total_ce_oi INTEGER,
                total_pe_oi INTEGER,
                pcr REAL,
                ce_oi_change INTEGER DEFAULT 0,
                pe_oi_change INTEGER DEFAULT 0,
                max_pain REAL,
                iv_rank REAL,
                ce_pe_ratio REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_oi_symbol_expiry ON oi_analysis(symbol, expiry);
            CREATE INDEX IF NOT EXISTS idx_oi_timestamp ON oi_analysis(timestamp);

            -- Price history (underlying)
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                ltp REAL,
                change REAL,
                change_pct REAL,
                volume INTEGER,
                oi INTEGER,
                vwap REAL,
                high REAL,
                low REAL,
                open_price REAL,
                close_price REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_price_symbol ON price_history(symbol);
            CREATE INDEX IF NOT EXISTS idx_price_timestamp ON price_history(timestamp);

            -- Expiry tracking
            CREATE TABLE IF NOT EXISTS expiry_list (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                expiry TEXT NOT NULL,
                expiry_date TEXT,
                days_to_expiry INTEGER,
                is_current_month INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, expiry)
            );
            CREATE INDEX IF NOT EXISTS idx_expiry_symbol ON expiry_list(symbol);

            -- Scan results (for alerts)
            CREATE TABLE IF NOT EXISTS scan_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                expiry TEXT NOT NULL,
                scan_type TEXT NOT NULL,
                strike REAL,
                message TEXT,
                severity TEXT DEFAULT 'info',
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_scan_symbol ON scan_results(symbol);
            CREATE INDEX IF NOT EXISTS idx_scan_type ON scan_results(scan_type);
        """)
        print("[DB] ✅ Database initialized with all tables!")

# ─── OPTION CHAIN ──────────────────────────────────────────────

def save_option_chain(data_list, symbol, expiry, underlying=None):
    """Save option chain snapshot to DB"""
    timestamp = datetime.now().isoformat()
    with get_db() as conn:
        for item in data_list:
            ce = item.get('CE', {}) or {}
            pe = item.get('PE', {}) or {}
            conn.execute("""
                INSERT INTO option_chain 
                (timestamp, symbol, expiry, strike, ce_ltp, pe_ltp, ce_oi, pe_oi,
                 ce_volume, pe_volume, ce_iv, pe_iv, ce_change, pe_change,
                 ce_bid, ce_ask, pe_bid, pe_ask, underlying)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp, symbol, expiry,
                item.get('strikePrice'),
                ce.get('lastPrice'), pe.get('lastPrice'),
                ce.get('openInterest'), pe.get('openInterest'),
                ce.get('volume'), pe.get('volume'),
                ce.get('impliedVolatility'), pe.get('impliedVolatility'),
                ce.get('change'), pe.get('change'),
                ce.get('bid'), ce.get('ask'),
                pe.get('bid'), pe.get('ask'),
                underlying or item.get('underlyingPrice')
            ))
    return timestamp

def get_latest_option_chain(symbol, expiry, limit=1):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM option_chain 
            WHERE symbol = ? AND expiry = ?
            ORDER BY timestamp DESC, strike ASC
            LIMIT ?
        """, (symbol, expiry, limit)).fetchall()
        return [dict(row) for row in rows]

def get_option_chain_at_time(symbol, expiry, timestamp):
    """Get option chain closest to given timestamp"""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM option_chain 
            WHERE symbol = ? AND expiry = ? AND timestamp <= ?
            ORDER BY timestamp DESC, strike ASC
        """, (symbol, expiry, timestamp)).fetchall()
        return [dict(row) for row in rows]

def get_strikes_range(symbol, expiry, atm_strike, range_count=10):
    """Get strikes around ATM"""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT DISTINCT strike FROM option_chain
            WHERE symbol = ? AND expiry = ?
            ORDER BY ABS(strike - ?) ASC
            LIMIT ?
        """, (symbol, expiry, atm_strike, range_count * 2 + 1)).fetchall()
        return [r['strike'] for r in rows]

# ─── OI ANALYSIS / PCR ─────────────────────────────────────────

def save_oi_analysis(symbol, expiry, total_ce_oi, total_pe_oi, 
                     ce_oi_change=0, pe_oi_change=0, max_pain=None, iv_rank=None):
    timestamp = datetime.now().isoformat()
    pcr = round(total_pe_oi / total_ce_oi, 4) if total_ce_oi else 0
    ce_pe_ratio = round(total_ce_oi / total_pe_oi, 4) if total_pe_oi else 0

    with get_db() as conn:
        conn.execute("""
            INSERT INTO oi_analysis 
            (timestamp, symbol, expiry, total_ce_oi, total_pe_oi, pcr,
             ce_oi_change, pe_oi_change, max_pain, iv_rank, ce_pe_ratio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, symbol, expiry, total_ce_oi, total_pe_oi, pcr,
              ce_oi_change, pe_oi_change, max_pain, iv_rank, ce_pe_ratio))
    return pcr

def get_oi_trend(symbol, expiry, minutes=30):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT timestamp, strike, ce_oi, pe_oi, ce_volume, pe_volume,
                   ce_ltp, pe_ltp, ce_iv, pe_iv
            FROM option_chain
            WHERE symbol = ? AND expiry = ? 
            AND datetime(timestamp) > datetime('now', ?)
            ORDER BY timestamp DESC, strike ASC
        """, (symbol, expiry, f'-{minutes} minutes')).fetchall()
        return [dict(row) for row in rows]

def get_pcr_history(symbol, expiry, limit=50):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT timestamp, pcr, total_ce_oi, total_pe_oi, 
                   ce_oi_change, pe_oi_change, max_pain
            FROM oi_analysis
            WHERE symbol = ? AND expiry = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (symbol, expiry, limit)).fetchall()
        return [dict(row) for row in rows]

def get_latest_pcr(symbol, expiry):
    with get_db() as conn:
        row = conn.execute("""
            SELECT * FROM oi_analysis
            WHERE symbol = ? AND expiry = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (symbol, expiry)).fetchone()
        return dict(row) if row else None

# ─── PRICE HISTORY ───────────────────────────────────────────

def save_price(symbol, ltp, change=None, change_pct=None, volume=None,
               oi=None, vwap=None, high=None, low=None, open_price=None, close_price=None):
    timestamp = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute("""
            INSERT INTO price_history 
            (timestamp, symbol, ltp, change, change_pct, volume, oi, vwap, high, low, open_price, close_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, symbol, ltp, change, change_pct, volume, oi, vwap, high, low, open_price, close_price))

def get_price_history(symbol, minutes=60):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM price_history
            WHERE symbol = ? AND datetime(timestamp) > datetime('now', ?)
            ORDER BY timestamp ASC
        """, (symbol, f'-{minutes} minutes')).fetchall()
        return [dict(row) for row in rows]

# ─── EXPIRY LIST ──────────────────────────────────────────────

def save_expiry_list(symbol, expiries):
    from datetime import datetime as dt
    today = dt.now().date()

    with get_db() as conn:
        for exp in expiries:
            try:
                exp_date = dt.strptime(exp, '%Y-%m-%d').date()
                days_to_exp = (exp_date - today).days
                is_current = 1 if days_to_exp <= 30 else 0
            except:
                exp_date = None
                days_to_exp = None
                is_current = 0

            conn.execute("""
                INSERT INTO expiry_list (symbol, expiry, expiry_date, days_to_expiry, is_current_month)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(symbol, expiry) DO UPDATE SET
                    days_to_expiry = excluded.days_to_expiry,
                    is_current_month = excluded.is_current_month
            """, (symbol, exp, str(exp_date) if exp_date else None, days_to_exp, is_current))

def get_expiries(symbol, current_month_only=False):
    with get_db() as conn:
        if current_month_only:
            rows = conn.execute("""
                SELECT expiry, days_to_expiry FROM expiry_list
                WHERE symbol = ? AND is_current_month = 1
                ORDER BY expiry_date ASC
            """, (symbol,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT expiry, days_to_expiry FROM expiry_list
                WHERE symbol = ?
                ORDER BY expiry_date ASC
            """, (symbol,)).fetchall()
        return [dict(row) for row in rows]

# ─── SCAN RESULTS ─────────────────────────────────────────────

def save_scan(symbol, expiry, scan_type, message, severity='info', strike=None, metadata=None):
    timestamp = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute("""
            INSERT INTO scan_results (timestamp, symbol, expiry, scan_type, strike, message, severity, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, symbol, expiry, scan_type, strike, message, severity, 
              json.dumps(metadata) if metadata else None))

def get_scans(symbol=None, scan_type=None, limit=100):
    with get_db() as conn:
        query = "SELECT * FROM scan_results WHERE 1=1"
        params = []
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if scan_type:
            query += " AND scan_type = ?"
            params.append(scan_type)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

# ─── UTILITY ─────────────────────────────────────────────────

def get_db_stats():
    with get_db() as conn:
        stats = {}
        for table in ['option_chain', 'oi_analysis', 'price_history', 'expiry_list', 'scan_results']:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            stats[table] = count

        # Last update per symbol
        symbols = conn.execute("""
            SELECT symbol, MAX(timestamp) as last_update, COUNT(*) as records
            FROM option_chain GROUP BY symbol
        """).fetchall()
        stats['symbols'] = [dict(row) for row in symbols]
        return stats

def cleanup_old_data(days=7):
    """Delete data older than N days"""
    with get_db() as conn:
        for table in ['option_chain', 'oi_analysis', 'price_history']:
            conn.execute(f"""
                DELETE FROM {table} 
                WHERE datetime(timestamp) < datetime('now', '-{days} days')
            """)
        print(f"[DB] Cleaned up data older than {days} days")

if __name__ == '__main__':
    init_db()
    print("[DB] All tables created successfully!")
    print("[DB] Tracking indices:", INDICES)

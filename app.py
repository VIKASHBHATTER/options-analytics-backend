import logging
import json
import os
import time
import webbrowser
import threading
from queue import Queue
from datetime import datetime
from functools import wraps
from typing import Dict, Any, Optional, List, Tuple

from flask import Flask, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from dhanhq import DhanClient
import pyotp
from config import get_config

# Initialize Flask app
app = Flask(__name__)
config = get_config()
app.config.from_object(config)
app.secret_key = config.SECRET_KEY
CORS(app)

# Setup logging
logging.basicConfig(
    filename=config.LOG_FILE,
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Initialize DhanClient
dhan_client = None

# WebSocket data storage
ws_data = {
    'market_feed': Queue(maxsize=1000),
    'order_updates': Queue(maxsize=1000),
    'full_depth': Queue(maxsize=1000)
}

# WebSocket threads
ws_threads = {
    'market_feed': None,
    'order_updates': None,
    'full_depth': None
}

# WebSocket flags
ws_running = {
    'market_feed': False,
    'order_updates': False,
    'full_depth': False
}

def get_dhan_client():
    """Get or initialize DhanClient"""
    global dhan_client
    if not dhan_client:
        dhan_client = DhanClient(client_id=config.DHAN_CLIENT_ID)
        if config.DHAN_ACCESS_TOKEN:
            dhan_client.set_access_token(config.DHAN_ACCESS_TOKEN)
    return dhan_client

def error_handler(f):
    """Decorator for consistent error handling"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {f.__name__}: {str(e)}", exc_info=True)
            return jsonify({
                'success': False,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }), 500
    return decorated_function

# ==================== AUTHENTICATION ENDPOINTS ====================

@app.route('/auth/health', methods=['GET'])
@error_handler
def auth_health():
    """Health check endpoint"""
    logger.info("Health check called")
    return jsonify({
        'success': True,
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'client_id': config.DHAN_CLIENT_ID
    })

@app.route('/auth/status', methods=['GET'])
@error_handler
def auth_status():
    """Get authentication status"""
    logger.info("Status check called")
    client = get_dhan_client()
    try:
        has_token = bool(config.DHAN_ACCESS_TOKEN)
        return jsonify({
            'success': True,
            'authenticated': has_token,
            'client_id': config.DHAN_CLIENT_ID,
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Status check error: {str(e)}")
        return jsonify({
            'success': False,
            'authenticated': False,
            'error': str(e)
        }), 401

@app.route('/auth/dhan-context', methods=['POST'])
@error_handler
def dhan_context():
    """Initialize DhanContext with access token"""
    logger.info("DhanContext initialization called")
    data = request.get_json() or {}
    access_token = data.get('access_token')
    
    if not access_token:
        return jsonify({
            'success': False,
            'error': 'access_token is required'
        }), 400
    
    try:
        client = get_dhan_client()
        client.set_access_token(access_token)
        logger.info("DhanContext initialized successfully")
        return jsonify({
            'success': True,
            'message': 'DhanContext initialized',
            'client_id': config.DHAN_CLIENT_ID
        })
    except Exception as e:
        logger.error(f"DhanContext error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/auth/oauth/initiate', methods=['POST'])
@error_handler
def oauth_initiate():
    """OAuth login endpoint"""
    logger.info("OAuth login initiated")
    oauth_url = f"https://api.dhan.co/oauth/authorize?client_id={config.DHAN_OAUTH_CLIENT_ID}&redirect_uri={config.DHAN_OAUTH_REDIRECT_URI}&response_type=code"
    logger.info(f"OAuth URL: {oauth_url}")
    return jsonify({
        'success': True,
        'oauth_url': oauth_url,
        'message': 'Redirect to this URL to initiate OAuth'
    })

@app.route('/auth/oauth/token', methods=['POST'])
@error_handler
def oauth_token():
    """OAuth token exchange endpoint"""
    logger.info("OAuth token exchange called")
    data = request.get_json() or {}
    code = data.get('code')
    
    if not code:
        return jsonify({
            'success': False,
            'error': 'Authorization code is required'
        }), 400
    
    try:
        import requests
        response = requests.post(
            'https://api.dhan.co/oauth/token',
            data={
                'grant_type': 'authorization_code',
                'code': code,
                'client_id': config.DHAN_OAUTH_CLIENT_ID,
                'client_secret': config.DHAN_OAUTH_CLIENT_SECRET
            }
        )
        
        if response.status_code == 200:
            token_data = response.json()
            session['access_token'] = token_data.get('access_token')
            logger.info("OAuth token exchange successful")
            return jsonify({
                'success': True,
                'message': 'OAuth authentication successful',
                'access_token': token_data.get('access_token'),
                'refresh_token': token_data.get('refresh_token')
            })
        else:
            logger.error(f"OAuth token exchange failed: {response.text}")
            return jsonify({
                'success': False,
                'error': 'Token exchange failed'
            }), 400
    except Exception as e:
        logger.error(f"OAuth token error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/auth/pin-totp', methods=['POST'])
@error_handler
def pin_totp_auth():
    """Authentication with PIN and TOTP"""
    logger.info("PIN+TOTP authentication called")
    data = request.get_json() or {}
    pin = data.get('pin')
    
    if not pin:
        return jsonify({
            'success': False,
            'error': 'PIN is required'
        }), 400
    
    try:
        totp = None
        if config.DHAN_TOTP_SECRET:
            totp_generator = pyotp.TOTP(config.DHAN_TOTP_SECRET)
            totp = totp_generator.now()
            logger.info("TOTP generated successfully")
        
        client = get_dhan_client()
        session['pin'] = pin
        session['totp'] = totp
        
        logger.info("PIN+TOTP credentials stored")
        return jsonify({
            'success': True,
            'message': 'PIN+TOTP authentication credentials stored',
            'has_totp': bool(totp)
        })
    except Exception as e:
        logger.error(f"PIN+TOTP auth error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/auth/renew', methods=['POST'])
@error_handler
def renew_token():
    """Renew access token"""
    logger.info("Token renewal called")
    data = request.get_json() or {}
    refresh_token = data.get('refresh_token')
    
    if not refresh_token:
        return jsonify({
            'success': False,
            'error': 'refresh_token is required'
        }), 400
    
    try:
        import requests
        response = requests.post(
            'https://api.dhan.co/oauth/token',
            data={
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'client_id': config.DHAN_OAUTH_CLIENT_ID,
                'client_secret': config.DHAN_OAUTH_CLIENT_SECRET
            }
        )
        
        if response.status_code == 200:
            token_data = response.json()
            logger.info("Token renewed successfully")
            return jsonify({
                'success': True,
                'access_token': token_data.get('access_token'),
                'refresh_token': token_data.get('refresh_token'),
                'expires_in': token_data.get('expires_in')
            })
        else:
            logger.error(f"Token renewal failed: {response.text}")
            return jsonify({
                'success': False,
                'error': 'Token renewal failed'
            }), 400
    except Exception as e:
        logger.error(f"Token renewal error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/auth/profile', methods=['GET'])
@error_handler
def user_profile():
    """Get user profile"""
    logger.info("User profile endpoint called")
    client = get_dhan_client()
    
    try:
        profile = {
            'client_id': config.DHAN_CLIENT_ID,
            'authenticated': bool(config.DHAN_ACCESS_TOKEN),
            'timestamp': datetime.utcnow().isoformat()
        }
        logger.info("User profile retrieved")
        return jsonify({
            'success': True,
            'profile': profile
        })
    except Exception as e:
        logger.error(f"User profile error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ==================== ORDERS ENDPOINTS ====================

@app.route('/order/place', methods=['POST'])
@error_handler
def place_order():
    """Place a new order"""
    logger.info("Place order called")
    data = request.get_json() or {}
    client = get_dhan_client()
    
    try:
        required_fields = ['security_id', 'exchange_segment', 'transaction_type', 'quantity', 'price']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'{field} is required'
                }), 400
        
        response = client.place_order(
            security_id=data['security_id'],
            exchange_segment=data['exchange_segment'],
            transaction_type=data['transaction_type'],
            quantity=data['quantity'],
            price=data['price'],
            order_type=data.get('order_type', 'REGULAR'),
            validity=data.get('validity', 'DAY'),
            disclosed_quantity=data.get('disclosed_quantity', 0),
            algo_order=data.get('algo_order', False),
            notes=data.get('notes', '')
        )
        
        logger.info(f"Order placed successfully: {response}")
        return jsonify({
            'success': True,
            'order_id': response.get('order_id'),
            'data': response
        })
    except Exception as e:
        logger.error(f"Place order error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/order/list', methods=['GET'])
@error_handler
def list_orders():
    """Get list of all orders"""
    logger.info("List orders called")
    client = get_dhan_client()
    
    try:
        response = client.get_order_list()
        logger.info(f"Orders list retrieved: {len(response) if isinstance(response, list) else 1}")
        return jsonify({
            'success': True,
            'orders': response if isinstance(response, list) else [response],
            'count': len(response) if isinstance(response, list) else 1
        })
    except Exception as e:
        logger.error(f"List orders error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'orders': []
        }), 400

@app.route('/order/<order_id>', methods=['GET'])
@error_handler
def get_order_by_id(order_id):
    """Get order by order ID"""
    logger.info(f"Get order by ID called: {order_id}")
    client = get_dhan_client()
    
    try:
        response = client.get_order_by_id(order_id=order_id)
        logger.info(f"Order retrieved: {order_id}")
        return jsonify({
            'success': True,
            'order': response
        })
    except Exception as e:
        logger.error(f"Get order by ID error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/order/correlation/<correlation_id>', methods=['GET'])
@error_handler
def get_order_by_correlation_id(correlation_id):
    """Get order by correlation ID"""
    logger.info(f"Get order by correlation ID called: {correlation_id}")
    client = get_dhan_client()
    
    try:
        response = client.get_order_by_correlationID(order_correlation_id=correlation_id)
        logger.info(f"Order retrieved by correlation ID: {correlation_id}")
        return jsonify({
            'success': True,
            'order': response
        })
    except Exception as e:
        logger.error(f"Get order by correlation ID error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/order/modify/<order_id>', methods=['PUT'])
@error_handler
def modify_order(order_id):
    """Modify an existing order"""
    logger.info(f"Modify order called: {order_id}")
    data = request.get_json() or {}
    client = get_dhan_client()
    
    try:
        response = client.modify_order(
            order_id=order_id,
            quantity=data.get('quantity'),
            price=data.get('price'),
            disclosed_quantity=data.get('disclosed_quantity'),
            validity=data.get('validity', 'DAY')
        )
        
        logger.info(f"Order modified successfully: {response}")
        return jsonify({
            'success': True,
            'order_id': response.get('order_id'),
            'data': response
        })
    except Exception as e:
        logger.error(f"Modify order error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/order/cancel/<order_id>', methods=['DELETE'])
@error_handler
def cancel_order(order_id):
    """Cancel an order"""
    logger.info(f"Cancel order called: {order_id}")
    client = get_dhan_client()
    
    try:
        response = client.cancel_order(order_id=order_id)
        
        logger.info(f"Order cancelled successfully: {response}")
        return jsonify({
            'success': True,
            'order_id': response.get('order_id'),
            'data': response
        })
    except Exception as e:
        logger.error(f"Cancel order error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

# ==================== PORTFOLIO ENDPOINTS ====================

@app.route('/portfolio/funds', methods=['GET'])
@error_handler
def get_funds():
    """Get fund limits"""
    logger.info("Get funds called")
    client = get_dhan_client()
    
    try:
        response = client.get_fund_limits()
        logger.info("Funds retrieved successfully")
        return jsonify({
            'success': True,
            'funds': response
        })
    except Exception as e:
        logger.error(f"Get funds error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/portfolio/positions', methods=['GET'])
@error_handler
def get_positions():
    """Get positions"""
    logger.info("Get positions called")
    client = get_dhan_client()
    
    try:
        response = client.get_positions()
        logger.info(f"Positions retrieved: {len(response) if isinstance(response, list) else 1}")
        return jsonify({
            'success': True,
            'positions': response if isinstance(response, list) else [response],
            'count': len(response) if isinstance(response, list) else 1
        })
    except Exception as e:
        logger.error(f"Get positions error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'positions': []
        }), 400

@app.route('/portfolio/holdings', methods=['GET'])
@error_handler
def get_holdings():
    """Get holdings"""
    logger.info("Get holdings called")
    client = get_dhan_client()
    
    try:
        response = client.get_holdings()
        logger.info(f"Holdings retrieved: {len(response) if isinstance(response, list) else 1}")
        return jsonify({
            'success': True,
            'holdings': response if isinstance(response, list) else [response],
            'count': len(response) if isinstance(response, list) else 1
        })
    except Exception as e:
        logger.error(f"Get holdings error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'holdings': []
        }), 400

@app.route('/portfolio/trades', methods=['GET'])
@error_handler
def get_trade_book():
    """Get trade book"""
    logger.info("Get trade book called")
    client = get_dhan_client()
    
    try:
        response = client.get_trade_book()
        logger.info(f"Trade book retrieved: {len(response) if isinstance(response, list) else 1}")
        return jsonify({
            'success': True,
            'trades': response if isinstance(response, list) else [response],
            'count': len(response) if isinstance(response, list) else 1
        })
    except Exception as e:
        logger.error(f"Get trade book error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'trades': []
        }), 400

@app.route('/portfolio/trade-history', methods=['GET'])
@error_handler
def get_trade_history():
    """Get trade history"""
    logger.info("Get trade history called")
    client = get_dhan_client()
    
    try:
        response = client.get_trade_history()
        logger.info(f"Trade history retrieved: {len(response) if isinstance(response, list) else 1}")
        return jsonify({
            'success': True,
            'history': response if isinstance(response, list) else [response],
            'count': len(response) if isinstance(response, list) else 1
        })
    except Exception as e:
        logger.error(f"Get trade history error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'history': []
        }), 400

# ==================== MARKET DATA ENDPOINTS ====================

@app.route('/data/quote/<symbol>', methods=['GET'])
@error_handler
def get_quote(symbol):
    """Get OHLC data"""
    logger.info(f"Get quote called: {symbol}")
    client = get_dhan_client()
    
    try:
        security_id = request.args.get('security_id')
        exchange_segment = request.args.get('exchange_segment', 'NSE_EQ')
        
        if not security_id:
            return jsonify({
                'success': False,
                'error': 'security_id is required'
            }), 400
        
        response = client.ohlc_data(security_id=security_id, exchange_segment=exchange_segment)
        logger.info(f"OHLC data retrieved for security {security_id}")
        return jsonify({
            'success': True,
            'quote': response
        })
    except Exception as e:
        logger.error(f"Get quote error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/data/historical/<symbol>', methods=['GET'])
@error_handler
def get_historical_data(symbol):
    """Get historical daily data"""
    logger.info(f"Get historical data called: {symbol}")
    client = get_dhan_client()
    
    try:
        security_id = request.args.get('security_id')
        exchange_segment = request.args.get('exchange_segment', 'NSE_EQ')
        
        if not security_id:
            return jsonify({
                'success': False,
                'error': 'security_id is required'
            }), 400
        
        response = client.historical_daily_data(
            security_id=security_id,
            exchange_segment=exchange_segment
        )
        
        logger.info(f"Historical data retrieved for security {security_id}")
        return jsonify({
            'success': True,
            'data': response if isinstance(response, list) else [response],
            'count': len(response) if isinstance(response, list) else 1
        })
    except Exception as e:
        logger.error(f"Get historical data error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/data/intraday/<symbol>', methods=['GET'])
@error_handler
def get_intraday_data(symbol):
    """Get intraday minute data"""
    logger.info(f"Get intraday data called: {symbol}")
    client = get_dhan_client()
    
    try:
        security_id = request.args.get('security_id')
        exchange_segment = request.args.get('exchange_segment', 'NSE_EQ')
        
        if not security_id:
            return jsonify({
                'success': False,
                'error': 'security_id is required'
            }), 400
        
        response = client.intraday_minute_data(
            security_id=security_id,
            exchange_segment=exchange_segment
        )
        
        logger.info(f"Intraday data retrieved for security {security_id}")
        return jsonify({
            'success': True,
            'data': response if isinstance(response, list) else [response],
            'count': len(response) if isinstance(response, list) else 1
        })
    except Exception as e:
        logger.error(f"Get intraday data error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/data/option-chain/<symbol>', methods=['GET'])
@error_handler
def get_option_chain(symbol):
    """Get option chain data with Greeks"""
    logger.info(f"Get option chain called: {symbol}")
    client = get_dhan_client()
    
    try:
        security_id = request.args.get('security_id')
        expiry_date = request.args.get('expiry_date')
        strike_price = request.args.get('strike_price')
        option_type = request.args.get('option_type')
        
        if not security_id:
            return jsonify({
                'success': False,
                'error': 'security_id is required'
            }), 400
        
        response = client.option_chain(
            security_id=security_id,
            expiry_date=expiry_date,
            strike_price=strike_price,
            option_type=option_type
        )
        
        logger.info(f"Option chain retrieved for security {security_id}")
        return jsonify({
            'success': True,
            'option_chain': response if isinstance(response, list) else [response],
            'count': len(response) if isinstance(response, list) else 1
        })
    except Exception as e:
        logger.error(f"Get option chain error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/data/expired-options', methods=['GET'])
@error_handler
def get_expired_options():
    """Get expired options data"""
    logger.info("Get expired options called")
    client = get_dhan_client()
    
    try:
        response = client.expired_options_data()
        logger.info(f"Expired options retrieved: {len(response) if isinstance(response, list) else 1}")
        return jsonify({
            'success': True,
            'expired_options': response if isinstance(response, list) else [response],
            'count': len(response) if isinstance(response, list) else 1
        })
    except Exception as e:
        logger.error(f"Get expired options error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'expired_options': []
        }), 400

@app.route('/data/expiry-list/<symbol>', methods=['GET'])
@error_handler
def get_expiry_list(symbol):
    """Get expiry list"""
    logger.info(f"Get expiry list called: {symbol}")
    client = get_dhan_client()
    
    try:
        security_id = request.args.get('security_id')
        
        if not security_id:
            return jsonify({
                'success': False,
                'error': 'security_id is required'
            }), 400
        
        response = client.expiry_list(security_id=security_id)
        logger.info(f"Expiry list retrieved: {len(response) if isinstance(response, list) else 1}")
        return jsonify({
            'success': True,
            'expiry_list': response if isinstance(response, list) else [response],
            'count': len(response) if isinstance(response, list) else 1
        })
    except Exception as e:
        logger.error(f"Get expiry list error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'expiry_list': []
        }), 400

@app.route('/data/security-list', methods=['GET'])
@error_handler
def get_security_list():
    """Get security list"""
    logger.info("Get security list called")
    client = get_dhan_client()
    
    try:
        response = client.fetch_security_list()
        logger.info(f"Security list retrieved: {len(response) if isinstance(response, list) else 1}")
        return jsonify({
            'success': True,
            'securities': response if isinstance(response, list) else [response],
            'count': len(response) if isinstance(response, list) else 1
        })
    except Exception as e:
        logger.error(f"Get security list error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'securities': []
        }), 400

# ==================== FOREVER ORDERS (GTT) ENDPOINTS ====================

@app.route('/forever/place', methods=['POST'])
@error_handler
def place_forever_order():
    """Place a forever order (GTT)"""
    logger.info("Place forever order called")
    data = request.get_json() or {}
    client = get_dhan_client()
    
    try:
        required_fields = ['security_id', 'exchange_segment', 'transaction_type', 'quantity', 'price']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'{field} is required'
                }), 400
        
        response = client.place_forever(
            security_id=data['security_id'],
            exchange_segment=data['exchange_segment'],
            transaction_type=data['transaction_type'],
            quantity=data['quantity'],
            price=data['price'],
            order_type=data.get('order_type', 'REGULAR')
        )
        
        logger.info(f"Forever order placed successfully: {response}")
        return jsonify({
            'success': True,
            'order_id': response.get('order_id'),
            'data': response
        })
    except Exception as e:
        logger.error(f"Place forever order error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/forever/modify/<order_id>', methods=['PUT'])
@error_handler
def modify_forever_order(order_id):
    """Modify a forever order"""
    logger.info(f"Modify forever order called: {order_id}")
    data = request.get_json() or {}
    client = get_dhan_client()
    
    try:
        response = client.modify_forever(
            order_id=order_id,
            quantity=data.get('quantity'),
            price=data.get('price')
        )
        
        logger.info(f"Forever order modified successfully: {response}")
        return jsonify({
            'success': True,
            'order_id': response.get('order_id'),
            'data': response
        })
    except Exception as e:
        logger.error(f"Modify forever order error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/forever/cancel/<order_id>', methods=['DELETE'])
@error_handler
def cancel_forever_order(order_id):
    """Cancel a forever order"""
    logger.info(f"Cancel forever order called: {order_id}")
    client = get_dhan_client()
    
    try:
        response = client.cancel_forever(order_id=order_id)
        
        logger.info(f"Forever order cancelled successfully: {response}")
        return jsonify({
            'success': True,
            'order_id': response.get('order_id'),
            'data': response
        })
    except Exception as e:
        logger.error(f"Cancel forever order error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

# ==================== WEBSOCKET LIVE FEED ENDPOINTS ====================

def market_feed_worker():
    """Background worker for market feed"""
    logger.info("Market feed worker started")
    try:
        from dhanhq import MarketFeed
        client = get_dhan_client()
        market_feed = MarketFeed(client)
        
        while ws_running['market_feed']:
            try:
                data = market_feed.get_data()
                if data:
                    ws_data['market_feed'].put(data)
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"Market feed worker error: {str(e)}")
                time.sleep(1)
    except Exception as e:
        logger.error(f"Market feed initialization error: {str(e)}")

def order_update_worker():
    """Background worker for order updates"""
    logger.info("Order update worker started")
    try:
        from dhanhq import OrderUpdate
        client = get_dhan_client()
        order_update = OrderUpdate(client)
        
        while ws_running['order_updates']:
            try:
                data = order_update.get_data()
                if data:
                    ws_data['order_updates'].put(data)
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"Order update worker error: {str(e)}")
                time.sleep(1)
    except Exception as e:
        logger.error(f"Order update initialization error: {str(e)}")

def full_depth_worker(level=20):
    """Background worker for full depth"""
    logger.info(f"Full depth worker started (level: {level})")
    try:
        from dhanhq import FullDepth
        client = get_dhan_client()
        full_depth = FullDepth(client, level=level)
        
        while ws_running['full_depth']:
            try:
                data = full_depth.get_data()
                if data:
                    ws_data['full_depth'].put(data)
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"Full depth worker error: {str(e)}")
                time.sleep(1)
    except Exception as e:
        logger.error(f"Full depth initialization error: {str(e)}")

@app.route('/ws/market-feed/start', methods=['POST'])
@error_handler
def start_market_feed():
    """Start market feed WebSocket"""
    logger.info("Start market feed called")
    try:
        if not ws_running['market_feed']:
            ws_running['market_feed'] = True
            ws_threads['market_feed'] = threading.Thread(target=market_feed_worker, daemon=True)
            ws_threads['market_feed'].start()
            logger.info("Market feed started")
        
        return jsonify({
            'success': True,
            'message': 'Market feed started'
        })
    except Exception as e:
        logger.error(f"Start market feed error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/ws/market-feed/data', methods=['GET'])
@error_handler
def get_market_feed_data():
    """Get market feed data"""
    logger.info("Get market feed data called")
    try:
        data_list = []
        while not ws_data['market_feed'].empty():
            data_list.append(ws_data['market_feed'].get())
        
        return jsonify({
            'success': True,
            'data': data_list,
            'count': len(data_list)
        })
    except Exception as e:
        logger.error(f"Get market feed data error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/ws/market-feed/stop', methods=['POST'])
@error_handler
def stop_market_feed():
    """Stop market feed WebSocket"""
    logger.info("Stop market feed called")
    try:
        ws_running['market_feed'] = False
        if ws_threads['market_feed']:
            ws_threads['market_feed'].join(timeout=5)
        logger.info("Market feed stopped")
        
        return jsonify({
            'success': True,
            'message': 'Market feed stopped'
        })
    except Exception as e:
        logger.error(f"Stop market feed error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/ws/order-updates/start', methods=['POST'])
@error_handler
def start_order_updates():
    """Start order updates WebSocket"""
    logger.info("Start order updates called")
    try:
        if not ws_running['order_updates']:
            ws_running['order_updates'] = True
            ws_threads['order_updates'] = threading.Thread(target=order_update_worker, daemon=True)
            ws_threads['order_updates'].start()
            logger.info("Order updates started")
        
        return jsonify({
            'success': True,
            'message': 'Order updates started'
        })
    except Exception as e:
        logger.error(f"Start order updates error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/ws/order-updates/data', methods=['GET'])
@error_handler
def get_order_updates_data():
    """Get order updates data"""
    logger.info("Get order updates data called")
    try:
        data_list = []
        while not ws_data['order_updates'].empty():
            data_list.append(ws_data['order_updates'].get())
        
        return jsonify({
            'success': True,
            'data': data_list,
            'count': len(data_list)
        })
    except Exception as e:
        logger.error(f"Get order updates data error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/ws/full-depth/start', methods=['POST'])
@error_handler
def start_full_depth():
    """Start full depth WebSocket"""
    logger.info("Start full depth called")
    data = request.get_json() or {}
    level = data.get('level', 20)
    
    try:
        if not ws_running['full_depth']:
            ws_running['full_depth'] = True
            ws_threads['full_depth'] = threading.Thread(target=full_depth_worker, args=(level,), daemon=True)
            ws_threads['full_depth'].start()
            logger.info(f"Full depth started (level: {level})")
        
        return jsonify({
            'success': True,
            'message': f'Full depth started (level: {level})'
        })
    except Exception as e:
        logger.error(f"Start full depth error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/ws/full-depth/data', methods=['GET'])
@error_handler
def get_full_depth_data():
    """Get full depth data"""
    logger.info("Get full depth data called")
    try:
        data_list = []
        while not ws_data['full_depth'].empty():
            data_list.append(ws_data['full_depth'].get())
        
        return jsonify({
            'success': True,
            'data': data_list,
            'count': len(data_list)
        })
    except Exception as e:
        logger.error(f"Get full depth data error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

# ==================== eDIS / CDSL ENDPOINTS ====================

@app.route('/edis/tpin', methods=['POST'])
@error_handler
def generate_tpin():
    """Generate eDIS TPIN"""
    logger.info("Generate eDIS TPIN called")
    data = request.get_json() or {}
    client = get_dhan_client()
    
    try:
        response = client.generate_tpin(
            isin=data.get('isin'),
            quantity=data.get('quantity')
        )
        
        logger.info("TPIN generated successfully")
        return jsonify({
            'success': True,
            'tpin': response.get('tpin'),
            'data': response
        })
    except Exception as e:
        logger.error(f"Generate TPIN error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/edis/browser', methods=['POST'])
@error_handler
def open_browser_for_tpin():
    """Open browser for eDIS TPIN"""
    logger.info("Open browser for TPIN called")
    data = request.get_json() or {}
    client = get_dhan_client()
    
    try:
        tpin_url = data.get('tpin_url')
        if not tpin_url:
            return jsonify({
                'success': False,
                'error': 'tpin_url is required'
            }), 400
        
        client.open_browser_for_tpin(tpin_url=tpin_url)
        logger.info("Browser opened for TPIN")
        
        return jsonify({
            'success': True,
            'message': 'Browser opened for TPIN verification'
        })
    except Exception as e:
        logger.error(f"Open browser for TPIN error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/edis/inquiry', methods=['GET'])
@error_handler
def edis_inquiry():
    """eDIS inquiry"""
    logger.info("eDIS inquiry called")
    client = get_dhan_client()
    
    try:
        isin = request.args.get('isin')
        if not isin:
            return jsonify({
                'success': False,
                'error': 'isin is required'
            }), 400
        
        response = client.edis_inquiry(isin=isin)
        
        logger.info("eDIS inquiry retrieved")
        return jsonify({
            'success': True,
            'inquiry': response
        })
    except Exception as e:
        logger.error(f"eDIS inquiry error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

# ==================== IP MANAGEMENT ENDPOINTS ====================

@app.route('/admin/set-ip', methods=['POST'])
@error_handler
def set_ip():
    """Set user IP"""
    logger.info("Set IP called")
    data = request.get_json() or {}
    client = get_dhan_client()
    
    try:
        if 'ip_address' not in data:
            return jsonify({
                'success': False,
                'error': 'ip_address is required'
            }), 400
        
        from dhanhq import DhanLogin
        login = DhanLogin()
        response = login.set_ip(ip_address=data['ip_address'])
        
        logger.info(f"IP set successfully: {data['ip_address']}")
        return jsonify({
            'success': True,
            'ip_address': data['ip_address'],
            'data': response
        })
    except Exception as e:
        logger.error(f"Set IP error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/admin/modify-ip', methods=['PUT'])
@error_handler
def modify_ip():
    """Modify user IP"""
    logger.info("Modify IP called")
    data = request.get_json() or {}
    client = get_dhan_client()
    
    try:
        if 'old_ip' not in data or 'new_ip' not in data:
            return jsonify({
                'success': False,
                'error': 'old_ip and new_ip are required'
            }), 400
        
        from dhanhq import DhanLogin
        login = DhanLogin()
        response = login.modify_ip(
            old_ip=data['old_ip'],
            new_ip=data['new_ip']
        )
        
        logger.info(f"IP modified successfully: {data['old_ip']} -> {data['new_ip']}")
        return jsonify({
            'success': True,
            'old_ip': data['old_ip'],
            'new_ip': data['new_ip'],
            'data': response
        })
    except Exception as e:
        logger.error(f"Modify IP error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/admin/get-ip', methods=['GET'])
@error_handler
def get_ip():
    """Get user IP"""
    logger.info("Get IP called")
    client = get_dhan_client()
    
    try:
        from dhanhq import DhanLogin
        login = DhanLogin()
        response = login.get_ip()
        
        logger.info("IP retrieved successfully")
        return jsonify({
            'success': True,
            'ip_address': response.get('ip_address') if isinstance(response, dict) else response,
            'data': response
        })
    except Exception as e:
        logger.error(f"Get IP error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

# ==================== UTILITY ENDPOINTS ====================

@app.route('/health', methods=['GET'])
@error_handler
def health():
    """Health check"""
    logger.info("Health check called")
    return jsonify({
        'success': True,
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'server': 'DhanHQ Analytics Backend',
        'version': '1.0.0'
    })

@app.route('/status', methods=['GET'])
@error_handler
def status():
    """Status endpoint"""
    logger.info("Status endpoint called")
    try:
        client = get_dhan_client()
        return jsonify({
            'success': True,
            'status': 'operational',
            'client_id': config.DHAN_CLIENT_ID,
            'authenticated': bool(config.DHAN_ACCESS_TOKEN),
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Status endpoint error: {str(e)}")
        return jsonify({
            'success': False,
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/utility/time-convert', methods=['POST'])
@error_handler
def time_converter():
    """Time converter utility"""
    logger.info("Time converter utility called")
    data = request.get_json() or {}
    client = get_dhan_client()
    
    try:
        timestamp = data.get('timestamp')
        if not timestamp:
            return jsonify({
                'success': False,
                'error': 'timestamp is required'
            }), 400
        
        # Convert Unix timestamp to ISO format
        if isinstance(timestamp, (int, float)):
            dt = datetime.fromtimestamp(timestamp)
        else:
            dt = datetime.fromisoformat(timestamp)
        
        # Use client's time converter if available
        try:
            response = client.convert_to_date_time(timestamp=timestamp)
            logger.info(f"Time converted: {timestamp}")
            return jsonify({
                'success': True,
                'input': timestamp,
                'iso_format': dt.isoformat(),
                'unix_timestamp': dt.timestamp(),
                'readable': dt.strftime('%Y-%m-%d %H:%M:%S'),
                'sdk_response': response
            })
        except:
            logger.info(f"Time converted (no SDK): {timestamp}")
            return jsonify({
                'success': True,
                'input': timestamp,
                'iso_format': dt.isoformat(),
                'unix_timestamp': dt.timestamp(),
                'readable': dt.strftime('%Y-%m-%d %H:%M:%S')
            })
    except Exception as e:
        logger.error(f"Time converter error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/utility/indices', methods=['GET'])
@error_handler
def get_indices():
    """Get market indices"""
    logger.info("Get indices called")
    try:
        return jsonify({
            'success': True,
            'indices': config.INDICES,
            'count': len(config.INDICES)
        })
    except Exception as e:
        logger.error(f"Get indices error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    logger.warning(f"404 error: {request.path}")
    return jsonify({
        'success': False,
        'error': 'Resource not found',
        'path': request.path
    }), 404

@app.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 errors"""
    logger.warning(f"405 error: {request.method} {request.path}")
    return jsonify({
        'success': False,
        'error': 'Method not allowed',
        'method': request.method,
        'path': request.path
    }), 405

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"500 error: {str(error)}", exc_info=True)
    return jsonify({
        'success': False,
        'error': 'Internal server error',
        'timestamp': datetime.utcnow().isoformat()
    }), 500

# ==================== API DOCUMENTATION ====================

@app.route('/', methods=['GET'])
@error_handler
def api_documentation():
    """API documentation endpoint"""
    logger.info("API documentation accessed")
    return jsonify({
        'success': True,
        'name': 'DhanHQ Analytics Backend',
        'version': '1.0.0',
        'client_id': config.DHAN_CLIENT_ID,
        'sdk_version': 'dhanhq==2.2.0',
        'endpoints': {
            'authentication': {
                'health': 'GET /auth/health',
                'status': 'GET /auth/status',
                'dhan_context': 'POST /auth/dhan-context',
                'oauth_initiate': 'POST /auth/oauth/initiate',
                'oauth_token': 'POST /auth/oauth/token',
                'pin_totp': 'POST /auth/pin-totp',
                'renew_token': 'POST /auth/renew',
                'user_profile': 'GET /auth/profile'
            },
            'orders': {
                'place': 'POST /order/place',
                'list': 'GET /order/list',
                'by_id': 'GET /order/<order_id>',
                'by_correlation_id': 'GET /order/correlation/<correlation_id>',
                'modify': 'PUT /order/modify/<order_id>',
                'cancel': 'DELETE /order/cancel/<order_id>'
            },
            'portfolio': {
                'funds': 'GET /portfolio/funds',
                'positions': 'GET /portfolio/positions',
                'holdings': 'GET /portfolio/holdings',
                'trade_book': 'GET /portfolio/trades',
                'trade_history': 'GET /portfolio/trade-history'
            },
            'market': {
                'quote': 'GET /data/quote/<symbol>',
                'historical': 'GET /data/historical/<symbol>',
                'intraday': 'GET /data/intraday/<symbol>',
                'option_chain': 'GET /data/option-chain/<symbol>',
                'expired_options': 'GET /data/expired-options',
                'expiry_list': 'GET /data/expiry-list/<symbol>',
                'security_list': 'GET /data/security-list'
            },
            'forever_orders': {
                'place': 'POST /forever/place',
                'modify': 'PUT /forever/modify/<order_id>',
                'cancel': 'DELETE /forever/cancel/<order_id>'
            },
            'websocket': {
                'market_feed_start': 'POST /ws/market-feed/start',
                'market_feed_data': 'GET /ws/market-feed/data',
                'market_feed_stop': 'POST /ws/market-feed/stop',
                'order_updates_start': 'POST /ws/order-updates/start',
                'order_updates_data': 'GET /ws/order-updates/data',
                'full_depth_start': 'POST /ws/full-depth/start',
                'full_depth_data': 'GET /ws/full-depth/data'
            },
            'edis': {
                'generate_tpin': 'POST /edis/tpin',
                'open_browser': 'POST /edis/browser',
                'inquiry': 'GET /edis/inquiry'
            },
            'ip_management': {
                'set_ip': 'POST /admin/set-ip',
                'modify_ip': 'PUT /admin/modify-ip',
                'get_ip': 'GET /admin/get-ip'
            },
            'utility': {
                'health': 'GET /health',
                'status': 'GET /status',
                'time_converter': 'POST /utility/time-convert',
                'indices': 'GET /utility/indices'
            }
        }
    })

# ==================== MAIN ====================

if __name__ == '__main__':
    logger.info("="*60)
    logger.info("Starting DhanHQ Analytics Backend")
    logger.info(f"Client ID: {config.DHAN_CLIENT_ID}")
    logger.info(f"Environment: {config.FLASK_ENV}")
    logger.info("="*60)
    
    # Run Flask app
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=config.DEBUG,
        use_reloader=config.DEBUG
    )

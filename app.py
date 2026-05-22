import logging
import json
import os
import time
import webbrowser
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

def get_dhan_client():
    """Get or initialize DhanClient"""
    global dhan_client
    if not dhan_client:
        dhan_client = DhanClient(client_id=config.DHAN_CLIENT_ID)
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

# ==================== AUTH ENDPOINTS ====================

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
        # Check if we have valid access token
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

@app.route('/auth/oauth/login', methods=['GET'])
@error_handler
def oauth_login():
    """OAuth login endpoint"""
    logger.info("OAuth login initiated")
    # Construct OAuth URL
    oauth_url = f"https://api.dhan.co/oauth/authorize?client_id={config.DHAN_OAUTH_CLIENT_ID}&redirect_uri={config.DHAN_OAUTH_REDIRECT_URI}&response_type=code"
    logger.info(f"Redirecting to OAuth URL: {oauth_url}")
    return redirect(oauth_url)

@app.route('/auth/callback', methods=['GET'])
@error_handler
def oauth_callback():
    """OAuth callback endpoint"""
    code = request.args.get('code')
    logger.info(f"OAuth callback received with code: {code}")
    
    if not code:
        return jsonify({
            'success': False,
            'error': 'No authorization code received'
        }), 400
    
    try:
        # Exchange code for access token
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
                'access_token': token_data.get('access_token')
            })
        else:
            logger.error(f"OAuth token exchange failed: {response.text}")
            return jsonify({
                'success': False,
                'error': 'Token exchange failed'
            }), 400
    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}")
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
        # Generate TOTP if secret is configured
        totp = None
        if config.DHAN_TOTP_SECRET:
            totp_generator = pyotp.TOTP(config.DHAN_TOTP_SECRET)
            totp = totp_generator.now()
            logger.info("TOTP generated successfully")
        
        client = get_dhan_client()
        # Store credentials for later use
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

@app.route('/auth/renew-token', methods=['POST'])
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

@app.route('/auth/user-profile', methods=['GET'])
@error_handler
def user_profile():
    """Get user profile"""
    logger.info("User profile endpoint called")
    client = get_dhan_client()
    
    try:
        # This would typically come from the API response
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

@app.route('/orders/place', methods=['POST'])
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

@app.route('/orders/modify', methods=['PUT'])
@error_handler
def modify_order():
    """Modify an existing order"""
    logger.info("Modify order called")
    data = request.get_json() or {}
    client = get_dhan_client()
    
    try:
        required_fields = ['order_id']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'{field} is required'
                }), 400
        
        response = client.modify_order(
            order_id=data['order_id'],
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

@app.route('/orders/cancel', methods=['DELETE'])
@error_handler
def cancel_order():
    """Cancel an order"""
    logger.info("Cancel order called")
    data = request.get_json() or {}
    client = get_dhan_client()
    
    try:
        if 'order_id' not in data:
            return jsonify({
                'success': False,
                'error': 'order_id is required'
            }), 400
        
        response = client.cancel_order(order_id=data['order_id'])
        
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

@app.route('/orders/list', methods=['GET'])
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

@app.route('/orders/<order_id>', methods=['GET'])
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

@app.route('/orders/correlation/<correlation_id>', methods=['GET'])
@error_handler
def get_order_by_correlation_id(correlation_id):
    """Get order by correlation ID"""
    logger.info(f"Get order by correlation ID called: {correlation_id}")
    client = get_dhan_client()
    
    try:
        response = client.get_order_by_correlation_id(order_correlation_id=correlation_id)
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

# ==================== PORTFOLIO ENDPOINTS ====================

@app.route('/portfolio/funds', methods=['GET'])
@error_handler
def get_funds():
    """Get fund details"""
    logger.info("Get funds called")
    client = get_dhan_client()
    
    try:
        response = client.get_fund()
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

@app.route('/portfolio/trade-book', methods=['GET'])
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

@app.route('/market/ohlc', methods=['POST'])
@error_handler
def get_ohlc_data():
    """Get OHLC data"""
    logger.info("Get OHLC data called")
    data = request.get_json() or {}
    client = get_dhan_client()
    
    try:
        required_fields = ['security_id', 'exchange_segment']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'{field} is required'
                }), 400
        
        response = client.get_ohlc(
            security_id=data['security_id'],
            exchange_segment=data['exchange_segment']
        )
        
        logger.info(f"OHLC data retrieved for security {data['security_id']}")
        return jsonify({
            'success': True,
            'ohlc': response
        })
    except Exception as e:
        logger.error(f"Get OHLC error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/market/historical-daily', methods=['POST'])
@error_handler
def get_historical_daily():
    """Get historical daily data"""
    logger.info("Get historical daily data called")
    data = request.get_json() or {}
    client = get_dhan_client()
    
    try:
        required_fields = ['security_id', 'exchange_segment']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'{field} is required'
                }), 400
        
        response = client.get_historical_daily_data(
            security_id=data['security_id'],
            exchange_segment=data['exchange_segment'],
            start_date=data.get('start_date'),
            end_date=data.get('end_date')
        )
        
        logger.info(f"Historical daily data retrieved for security {data['security_id']}")
        return jsonify({
            'success': True,
            'data': response if isinstance(response, list) else [response],
            'count': len(response) if isinstance(response, list) else 1
        })
    except Exception as e:
        logger.error(f"Get historical daily error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/market/intraday-minute', methods=['POST'])
@error_handler
def get_intraday_minute():
    """Get intraday minute data"""
    logger.info("Get intraday minute data called")
    data = request.get_json() or {}
    client = get_dhan_client()
    
    try:
        required_fields = ['security_id', 'exchange_segment']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'{field} is required'
                }), 400
        
        response = client.get_intraday_minute_data(
            security_id=data['security_id'],
            exchange_segment=data['exchange_segment']
        )
        
        logger.info(f"Intraday minute data retrieved for security {data['security_id']}")
        return jsonify({
            'success': True,
            'data': response if isinstance(response, list) else [response],
            'count': len(response) if isinstance(response, list) else 1
        })
    except Exception as e:
        logger.error(f"Get intraday minute error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/market/option-chain', methods=['POST'])
@error_handler
def get_option_chain():
    """Get option chain data"""
    logger.info("Get option chain called")
    data = request.get_json() or {}
    client = get_dhan_client()
    
    try:
        required_fields = ['security_id']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'{field} is required'
                }), 400
        
        response = client.get_option_chain(
            security_id=data['security_id'],
            expiry_date=data.get('expiry_date'),
            strike_price=data.get('strike_price'),
            option_type=data.get('option_type')
        )
        
        logger.info(f"Option chain retrieved for security {data['security_id']}")
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

@app.route('/market/expired-options', methods=['GET'])
@error_handler
def get_expired_options():
    """Get expired options"""
    logger.info("Get expired options called")
    client = get_dhan_client()
    
    try:
        response = client.get_expired_options()
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

@app.route('/market/expiry-list', methods=['GET'])
@error_handler
def get_expiry_list():
    """Get expiry list"""
    logger.info("Get expiry list called")
    client = get_dhan_client()
    
    try:
        response = client.get_expiry_list()
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

@app.route('/market/security-list', methods=['GET'])
@error_handler
def get_security_list():
    """Get security list"""
    logger.info("Get security list called")
    client = get_dhan_client()
    
    try:
        response = client.get_security_list()
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

# ==================== FOREVER ORDERS ENDPOINTS ====================

@app.route('/forever-orders/place', methods=['POST'])
@error_handler
def place_forever_order():
    """Place a forever order"""
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
        
        response = client.place_forever_order(
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

@app.route('/forever-orders/modify', methods=['PUT'])
@error_handler
def modify_forever_order():
    """Modify a forever order"""
    logger.info("Modify forever order called")
    data = request.get_json() or {}
    client = get_dhan_client()
    
    try:
        if 'order_id' not in data:
            return jsonify({
                'success': False,
                'error': 'order_id is required'
            }), 400
        
        response = client.modify_forever_order(
            order_id=data['order_id'],
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

@app.route('/forever-orders/cancel', methods=['DELETE'])
@error_handler
def cancel_forever_order():
    """Cancel a forever order"""
    logger.info("Cancel forever order called")
    data = request.get_json() or {}
    client = get_dhan_client()
    
    try:
        if 'order_id' not in data:
            return jsonify({
                'success': False,
                'error': 'order_id is required'
            }), 400
        
        response = client.cancel_forever_order(order_id=data['order_id'])
        
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

# ==================== WEBSOCKET ENDPOINTS ====================

@app.route('/websocket/market-feed', methods=['GET'])
@error_handler
def websocket_market_feed():
    """Market feed WebSocket configuration"""
    logger.info("Market feed WebSocket endpoint called")
    try:
        return jsonify({
            'success': True,
            'message': 'Market feed WebSocket available',
            'connection_url': 'ws://localhost:5000/ws/market-feed',
            'channels': ['price', 'volume', 'trades']
        })
    except Exception as e:
        logger.error(f"Market feed WebSocket error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/websocket/order-update', methods=['GET'])
@error_handler
def websocket_order_update():
    """Order update WebSocket configuration"""
    logger.info("Order update WebSocket endpoint called")
    try:
        return jsonify({
            'success': True,
            'message': 'Order update WebSocket available',
            'connection_url': 'ws://localhost:5000/ws/order-update',
            'events': ['order_placed', 'order_executed', 'order_rejected', 'order_modified', 'order_cancelled']
        })
    except Exception as e:
        logger.error(f"Order update WebSocket error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/websocket/full-depth', methods=['GET'])
@error_handler
def websocket_full_depth():
    """Full depth WebSocket configuration"""
    logger.info("Full depth WebSocket endpoint called")
    try:
        return jsonify({
            'success': True,
            'message': 'Full depth WebSocket available',
            'connection_url': 'ws://localhost:5000/ws/full-depth',
            'data': ['bid_queue', 'ask_queue']
        })
    except Exception as e:
        logger.error(f"Full depth WebSocket error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

# ==================== eDIS ENDPOINTS ====================

@app.route('/edis/generate-tpin', methods=['POST'])
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
        
        logger.info(f"TPIN generated successfully")
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

@app.route('/edis/open-browser-tpin', methods=['POST'])
@error_handler
def open_browser_for_tpin():
    """Open browser for eDIS TPIN"""
    logger.info("Open browser for TPIN called")
    data = request.get_json() or {}
    
    try:
        tpin_url = data.get('tpin_url')
        if not tpin_url:
            return jsonify({
                'success': False,
                'error': 'tpin_url is required'
            }), 400
        
        webbrowser.open(tpin_url)
        logger.info(f"Browser opened for TPIN")
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

@app.route('/edis/inquiry', methods=['POST'])
@error_handler
def edis_inquiry():
    """eDIS inquiry"""
    logger.info("eDIS inquiry called")
    data = request.get_json() or {}
    client = get_dhan_client()
    
    try:
        response = client.get_edis_inquiry(
            isin=data.get('isin')
        )
        
        logger.info(f"eDIS inquiry retrieved")
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

# ==================== IP ENDPOINTS ====================

@app.route('/ip/set', methods=['POST'])
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
        
        response = client.set_ip(ip_address=data['ip_address'])
        
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

@app.route('/ip/modify', methods=['PUT'])
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
        
        response = client.modify_ip(
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

@app.route('/ip/get', methods=['GET'])
@error_handler
def get_ip():
    """Get user IP"""
    logger.info("Get IP called")
    client = get_dhan_client()
    
    try:
        response = client.get_ip()
        logger.info(f"IP retrieved successfully")
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

@app.route('/util/health', methods=['GET'])
@error_handler
def util_health():
    """Health check utility"""
    logger.info("Health check utility called")
    return jsonify({
        'success': True,
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'server': 'DhanHQ Analytics Backend',
        'version': '1.0.0'
    })

@app.route('/util/status', methods=['GET'])
@error_handler
def util_status():
    """Status utility"""
    logger.info("Status utility called")
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
        logger.error(f"Status utility error: {str(e)}")
        return jsonify({
            'success': False,
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/util/time-converter', methods=['POST'])
@error_handler
def time_converter():
    """Time converter utility"""
    logger.info("Time converter utility called")
    data = request.get_json() or {}
    
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
        
        logger.info(f"Time converted: {timestamp}")
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

@app.route('/util/indices', methods=['GET'])
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
        'endpoints': {
            'authentication': {
                'health': 'GET /auth/health',
                'status': 'GET /auth/status',
                'dhan_context': 'POST /auth/dhan-context',
                'oauth_login': 'GET /auth/oauth/login',
                'oauth_callback': 'GET /auth/callback',
                'pin_totp': 'POST /auth/pin-totp',
                'renew_token': 'POST /auth/renew-token',
                'user_profile': 'GET /auth/user-profile'
            },
            'orders': {
                'place': 'POST /orders/place',
                'modify': 'PUT /orders/modify',
                'cancel': 'DELETE /orders/cancel',
                'list': 'GET /orders/list',
                'by_id': 'GET /orders/<order_id>',
                'by_correlation_id': 'GET /orders/correlation/<correlation_id>'
            },
            'portfolio': {
                'funds': 'GET /portfolio/funds',
                'positions': 'GET /portfolio/positions',
                'holdings': 'GET /portfolio/holdings',
                'trade_book': 'GET /portfolio/trade-book',
                'trade_history': 'GET /portfolio/trade-history'
            },
            'market': {
                'ohlc': 'POST /market/ohlc',
                'historical_daily': 'POST /market/historical-daily',
                'intraday_minute': 'POST /market/intraday-minute',
                'option_chain': 'POST /market/option-chain',
                'expired_options': 'GET /market/expired-options',
                'expiry_list': 'GET /market/expiry-list',
                'security_list': 'GET /market/security-list'
            },
            'forever_orders': {
                'place': 'POST /forever-orders/place',
                'modify': 'PUT /forever-orders/modify',
                'cancel': 'DELETE /forever-orders/cancel'
            },
            'websocket': {
                'market_feed': 'GET /websocket/market-feed',
                'order_update': 'GET /websocket/order-update',
                'full_depth': 'GET /websocket/full-depth'
            },
            'edis': {
                'generate_tpin': 'POST /edis/generate-tpin',
                'open_browser': 'POST /edis/open-browser-tpin',
                'inquiry': 'POST /edis/inquiry'
            },
            'ip': {
                'set': 'POST /ip/set',
                'modify': 'PUT /ip/modify',
                'get': 'GET /ip/get'
            },
            'utility': {
                'health': 'GET /util/health',
                'status': 'GET /util/status',
                'time_converter': 'POST /util/time-converter',
                'indices': 'GET /util/indices'
            }
        }
    })

# ==================== MAIN ====================

if __name__ == '__main__':
    logger.info("Starting DhanHQ Analytics Backend")
    logger.info(f"Client ID: {config.DHAN_CLIENT_ID}")
    logger.info(f"Environment: {config.FLASK_ENV}")
    
    # Run Flask app
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=config.DEBUG,
        use_reloader=config.DEBUG
    )

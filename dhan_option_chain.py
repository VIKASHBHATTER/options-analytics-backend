"""
Dhan Option Chain - Direct API Calls
No external library needed except requests
"""

from dotenv import load_dotenv
load_dotenv()
import os
import requests

TOKEN = os.getenv('DHAN_ACCESS_TOKEN')
CLIENT_ID = os.getenv('DHAN_CLIENT_ID', '1106299230')

HEADERS = {
    'Accept': 'application/json',
    'access-token': TOKEN,
    'client-id': CLIENT_ID
}

INDICES = {
    'NIFTY': {'id': '13', 'segment': 'IDX_I'},
    'BANKNIFTY': {'id': '25', 'segment': 'IDX_I'},
    'FINNIFTY': {'id': '27', 'segment': 'IDX_I'},
    'SENSEX': {'id': '51', 'segment': 'IDX_I'}
}


def api_call(method, endpoint, params=None):
    """Make API call and return parsed response"""
    url = f'https://api.dhan.co{endpoint}'
    try:
        if method == 'GET':
            r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        else:
            r = requests.post(url, headers=HEADERS, json=params, timeout=15)
        
        if r.status_code == 200:
            try:
                return r.json()
            except:
                return {'status': 'error', 'message': 'Invalid JSON', 'raw': r.text[:100]}
        else:
            return {'status': 'error', 'message': f'HTTP {r.status_code}', 'raw': r.text[:100]}
    except requests.exceptions.Timeout:
        return {'status': 'error', 'message': 'Timeout'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


def get_expiry_list(index_name):
    """Get expiry dates"""
    idx = INDICES.get(index_name.upper())
    if not idx:
        return {'status': 'error', 'message': 'Invalid index'}
    
    return api_call('GET', '/option-chain/expiry-list', {
        'securityId': idx['id'],
        'exchangeSegment': idx['segment']
    })


def get_option_chain(index_name, expiry):
    """Get option chain data"""
    idx = INDICES.get(index_name.upper())
    if not idx:
        return {'status': 'error', 'message': 'Invalid index'}
    
    return api_call('GET', '/option-chain', {
        'securityId': idx['id'],
        'exchangeSegment': idx['segment'],
        'expiry': expiry
    })


def test_index(index_name):
    """Test one index"""
    print(f'\n{"="*50}')
    print(f'📊 {index_name}')
    print('='*50)
    
    # Get expiry
    exp = get_expiry_list(index_name)
    if exp.get('status') != 'success':
        print(f'❌ Expiry Error: {exp.get("message")}')
        return
    
    expiries = exp.get('data', [])
    print(f'✅ Expiry Status: success')
    print(f'📅 Found {len(expiries)} expiries')
    if not expiries:
        return
    
    first = expiries[0]
    print(f'📅 First: {first}')
    
    # Get option chain
    chain = get_option_chain(index_name, first)
    if chain.get('status') != 'success':
        print(f'❌ Chain Error: {chain.get("message")}')
        if 'raw' in chain:
            print(f'   Raw: {chain["raw"]}')
        return
    
    data = chain.get('data', {})
    oc = data.get('oc', {})
    
    print(f'✅ Chain Status: success')
    print(f'💰 Last Price: {data.get("last_price")}')
    print(f'📊 Strikes: {len(oc)}')
    
    if oc:
        strikes = sorted(oc.keys(), key=float)
        print(f'🔹 Range: {strikes[0]} - {strikes[-1]}')
        atm = strikes[len(strikes)//2]
        print(f'🔹 ATM: {atm}')
        
        ce = oc[atm].get('CE', {})
        pe = oc[atm].get('PE', {})
        print(f'💚 CE LTP: {ce.get("ltp")} | OI: {ce.get("oi")}')
        print(f'❤️ PE LTP: {pe.get("ltp")} | OI: {pe.get("oi")}')


# ============== MAIN ==============
if __name__ == '__main__':
    print('🚀 DHAN OPTION CHAIN - ALL INDICES')
    print(f'Token: {TOKEN[:15]}...' if TOKEN else '❌ NOT SET')
    print(f'Client: {CLIENT_ID}')
    
    for index in ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX']:
        test_index(index)
    
    print('\n✅ DONE')


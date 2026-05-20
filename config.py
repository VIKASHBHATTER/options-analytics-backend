import os
from dotenv import load_dotenv

# Load from .env file
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

CLIENT_ID = os.getenv('DHAN_CLIENT_ID', '1106299230')
ACCESS_TOKEN = os.getenv('DHAN_ACCESS_TOKEN', '')

if not ACCESS_TOKEN:
    raise ValueError('Set DHAN_ACCESS_TOKEN in .env file!')

BASE_URL = 'https://api.dhan.co/v2'
HEADERS = {
    'access-token': ACCESS_TOKEN,
    'client-id': CLIENT_ID,
    'Content-Type': 'application/json'
}

import os
from datetime import datetime, timedelta

class DhanTokenManager:
    def __init__(self):
        self.access_token = os.getenv('DHAN_ACCESS_TOKEN')
        self.client_id = os.getenv('DHAN_CLIENT_ID', '1106299230')
        self.last_refresh = None
        
    def is_token_expired(self):
        if not self.last_refresh:
            return True
        elapsed = datetime.now() - self.last_refresh
        return elapsed > timedelta(hours=6)
    
    def refresh_token(self):
        print("TOKEN EXPIRED!")
        print("=" * 50)
        print("Steps to get new token:")
        print("1. Login to https://dhan.co/")
        print("2. Go to 'My Account' -> 'API Access'")
        print("3. Generate new Access Token")
        print("4. Update your .env file")
        print("=" * 50)
        
        new_token = os.getenv('DHAN_ACCESS_TOKEN')
        if new_token != self.access_token:
            self.access_token = new_token
            self.last_refresh = datetime.now()
            print("New token detected!")
            return True
        return False
    
    def get_valid_token(self):
        if self.is_token_expired():
            if not self.refresh_token():
                raise Exception("Token expired! Update DHAN_ACCESS_TOKEN in .env")
        return self.access_token

token_manager = DhanTokenManager()

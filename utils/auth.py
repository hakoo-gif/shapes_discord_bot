import aiohttp
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class ShapesAuth:
    """Handles Shapes API authentication"""
    
    AUTH_BASE_URL = "https://api.shapes.inc/auth"
    SITE_BASE_URL = "https://shapes.inc"
    
    def __init__(self, app_id: str):
        self.app_id = app_id
    
    def get_auth_url(self, app_id: str) -> str:
        """Generate authorization URL for users"""
        return f"{self.SITE_BASE_URL}/authorize?app_id={app_id}"
    
    async def exchange_code_for_token(self, code: str, app_id: str) -> Optional[str]:
        """
        Exchange one-time code for user auth token
        
        Args:
            code: One-time code from user authorization
            app_id: The app ID for the authorization
            
        Returns:
            User auth token if successful, None otherwise
        """
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "app_id": app_id,
                    "code": code.strip()
                }
                
                async with session.post(
                    f"{self.AUTH_BASE_URL}/nonce",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("auth_token")
                    else:
                        error_text = await response.text()
                        logger.error(f"Auth token exchange failed: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error exchanging code for token: {e}")
            return None
    
    @staticmethod
    def create_auth_headers(app_id: str, user_auth_token: str) -> Dict[str, str]:
        """
        Create headers for authenticated API requests using X-App-ID and X-User-Auth
        
        Args:
            app_id: The app ID
            user_auth_token: User's authentication token
            
        Returns:
            Dictionary of headers with app ID and user auth
        """
        return {
            "X-App-ID": app_id,
            "X-User-Auth": user_auth_token,
            "Content-Type": "application/json"
        }

class AuthManager:
    """Manages authentication state and tokens"""
    
    def __init__(self, storage, default_app_id: str):
        self.storage = storage
        self.default_app_id = default_app_id
        self.shapes_auth = ShapesAuth(default_app_id)
    
    async def get_user_auth_data(self, user_id: int) -> Optional[Dict[str, str]]:
        """Get stored auth data for user (includes app_id and auth_token)"""
        return await self.storage.get_user_auth(user_id)
    
    async def store_user_auth_data(self, user_id: int, app_id: str, auth_token: str):
        """Store auth data for user"""
        auth_data = {
            "app_id": app_id,
            "auth_token": auth_token
        }
        await self.storage.set_user_auth(user_id, auth_data)
    
    async def remove_user_auth_token(self, user_id: int) -> bool:
        """Remove auth token for user"""
        return await self.storage.remove_user_auth(user_id)
    
    def get_auth_url(self, app_id: str) -> str:
        """Get authorization URL"""
        return self.shapes_auth.get_auth_url(app_id)
    
    async def exchange_code(self, user_id: int, code: str, app_id: str) -> bool:
        """
        Exchange code for token and store it
        
        Args:
            user_id: Discord user ID
            code: One-time authorization code
            app_id: The app ID for the authorization
            
        Returns:
            True if successful, False otherwise
        """
        token = await self.shapes_auth.exchange_code_for_token(code, app_id)
        if token:
            await self.store_user_auth_data(user_id, app_id, token)
            return True
        return False
    
    def create_headers_for_user(self, app_id: str, user_auth_token: str) -> Dict[str, str]:
        """Create API headers for authenticated user"""
        return ShapesAuth.create_auth_headers(app_id, user_auth_token)
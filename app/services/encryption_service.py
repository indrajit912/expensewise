import base64
import os
from flask import session, g, current_app
from flask_login import current_user
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from app.extensions import cache

import threading
_local_data = threading.local()

class EncryptionService:
    """Service to handle end-to-end user data encryption and key management."""

    @staticmethod
    def derive_key(password: str, salt: bytes) -> bytes:
        """Derives a 32-byte URL-safe key from the user password using PBKDF2-HMAC-SHA256."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))

    @staticmethod
    def generate_fernet_key() -> str:
        """Generates a secure random 32-byte Fernet key."""
        return Fernet.generate_key().decode()

    @staticmethod
    def encrypt_fernet_key(fernet_key: str, password_derived_key: bytes) -> str:
        """Encrypts the Fernet key with the derived password key."""
        f = Fernet(password_derived_key)
        return f.encrypt(fernet_key.encode()).decode()

    @staticmethod
    def decrypt_fernet_key(encrypted_fernet_key: str, password_derived_key: bytes) -> str:
        """Decrypts the user's Fernet key using the derived password key."""
        f = Fernet(password_derived_key)
        return f.decrypt(encrypted_fernet_key.encode()).decode()

    @staticmethod
    def set_override_key(key: str):
        """Sets a thread-global override key. Useful for CLI commands and test fixtures."""
        _local_data.override_key = key

    @staticmethod
    def get_user_key() -> str:
        """Retrieves the decrypted Fernet key for the active user session or API token."""
        override = getattr(_local_data, 'override_key', None)
        if override:
            return override

        from flask import has_request_context, g, session
        if has_request_context():
            # Check API token authorization context first (for REST calls)
            if hasattr(g, 'current_token') and g.current_token:
                val = cache.get(f"user_key_{g.current_token.token}")
                if val:
                    return val

            # Fallback to session memory (for browser navigation)
            try:
                val = session.get('user_fernet_key')
                if val:
                    return val
            except (RuntimeError, KeyError):
                pass

        return None

    @staticmethod
    def store_user_key(user_id: str, decrypted_key: str, token: str = None):
        """Saves the decrypted Fernet key inside the request context (session or cache)."""
        from flask import has_request_context, session
        if token:
            # Keys for token authentication are cached in-memory mapped to the access token
            cache.set(f"user_key_{token}", decrypted_key, timeout=86400 * 30)
        elif has_request_context():
            # Web dashboard users store the key in flask session cookie memory
            try:
                session['user_fernet_key'] = decrypted_key
            except (RuntimeError, AttributeError):
                pass

    @staticmethod
    def clear_user_key(token: str = None):
        """Purges key material upon logout or session revocation."""
        if hasattr(_local_data, 'override_key'):
            del _local_data.override_key
        
        from flask import has_request_context, session
        if token:
            cache.delete(f"user_key_{token}")
        if has_request_context():
            try:
                session.pop('user_fernet_key', None)
            except (RuntimeError, AttributeError):
                pass

    @staticmethod
    def encrypt(plaintext: str) -> str:
        """Encrypts data string using the current user's unlocked Fernet key."""
        if plaintext is None:
            return None
        
        key = EncryptionService.get_user_key()
        if not key:
            raise ValueError("Encryption key is locked. Please log in to unlock your data vault.")
            
        f = Fernet(key.encode())
        return f.encrypt(str(plaintext).encode()).decode()

    @staticmethod
    def decrypt(ciphertext: str) -> str:
        """Decrypts database ciphertext using the current user's unlocked Fernet key."""
        if ciphertext is None:
            return None
            
        key = EncryptionService.get_user_key()
        if not key:
            raise ValueError("Encryption key is locked. Please log in to unlock your data vault.")
            
        f = Fernet(key.encode())
        return f.decrypt(ciphertext.encode()).decode()

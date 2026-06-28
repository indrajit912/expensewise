import uuid
import secrets
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from sqlalchemy.orm import validates
from sqlalchemy import event
from app.extensions import db, login_manager

class User(db.Model, UserMixin):
    """User Model for multi-user accounts and role authorization."""
    __tablename__ = 'users'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(50), unique=True, index=True, nullable=True)
    email = db.Column(db.String(120), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    date_joined = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=False, nullable=False) # Defaults to False for registration verification
    is_email_verified = db.Column(db.Boolean, default=False, nullable=False)
    default_currency = db.Column(db.String(10), nullable=False, default='INR')
    
    # End-to-End Encryption Columns
    encrypted_fernet_key = db.Column(db.Text, nullable=False)
    server_encrypted_fernet_key = db.Column(db.Text, nullable=True)
    kdf_salt = db.Column(db.LargeBinary, nullable=False)

    # Administrator Roles
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_super_admin = db.Column(db.Boolean, default=False, nullable=False)

    # Security/Lockout Columns
    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)
    lockout_until = db.Column(db.DateTime, nullable=True)

    # Relationships
    expenses = db.relationship('Expense', back_populates='user', cascade='all, delete-orphan')
    api_tokens = db.relationship('APIToken', back_populates='user', cascade='all, delete-orphan')

    def __init__(self, **kwargs):
        import os
        from app.services.encryption_service import EncryptionService
        
        super(User, self).__init__(**kwargs)
        
        # Pre-seed cryptographic salt and Fernet key
        if not self.kdf_salt:
            self.kdf_salt = os.urandom(16)
        if not self.encrypted_fernet_key:
            dummy_password = secrets.token_hex(16)
            derived = EncryptionService.derive_key(dummy_password, self.kdf_salt)
            fernet_key = EncryptionService.generate_fernet_key()
            self.encrypted_fernet_key = EncryptionService.encrypt_fernet_key(fernet_key, derived)
            
            # Seed server-encrypted copy
            try:
                server_derived = EncryptionService.get_server_master_key()
                self.server_encrypted_fernet_key = EncryptionService.encrypt_fernet_key(fernet_key, server_derived)
            except Exception:
                pass
                
            # Temporarily cache to thread memory for test suites/seeding
            if not EncryptionService.get_user_key():
                EncryptionService.set_override_key(fernet_key)

    def set_password(self, password):
        """Hashes the password securely and updates/re-encrypts the user's data Fernet key."""
        from app.services.encryption_service import EncryptionService
        
        self.password_hash = generate_password_hash(password)
        
        # Load active Fernet key or generate/recover one
        decrypted_key = EncryptionService.get_user_key()
        if not decrypted_key:
            # Attempt to recover via server-encrypted key if available
            if self.server_encrypted_fernet_key:
                try:
                    server_derived = EncryptionService.get_server_master_key()
                    decrypted_key = EncryptionService.decrypt_fernet_key(self.server_encrypted_fernet_key, server_derived)
                    EncryptionService.set_override_key(decrypted_key)
                except Exception:
                    pass
            
            if not decrypted_key:
                decrypted_key = EncryptionService.generate_fernet_key()
                EncryptionService.set_override_key(decrypted_key)
            
        derived_key = EncryptionService.derive_key(password, self.kdf_salt)
        self.encrypted_fernet_key = EncryptionService.encrypt_fernet_key(decrypted_key, derived_key)
        
        # Keep server-encrypted key in sync
        try:
            server_derived = EncryptionService.get_server_master_key()
            self.server_encrypted_fernet_key = EncryptionService.encrypt_fernet_key(decrypted_key, server_derived)
        except Exception:
            pass

    def check_password(self, password):
        """Verifies password hashes."""
        return check_password_hash(self.password_hash, password)

    def seed_defaults(self):
        """Seeds default categories and payment methods for this user."""
        from app.models.expense import Category, PaymentMethod
        
        category_colors = {
            'Food': '#f97316',
            'Snacks': '#fbbf24',
            'Groceries': '#10b981',
            'Shopping': '#f43f5e',
            'Travel': '#3b82f6',
            'Health': '#ef4444',
            'Essentials': '#8b5cf6',
            'Bills': '#6366f1',
            'Emergency': '#dc2626',
            'Others': '#64748b',
            'Toiletries': '#06b6d4',
            'Grooming': '#ec4899',
            'Study': '#7c3aed',
            'Trip': '#2563eb',
            'Chill': '#a855f7',
            'Gift': '#f472b6',
            'Kitchen': '#b45309',
            'Home Essentials': '#059669',
            'Rent': '#7c3aed',
            'Utilities': '#2563eb'
        }
        payment_colors = {
            'Cash': '#16a34a',
            'Paytm': '#1e40af',
            'Phonepe': '#0369a1',
            'Google Pay': '#ea580c',
            'BHIM': '#0d9488',
            'Card': '#2563eb',
            'Net Banking': '#0f766e',
            'NetBanking': '#0f766e'
        }
        
        for cat_name, cat_color in category_colors.items():
            db.session.add(Category(user_id=self.id, name=cat_name, color=cat_color))
                
        for pm_name, pm_color in payment_colors.items():
            db.session.add(PaymentMethod(user_id=self.id, name=pm_name, color=pm_color))
                
        db.session.commit()

    def generate_token(self, expires_in_days=30):
        """Generates a secure API token and saves it in the database."""
        token_str = secrets.token_urlsafe(32)
        expiration = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        api_token = APIToken(
            token=token_str,
            user_id=self.id,
            expires_at=expiration
        )
        db.session.add(api_token)
        db.session.commit()
        return token_str

    # Super Admin Immutable Validation Checks
    @validates('email')
    def validate_email(self, key, value):
        if self.is_super_admin and hasattr(self, 'email') and self.email and self.email != value:
            raise ValueError("Super administrator email address cannot be changed.")
        return value

    @validates('username')
    def validate_username(self, key, value):
        if self.is_super_admin and hasattr(self, 'username') and self.username and self.username != value:
            raise ValueError("Super administrator username cannot be changed.")
        return value

    @validates('is_admin')
    def validate_is_admin(self, key, value):
        if self.is_super_admin and hasattr(self, 'is_admin') and self.is_admin and not value:
            raise ValueError("Super administrator cannot lose administrator privileges.")
        return value

    @validates('is_super_admin')
    def validate_is_super_admin(self, key, value):
        if self.is_super_admin and hasattr(self, 'is_super_admin') and self.is_super_admin and not value:
            raise ValueError("Super administrator status cannot be revoked.")
        return value

    def avatar_url(self, size=32, default='identicon') -> str:
        """Generates a Gravatar URL for the user's email address."""
        import hashlib
        email_clean = self.email.strip().lower().encode('utf-8')
        email_hash = hashlib.md5(email_clean).hexdigest()
        return f"https://www.gravatar.com/avatar/{email_hash}?s={size}&d={default}"

    def __repr__(self):
        return f"<User {self.email}>"


class APIToken(db.Model):
    """API Token Model for REST client access control."""
    __tablename__ = 'api_tokens'

    token = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Relationships
    user = db.relationship('User', back_populates='api_tokens')

    @property
    def is_expired(self):
        """Checks if the API token is past its expiration date."""
        if self.expires_at.tzinfo is None:
            return self.expires_at < datetime.utcnow()
        return self.expires_at < datetime.now(timezone.utc)

    @property
    def is_valid(self):
        """Returns True if the token is active and not expired."""
        return self.is_active and not self.is_expired


class UserOTP(db.Model):
    """OTP Model for Email Verification."""
    __tablename__ = 'user_otps'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    otp_hash = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('otps', cascade='all, delete-orphan'))


class AuditLog(db.Model):
    """Audit Log Model for recording security and modification actions."""
    __tablename__ = 'audit_logs'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('logs', lazy=True))


@event.listens_for(User, 'before_delete')
def prevent_super_admin_deletion(mapper, connection, target):
    """Event listener to block deletion of the super admin."""
    if target.is_super_admin or target.username == 'ghostrix' or target.email == 'indrajitghosh912@gmail.com':
        raise ValueError("Super administrator account cannot be deleted.")


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login user loader callback."""
    return User.query.get(user_id)

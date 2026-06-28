import pytest
import random
from unittest.mock import patch
from app.models.user import User, UserOTP
from app import db

def test_user_registration(client, app):
    """Tests successful user registration and subsequent login."""
    # Register triggers OTP dispatch. Mock randint to have a deterministic OTP code.
    with patch('random.randint', return_value=123456):
        response = client.post('/auth/register', data={
            'name': 'Bob Tester',
            'username': 'bobtester',
            'email': 'bob@example.com',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'verification OTP has been sent' in response.data
    
    # Check that user is created in database but not yet active
    with app.app_context():
        user = User.query.filter_by(email='bob@example.com').first()
        assert user is not None
        assert user.is_active is False
        
    # Verify the registration OTP code to activate the user
    response_verify = client.post('/auth/verify-otp', data={
        'otp': '123456'
    }, follow_redirects=True)
    
    assert response_verify.status_code == 200
    assert b'verified and activated successfully' in response_verify.data
    
    with app.app_context():
        user_active = User.query.filter_by(email='bob@example.com').first()
        assert user_active.is_active is True
        assert user_active.check_password('Password123!') is True


def test_user_registration_email_exists(client, test_user):
    """Tests that registering with an existing email throws validation error."""
    response = client.post('/auth/register', data={
        'name': 'Duplicate Bob',
        'username': 'dup_bob',
        'email': 'test@example.com', # Pre-created by fixture
        'password': 'Password123!',
        'confirm_password': 'Password123!'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'An account with this email address already exists.' in response.data


def test_user_login_success(client, test_user):
    """Tests that a user can login with valid credentials."""
    response = client.post('/auth/login', data={
        'email': 'test@example.com',
        'password': 'Password123!',
        'remember_me': False
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Welcome back, Test User!' in response.data


def test_user_login_invalid(client, test_user):
    """Tests that login fails with invalid credentials."""
    response = client.post('/auth/login', data={
        'email': 'test@example.com',
        'password': 'wrongPassword123!'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Invalid email/username or password.' in response.data


def test_user_logout(client, test_user):
    """Tests that a logged in user can logout."""
    # Login first
    client.post('/auth/login', data={
        'email': 'test@example.com',
        'password': 'Password123!'
    })
    
    # Logout
    response = client.get('/auth/logout', follow_redirects=True)
    assert response.status_code == 200
    assert b'You have been logged out successfully.' in response.data


def test_password_reset_preserves_encrypted_data(client, app, test_user):
    """Verifies that resetting password does not invalidate encrypted expense data."""
    from app.services.encryption_service import EncryptionService
    from app.models.expense import Expense
    from decimal import Decimal
    from datetime import date
    
    # 1. Log in and add an expense (so it's encrypted with original key)
    client.post('/auth/login', data={
        'email': 'test@example.com',
        'password': 'Password123!'
    })
    
    # Add an expense via app context
    with app.app_context():
        derived = EncryptionService.derive_key("Password123!", test_user.kdf_salt)
        fernet_key = EncryptionService.decrypt_fernet_key(test_user.encrypted_fernet_key, derived)
        EncryptionService.set_override_key(fernet_key)
        
        expense = Expense(
            user_id=test_user.id,
            amount=Decimal('42.00'),
            category='Food',
            expense_date=date(2026, 6, 28),
            description='Secret Lunch'
        )
        db.session.add(expense)
        db.session.commit()
        expense_id = expense.id
        
        EncryptionService.clear_user_key()

    # 2. Logout the user
    client.get('/auth/logout')
    
    # 3. Simulate Forgot Password reset flow
    client.post(f'/auth/reset_password/{test_user.id}', data={
        'password': 'NewPassword123!',
        'confirm_password': 'NewPassword123!'
    })
    
    # 4. Log back in with the NEW password
    login_res = client.post('/auth/login', data={
        'email': 'test@example.com',
        'password': 'NewPassword123!'
    }, follow_redirects=True)
    assert login_res.status_code == 200
    assert b'Welcome back' in login_res.data
    
    # 5. Access the data directly to verify it decrypts successfully
    with app.app_context():
        user_reloaded = User.query.get(test_user.id)
        new_derived = EncryptionService.derive_key("NewPassword123!", user_reloaded.kdf_salt)
        new_fernet_key = EncryptionService.decrypt_fernet_key(user_reloaded.encrypted_fernet_key, new_derived)
        EncryptionService.set_override_key(new_fernet_key)
        
        exp_reloaded = Expense.query.get(expense_id)
        assert exp_reloaded.category == 'Food'
        assert float(exp_reloaded.amount) == 42.00
        assert exp_reloaded.description == 'Secret Lunch'
        
        EncryptionService.clear_user_key()


def test_change_password_preserves_encrypted_data(client, app, test_user):
    """Verifies that changing password from settings preserves encrypted expense data."""
    from app.services.encryption_service import EncryptionService
    from app.models.expense import Expense
    from decimal import Decimal
    from datetime import date
    
    # 1. Log in
    client.post('/auth/login', data={
        'email': 'test@example.com',
        'password': 'Password123!'
    })
    
    # Add an expense via app context
    with app.app_context():
        derived = EncryptionService.derive_key("Password123!", test_user.kdf_salt)
        fernet_key = EncryptionService.decrypt_fernet_key(test_user.encrypted_fernet_key, derived)
        EncryptionService.set_override_key(fernet_key)
        
        expense = Expense(
            user_id=test_user.id,
            amount=Decimal('88.50'),
            category='Utilities',
            expense_date=date(2026, 6, 28),
            description='Electricity Bill'
        )
        db.session.add(expense)
        db.session.commit()
        expense_id = expense.id
        
        EncryptionService.clear_user_key()
        
    # 2. Change password from settings
    settings_res = client.post('/settings', data={
        'action': 'change_password',
        'current_password': 'Password123!',
        'new_password': 'NewPassword123!',
        'confirm_password': 'NewPassword123!'
    }, follow_redirects=True)
    assert settings_res.status_code == 200
    assert b'changed successfully' in settings_res.data
    
    # 3. Logout
    client.get('/auth/logout')
    
    # 4. Log in with the new password
    login_res = client.post('/auth/login', data={
        'email': 'test@example.com',
        'password': 'NewPassword123!'
    }, follow_redirects=True)
    assert login_res.status_code == 200
    
    # 5. Verify the expense still decrypts correctly
    with app.app_context():
        user_reloaded = User.query.get(test_user.id)
        new_derived = EncryptionService.derive_key("NewPassword123!", user_reloaded.kdf_salt)
        new_fernet_key = EncryptionService.decrypt_fernet_key(user_reloaded.encrypted_fernet_key, new_derived)
        EncryptionService.set_override_key(new_fernet_key)
        
        exp_reloaded = Expense.query.get(expense_id)
        assert exp_reloaded.category == 'Utilities'
        assert float(exp_reloaded.amount) == 88.50
        assert exp_reloaded.description == 'Electricity Bill'
        
        EncryptionService.clear_user_key()


def test_custom_token_lifetimes(client, app, test_user):
    """Tests that token lifetimes are correctly defaulted to 1 day and custom lifetimes are restricted by permission."""
    from app.models.user import User, APIToken
    
    # Enable test_user login
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'Password123!'})
    
    # 1. Regular user without permission generating token via web dashboard (defaults to 1 day)
    client.post('/settings', data={'action': 'generate_token', 'expires_in_days': '30'}, follow_redirects=True)
    with app.app_context():
        token = APIToken.query.filter_by(user_id=test_user.id).order_by(APIToken.created_at.desc()).first()
        assert token is not None
        diff = token.expires_at - token.created_at
        assert abs(diff.total_seconds() - 86400) < 10
        
    # 2. Regular user without permission generating token via API endpoint (denied/returns 403)
    api_res = client.post('/api/v1/auth/login', json={
        'email': 'test@example.com',
        'password': 'Password123!',
        'expires_in_days': 15
    })
    assert api_res.status_code == 403
    assert b'do not have permission' in api_res.data
    
    # 3. Grant permission to regular user
    with app.app_context():
        u = User.query.get(test_user.id)
        u.can_create_custom_api_tokens = True
        db.session.commit()
        db.session.close()
        
    # Refresh session
    client.get('/auth/logout')
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'Password123!'})
        
    # 4. User with permission generating token via web dashboard (uses custom days)
    client.post('/settings', data={'action': 'generate_token', 'expires_in_days': '15'}, follow_redirects=True)
    with app.app_context():
        token = APIToken.query.filter_by(user_id=test_user.id).order_by(APIToken.created_at.desc()).first()
        diff = token.expires_at - token.created_at
        assert abs(diff.total_seconds() - 15 * 86400) < 10
        
    # 5. User with permission generating token via API (uses custom days)
    api_res = client.post('/api/v1/auth/login', json={
        'email': 'test@example.com',
        'password': 'Password123!',
        'expires_in_days': 30
    })
    assert api_res.status_code == 200
    res_data = api_res.get_json()
    token_str = res_data['token']
    with app.app_context():
        token = APIToken.query.filter_by(token=token_str).first()
        diff = token.expires_at - token.created_at
        assert abs(diff.total_seconds() - 30 * 86400) < 10

    # 6. Admin user generating custom token
    with app.app_context():
        u = User.query.get(test_user.id)
        u.can_create_custom_api_tokens = False
        u.is_admin = True
        db.session.commit()
        db.session.close()
        
    # Refresh session
    client.get('/auth/logout')
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'Password123!'})
        
    client.post('/settings', data={'action': 'generate_token', 'expires_in_days': '90'}, follow_redirects=True)
    with app.app_context():
        token = APIToken.query.filter_by(user_id=test_user.id).order_by(APIToken.created_at.desc()).first()
        diff = token.expires_at - token.created_at
        assert abs(diff.total_seconds() - 90 * 86400) < 10


def test_unverified_user_flow(client, app):
    """Tests the new OTP regeneration, verification workflow and security constraints for unverified accounts."""
    from app.models.user import User, UserOTP
    from app.extensions import db
    
    # 1. Register a new user (initially unverified)
    reg_res = client.post('/auth/register', data={
        'name': 'Unverified User',
        'username': 'unverified',
        'email': 'unverified@example.com',
        'password': 'Password123!',
        'confirm_password': 'Password123!'
    }, follow_redirects=True)
    assert reg_res.status_code == 200
    assert b'Enter Verification Code' in reg_res.data
    
    with app.app_context():
        user = User.query.filter_by(email='unverified@example.com').first()
        assert user is not None
        assert user.is_email_verified is False
        assert user.is_active is False
        
        # Get active OTP token details
        otp_record = UserOTP.query.filter_by(user_id=user.id).first()
        assert otp_record is not None
        initial_token_hash = otp_record.otp_hash

    # Log out to clear registration session variables
    client.get('/auth/logout')
    
    # 2. Attempt Web Login with unverified account
    web_login_res = client.post('/auth/login', data={
        'email': 'unverified@example.com',
        'password': 'Password123!'
    }, follow_redirects=True)
    assert web_login_res.status_code == 200
    assert b'email address has not yet been verified' in web_login_res.data
    assert b'Enter Verification Code' in web_login_res.data

    # 3. Attempt API Login with unverified account
    api_login_res = client.post('/api/v1/auth/login', json={
        'email': 'unverified@example.com',
        'password': 'Password123!'
    })
    assert api_login_res.status_code == 403
    api_login_data = api_login_res.get_json()
    assert api_login_data['error'] == 'Unverified'
    assert 'email address has not yet been verified' in api_login_data['message']

    # 4. Attempt rate-limiting on Resend Verification OTP
    # First resend should fail or be blocked by rate limit if too fast (< 60s)
    resend_res1 = client.post('/auth/resend-otp', follow_redirects=True)
    assert b'wait' in resend_res1.data
    
    # API resend rate limit check
    api_resend1 = client.post('/api/v1/auth/resend-otp', json={
        'email': 'unverified@example.com'
    })
    assert api_resend1.status_code == 429
    assert b'wait' in api_resend1.data
    
    # 5. Fast-forward OTP creation time in database to allow resending (bypass 60s rate limit in tests)
    with app.app_context():
        otp_record = UserOTP.query.filter_by(user_id=user.id).first()
        # Set created_at to 65 seconds ago
        from datetime import datetime, timezone, timedelta
        otp_record.created_at = datetime.now(timezone.utc) - timedelta(seconds=65)
        db.session.commit()
        db.session.close()

    # Now resending via API should work successfully
    api_resend2 = client.post('/api/v1/auth/resend-otp', json={
        'email': 'unverified@example.com'
    })
    assert api_resend2.status_code == 200
    assert b'sent to your email' in api_resend2.data

    # 6. Verify previous OTP was invalidated and new OTP generated
    with app.app_context():
        otp_record = UserOTP.query.filter_by(user_id=user.id).first()
        assert otp_record.otp_hash != initial_token_hash
        # Clean session cache
        db.session.close()

    # 7. Disallow verified users from requesting OTP resend
    # Verify the account manually first in database
    with app.app_context():
        u = User.query.filter_by(email='unverified@example.com').first()
        u.is_email_verified = True
        u.is_active = True
        db.session.commit()
        db.session.close()
        
    client.post('/auth/login', data={'email': 'unverified@example.com', 'password': 'Password123!'})
    
    # Disallow web resend for verified accounts
    resend_res_verified = client.post('/auth/resend-otp', follow_redirects=True)
    assert b'already verified' in resend_res_verified.data
    
    # Disallow API resend for verified accounts
    api_resend_verified = client.post('/api/v1/auth/resend-otp', json={
        'email': 'unverified@example.com'
    })
    assert api_resend_verified.status_code == 400
    assert b'already verified' in api_resend_verified.data

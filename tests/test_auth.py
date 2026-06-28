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

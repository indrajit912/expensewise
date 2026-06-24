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

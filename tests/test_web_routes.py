import pytest
import os
import io
from decimal import Decimal
from datetime import date
from app import db
from app.models.expense import Expense
from app.models.user import APIToken
from app.services.encryption_service import EncryptionService

def test_dashboard_index(client, test_user):
    """Tests loading the visual dashboard page."""
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'Password123!'})
    response = client.get('/dashboard')
    assert response.status_code == 200
    assert b'Financial Dashboard' in response.data


def test_dashboard_settings_and_tokens(client, app, test_user):
    """Tests profile viewing and generating/revoking API keys."""
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'Password123!'})
    
    # 1. View settings
    response = client.get('/settings')
    assert response.status_code == 200
    assert b'Account & Settings' in response.data
    
    # 2. Generate token (POST)
    gen_res = client.post('/settings', data={'action': 'generate_token'}, follow_redirects=True)
    assert gen_res.status_code == 200
    assert b'New API Token generated' in gen_res.data
    
    with app.app_context():
        token_obj = APIToken.query.filter_by(user_id=test_user.id).first()
        assert token_obj is not None
        token_str = token_obj.token
        
    # 3. Revoke token (POST)
    rev_res = client.post('/settings', data={'action': 'revoke_token', 'token': token_str}, follow_redirects=True)
    assert rev_res.status_code == 200
    assert b'API Token successfully revoked' in rev_res.data
    
    with app.app_context():
        token_check = APIToken.query.filter_by(token=token_str).first()
        assert token_check is None


def test_expense_list_filters_and_sorting(client, app, test_user):
    """Tests that registry table filters data elements according to query filters."""
    with app.app_context():
        # Set override key for encryption
        ukey = EncryptionService.get_user_key()
        if not ukey:
            EncryptionService.set_override_key(EncryptionService.generate_fernet_key())
            
        exp1 = Expense(user_id=test_user.id, amount=Decimal('20.00'), category='Food', expense_date=date(2026, 6, 20), payee='Dominos')
        exp2 = Expense(user_id=test_user.id, amount=Decimal('80.00'), category='Travel', expense_date=date(2026, 6, 21), payee='Uber')
        db.session.add_all([exp1, exp2])
        db.session.commit()
        
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'Password123!'})
    
    # Filter by category
    res_cat = client.get('/expenses/?category=Food')
    assert b'Dominos' in res_cat.data
    assert b'Uber' not in res_cat.data
    
    # Filter by search string
    res_search = client.get('/expenses/?search=Uber')
    assert b'Uber' in res_search.data
    assert b'Dominos' not in res_search.data
    
    # Filter by date range
    res_date = client.get('/expenses/?start_date=2026-06-21&end_date=2026-06-21')
    assert b'Uber' in res_date.data
    assert b'Dominos' not in res_date.data


def test_expenses_web_exports(client, test_user):
    """Tests the csv/json web download routes."""
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'Password123!'})
    
    # Export CSV
    csv_res = client.get('/expenses/export?format=csv')
    assert csv_res.status_code == 200
    assert csv_res.mimetype == 'text/csv'
    
    # Export JSON
    json_res = client.get('/expenses/export?format=json')
    assert json_res.status_code == 200
    assert json_res.mimetype == 'application/json'


def test_csv_upload_and_preview_flow(client, app, test_user):
    """Tests the staged file upload preview and staging confirm actions."""
    login_res = client.post('/auth/login', data={'email': 'test@example.com', 'password': 'Password123!'}, follow_redirects=True)
    assert b'Welcome back, Test User!' in login_res.data
    
    # Ensure GET /expenses/import is accessible
    get_res = client.get('/expenses/import')
    assert get_res.status_code == 200
    
    # Perform real CSV file upload post
    data = {
        'backup_file': (io.BytesIO(b"Amount,Category,Date,Description\n15.50,Food,2026-06-20,Burgers\n"), 'test.csv')
    }
    response = client.post('/expenses/import', data=data, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'CSV Staging Preview' in response.data
    assert b'Burgers' in response.data
    
    # Confirm staging load (POST confirm)
    confirm_res = client.post('/expenses/import/preview', data={'action': 'confirm'}, follow_redirects=True)
    assert confirm_res.status_code == 200
    assert b'Import completed successfully!' in confirm_res.data
    
    with app.app_context():
        expenses = Expense.query.filter_by(user_id=test_user.id).all()
        exp = None
        for e in expenses:
            if e.category == 'Food':
                exp = e
                break
        assert exp is not None
        assert float(exp.amount) == 15.50


def test_analytics_route(client, test_user):
    """Tests loading the visual analytics page."""
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'Password123!'})
    response = client.get('/analytics/')
    assert response.status_code == 200
    assert b'Analytics Engine' in response.data


def test_auth_reset_views(client, test_user):
    """Tests loading the password reset views."""
    # Reset request GET
    res_req_get = client.get('/auth/reset_password_request')
    assert res_req_get.status_code == 200
    assert b'Reset Password' in res_req_get.data
    
    # Reset request POST
    res_req_post = client.post('/auth/reset_password_request', data={'email': 'test@example.com'}, follow_redirects=True)
    assert res_req_post.status_code == 200
    assert b'An email has been sent with instructions' in res_req_post.data
    
    # Reset token verification page (GET)
    res_token_get = client.get(f'/auth/reset_password/{test_user.id}')
    assert res_token_get.status_code == 200
    assert b'New Password' in res_token_get.data
    
    # Reset token verification page (POST new password)
    res_token_post = client.post(f'/auth/reset_password/{test_user.id}', data={
        'password': 'NewPassword123!',
        'confirm_password': 'NewPassword123!'
    }, follow_redirects=True)
    assert res_token_post.status_code == 200
    assert b'Your password has been reset successfully' in res_token_post.data


def test_json_v2_upload_and_preview_flow(client, app, test_user):
    """Tests the staged v2.0 JSON file upload preview, validation checklist, and confirmation."""
    import json
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'Password123!'})
    
    backup_data = {
        "export_version": "2.0",
        "categories": [
            {"id": "e0b8e723-5e93-4c9f-bbd5-a332a683bb90", "name": "Food", "color": "#ff5500"}
        ],
        "payment_methods": [],
        "expenses": [
            {
                "id": "a90b6d21-fbb3-4ca2-8a9d-195b0ffea108",
                "amount": 12.50,
                "category_id": "e0b8e723-5e93-4c9f-bbd5-a332a683bb90",
                "expense_date": "2026-06-24",
                "description": "Coffee"
            }
        ]
    }
    
    # Upload JSON
    data = {
        'backup_file': (io.BytesIO(json.dumps(backup_data).encode('utf-8')), 'backup.json')
    }
    response = client.post('/expenses/import', data=data, follow_redirects=True)
    assert response.status_code == 200
    assert b'Backup Restore Preview' in response.data
    assert b'Backup Integrity Checklist' in response.data
    assert b'JSON Structure Check' in response.data
    assert b'Integrity Verified' in response.data
    
    # Confirm staging load
    confirm_res = client.post('/expenses/import/preview', data={'action': 'confirm'}, follow_redirects=True)
    assert confirm_res.status_code == 200
    assert b'Import completed successfully!' in confirm_res.data
    
    with app.app_context():
        # Setup override key
        from app.services.encryption_service import EncryptionService
        ukey = EncryptionService.get_user_key()
        if not ukey:
            EncryptionService.set_override_key(EncryptionService.generate_fernet_key())
            
        expenses = Expense.query.filter_by(user_id=test_user.id).all()
        assert len(expenses) == 1
        assert float(expenses[0].amount) == 12.50
        assert expenses[0].category == 'Food'


def test_json_v2_upload_invalid_preview(client, test_user):
    """Tests that uploading an invalid v2.0 JSON file fails checklist checks and disables confirmation."""
    import json
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'Password123!'})
    
    invalid_backup = {
        "export_version": "2.0",
        "categories": [
            {"id": "e0b8e723-5e93-4c9f-bbd5-a332a683bb90", "name": "Food", "color": "#ff5500"}
        ],
        "payment_methods": [],
        "expenses": [
            {
                "id": "a90b6d21-fbb3-4ca2-8a9d-195b0ffea108",
                "amount": 12.50,
                "category_id": "8c459be3-4e4f-4d37-8f5b-1ff2f0d922bb", # Invalid category_id reference
                "expense_date": "2026-06-24",
                "description": "Coffee"
            }
        ]
    }
    
    data = {
        'backup_file': (io.BytesIO(json.dumps(invalid_backup).encode('utf-8')), 'backup.json')
    }
    response = client.post('/expenses/import', data=data, follow_redirects=True)
    assert response.status_code == 200
    assert b'Backup Restore Preview' in response.data
    assert b'Restore Blocked' in response.data
    assert b'disabled' in response.data # The confirm button must be disabled

    # Try to force confirm POST request
    confirm_res = client.post('/expenses/import/preview', data={'action': 'confirm'}, follow_redirects=True)
    assert b'Import failed: Validation error' in confirm_res.data

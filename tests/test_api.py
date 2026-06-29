import pytest
import json
from decimal import Decimal
from datetime import date
from unittest.mock import patch
from app import db
from app.models.expense import Expense


def test_schemas_import_successfully():
    """Schemas should import cleanly with the installed Marshmallow extensions."""
    from app.api.schemas import UserSchema, ExpenseSchema

    assert UserSchema is not None
    assert ExpenseSchema is not None


def test_api_auth_register(client):
    """Tests registering an account via the REST API endpoint."""
    with patch('random.randint', return_value=123456):
        response = client.post('/api/v1/auth/register', json={
            'name': 'API Bob',
            'username': 'apibob',
            'email': 'apibob@example.com',
            'password': 'Password123!'
        })
    
    assert response.status_code == 201
    data = response.get_json()
    assert 'OTP has been sent' in data['message']
    assert data['user']['email'] == 'apibob@example.com'
    user_id = data['user_id']
    
    # Verify OTP
    verify_res = client.post('/api/v1/auth/verify-otp', json={
        'user_id': user_id,
        'otp': '123456'
    })
    assert verify_res.status_code == 200
    assert 'activated successfully' in verify_res.get_json()['message']


def test_api_auth_login_logout(client, test_user):
    """Tests fetching an API auth key and revoking it via endpoints."""
    # Test Login
    response = client.post('/api/v1/auth/login', json={
        'email': 'test@example.com',
        'password': 'Password123!'
    })
    
    assert response.status_code == 200
    data = response.get_json()
    assert 'token' in data
    assert data['token_type'] == 'Bearer'
    token = data['token']
    
    # Test Logout (revokes key)
    logout_res = client.post('/api/v1/auth/logout', headers={
        'Authorization': f"Bearer {token}"
    })
    assert logout_res.status_code == 200
    assert b'Logged out successfully' in logout_res.data


def test_api_unauthorized_access(client):
    """Tests that accessing endpoints without a valid API key yields 401."""
    response = client.get('/api/v1/expenses')
    assert response.status_code == 401
    
    response_bad = client.get('/api/v1/expenses', headers={
        'Authorization': 'Bearer bad_token_xyz'
    })
    assert response_bad.status_code == 401


def test_api_expense_crud(client, app, test_user, api_headers):
    """Tests CRUD operations over the API endpoints."""
    # 1. Create Expense (POST)
    response = client.post('/api/v1/expenses', json={
        'amount': '33.33',
        'category': 'Shopping',
        'expense_date': '2026-06-22',
        'payee': 'Amazon',
        'payment_mode': 'Card',
        'description': 'Office supplies'
    }, headers=api_headers)
    
    assert response.status_code == 201
    data = response.get_json()
    assert data['amount'] == '33.33'
    assert data['category'] == 'Shopping'
    exp_uuid = data['id']
    
    # 2. Retrieve Expense (GET)
    get_res = client.get(f'/api/v1/expenses/{exp_uuid}', headers=api_headers)
    assert get_res.status_code == 200
    assert get_res.get_json()['payee'] == 'Amazon'
    
    # 3. Update Expense (PUT)
    put_res = client.put(f'/api/v1/expenses/{exp_uuid}', json={
        'amount': '35.00',
        'description': 'Updated office supplies'
    }, headers=api_headers)
    
    assert put_res.status_code == 200
    assert put_res.get_json()['amount'] == '35.00'
    assert put_res.get_json()['description'] == 'Updated office supplies'
    
    # 4. Delete Expense (DELETE)
    del_res = client.delete(f'/api/v1/expenses/{exp_uuid}', headers=api_headers)
    assert del_res.status_code == 200
    assert b'deleted successfully' in del_res.data


def test_api_analytics(client, app, test_user, api_headers):
    """Tests that analytics API endpoints serve aggregated metrics and forecasts."""
    # Write a test expense first
    with app.app_context():
        # Set user key override because we are running in DB context outside login session
        from app.services.encryption_service import EncryptionService
        # Find token in headers
        token = api_headers['Authorization'].split()[1]
        ukey = EncryptionService.get_user_key()
        if not ukey:
            # Generate a key and override
            ukey = EncryptionService.generate_fernet_key()
            EncryptionService.set_override_key(ukey)
            
        exp = Expense(
            user_id=test_user.id,
            amount=Decimal('400.00'),
            category='Rent',
            expense_date=date.today()
        )
        db.session.add(exp)
        db.session.commit()
        
    # Test summary metrics endpoint
    sum_res = client.get('/api/v1/analytics/summary', headers=api_headers)
    assert sum_res.status_code == 200
    sum_data = sum_res.get_json()
    assert sum_data['metrics']['total_spending'] == 400.0
    
    # Test trends endpoint
    trend_res = client.get('/api/v1/analytics/trends', headers=api_headers)
    assert trend_res.status_code == 200
    trend_data = trend_res.get_json()
    assert 'Rent' in trend_data['category_distribution']
    
    # Test forecast endpoint
    fore_res = client.get('/api/v1/analytics/forecast', headers=api_headers)
    assert fore_res.status_code == 200
    assert 'predicted_next_month_spending' in fore_res.get_json()

    # Test trends-over-time endpoint
    tot_res = client.get('/api/v1/analytics/trends-over-time?interval=month&moving_average_window=3', headers=api_headers)
    assert tot_res.status_code == 200
    tot_data = tot_res.get_json()
    assert 'labels' in tot_data
    assert 'totals' in tot_data
    assert 'moving_average' in tot_data
    assert len(tot_data['totals']) > 0

    tot_daily = client.get('/api/v1/analytics/trends-over-time?interval=day', headers=api_headers)
    assert tot_daily.status_code == 200

    # Test category breakdown endpoint
    cbd_res = client.get('/api/v1/analytics/category-breakdown', headers=api_headers)
    assert cbd_res.status_code == 200
    cbd_data = cbd_res.get_json()
    assert 'breakdown' in cbd_data
    assert len(cbd_data['breakdown']) > 0
    assert cbd_data['breakdown'][0]['category'] == 'Rent'
    assert cbd_data['breakdown'][0]['total_amount'] == 400.0
    assert cbd_data['breakdown'][0]['percentage'] == 100.0
    assert cbd_data['breakdown'][0]['transaction_count'] == 1

    # Test spending patterns endpoint
    spp_res = client.get('/api/v1/analytics/spending-patterns', headers=api_headers)
    assert spp_res.status_code == 200
    spp_data = spp_res.get_json()
    assert 'patterns' in spp_data
    assert 'day_of_week' in spp_data['patterns']
    assert 'time_of_month' in spp_data['patterns']
    assert 'insights' in spp_data['patterns']


def test_api_categories_and_payment_methods_crud(client, app, test_user, api_headers):
    """Tests categories and payment methods API endpoints and validation constraints."""
    
    # 1. Fetch categories
    res = client.get('/api/v1/categories', headers=api_headers)
    assert res.status_code == 200
    cats = res.get_json()
    assert len(cats) > 0
    # Find Rent category ID
    rent_id = next(c['id'] for c in cats if c['name'] == 'Rent')
    
    # 2. Add custom category
    res_add = client.post('/api/v1/categories', json={'name': 'Hobbies', 'color': '#1d4ed8'}, headers=api_headers)
    assert res_add.status_code == 201
    hobbies_cat = res_add.get_json()
    assert hobbies_cat['name'] == 'Hobbies'
    assert hobbies_cat['color'] == '#1d4ed8'
    hobbies_id = hobbies_cat['id']
    
    # 3. Rename custom category
    res_up = client.put(f'/api/v1/categories/{hobbies_id}', json={'name': 'Games', 'color': '#0ea5e9'}, headers=api_headers)
    assert res_up.status_code == 200
    assert res_up.get_json()['name'] == 'Games'
    assert res_up.get_json()['color'] == '#0ea5e9'
    
    # 4. Try to delete category 'Rent' with associated expense
    with app.app_context():
        # Set override key for encryption
        from app.services.encryption_service import EncryptionService
        ukey = EncryptionService.get_user_key()
        if not ukey:
            ukey = EncryptionService.generate_fernet_key()
            EncryptionService.set_override_key(ukey)
        from app.models.expense import Expense
        db_exp = Expense(user_id=test_user.id, amount=Decimal('50.00'), category='Rent', expense_date=date.today())
        db.session.add(db_exp)
        db.session.commit()
        
    res_del_rent = client.delete(f'/api/v1/categories/{rent_id}', headers=api_headers)
    assert res_del_rent.status_code == 400
    assert b'Cannot delete category' in res_del_rent.data
    
    # 5. Delete the custom 'Games' category (no expenses associated)
    res_del_games = client.delete(f'/api/v1/categories/{hobbies_id}', headers=api_headers)
    assert res_del_games.status_code == 200
    
    # 6. Fetch payment methods
    pm_res = client.get('/api/v1/payment-methods', headers=api_headers)
    assert pm_res.status_code == 200
    pms = pm_res.get_json()
    assert len(pms) > 0
    cash_id = next(p['id'] for p in pms if p['name'] == 'Cash')
    
    # 7. Add custom payment method
    pm_add = client.post('/api/v1/payment-methods', json={'name': 'Crypto', 'color': '#14b8a6'}, headers=api_headers)
    assert pm_add.status_code == 201
    crypto_pm = pm_add.get_json()
    assert crypto_pm['color'] == '#14b8a6'
    crypto_id = crypto_pm['id']
    
    # 8. Rename custom payment method
    pm_up = client.put(f'/api/v1/payment-methods/{crypto_id}', json={'name': 'Bitcoin', 'color': '#64748b'}, headers=api_headers)
    assert pm_up.status_code == 200
    assert pm_up.get_json()['name'] == 'Bitcoin'
    assert pm_up.get_json()['color'] == '#64748b'
    
    # 9. Try to delete 'Cash' payment method after associating it with an expense
    with app.app_context():
        # Set override key for encryption
        from app.services.encryption_service import EncryptionService
        ukey = EncryptionService.get_user_key()
        if not ukey:
            ukey = EncryptionService.generate_fernet_key()
            EncryptionService.set_override_key(ukey)
        from app.models.expense import Expense
        db_exp2 = Expense(user_id=test_user.id, amount=Decimal('10.00'), category='Food', expense_date=date.today(), payment_mode='Cash')
        db.session.add(db_exp2)
        db.session.commit()
        
    pm_del_cash = client.delete(f'/api/v1/payment-methods/{cash_id}', headers=api_headers)
    assert pm_del_cash.status_code == 400
    assert b'Cannot delete payment method' in pm_del_cash.data
    
    # 10. Delete 'Bitcoin' (no expenses associated)
    pm_del_btc = client.delete(f'/api/v1/payment-methods/{crypto_id}', headers=api_headers)
    assert pm_del_btc.status_code == 200


def test_api_profile_me(client, test_user, api_headers):
    """Tests fetching current user details via GET /api/v1/auth/me."""
    res = client.get('/api/v1/auth/me', headers=api_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data['email'] == test_user.email
    assert data['username'] == test_user.username
    assert 'id' in data


def test_api_change_password(client, app, test_user, api_headers):
    """Tests password updating through the API."""
    res = client.post('/api/v1/auth/change-password', json={
        'current_password': 'Password123!',
        'new_password': 'NewPassword123!'
    }, headers=api_headers)
    assert res.status_code == 200
    assert b'changed successfully' in res.data

    # Verify that we can log in with the new password
    login_res = client.post('/api/v1/auth/login', json={
        'email': test_user.email,
        'password': 'NewPassword123!'
    })
    assert login_res.status_code == 200


def test_api_budget_management(client, app, test_user, api_headers):
    """Tests budget CRUD operations via API."""
    # 1. Fetch suggestions and budget comparison list
    res = client.get('/api/v1/budget?month=2026-07', headers=api_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data['month'] == '2026-07'
    assert 'categories' in data

    # 2. Save budget limits
    save_res = client.post('/api/v1/budget', json={
        'month': '2026-07',
        'budgets': {
            'Food': 4000.00,
            'Shopping': 2500.00
        }
    }, headers=api_headers)
    assert save_res.status_code == 200

    # 3. Assert databases are updated
    with app.app_context():
        from app.models.expense import Budget
        b_food = Budget.query.filter_by(user_id=test_user.id, month='2026-07', category_name='Food').first()
        assert b_food is not None
        assert float(b_food.amount) == 4000.00

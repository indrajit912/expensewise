import pytest
import io
import json
from datetime import date
from decimal import Decimal
from app import db
from app.models.expense import Expense
from app.services.import_service import ImportService
from app.services.export_service import ExportService
from app.services.encryption_service import EncryptionService

def test_add_expense(client, app, test_user):
    """Tests writing a new expense record."""
    # Login user session
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'Password123!'})
    
    response = client.post('/expenses/add', data={
        'amount': '45.50',
        'currency': 'USD',
        'conversion_rate': '1.0',
        'category': 'Food',
        'expense_date': '2026-06-24',
        'payee': 'Starbucks',
        'payment_mode': 'Card',
        'description': 'Coffee meeting'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Expense recorded successfully.' in response.data
    
    with app.app_context():
        # Set override key for decryption in test db session
        ukey = EncryptionService.get_user_key()
        if not ukey:
            EncryptionService.set_override_key(EncryptionService.generate_fernet_key())
        exp = Expense.query.filter_by(user_id=test_user.id).first()
        assert exp is not None
        assert float(exp.amount) == 45.50
        assert exp.category == 'Food'
        assert exp.payee == 'Starbucks'


def test_edit_expense(client, app, test_user):
    """Tests updating an existing expense."""
    with app.app_context():
        # Set override key
        ukey = EncryptionService.get_user_key()
        if not ukey:
            EncryptionService.set_override_key(EncryptionService.generate_fernet_key())
        exp = Expense(
            user_id=test_user.id,
            amount=Decimal('100.00'),
            category='Utilities',
            expense_date=date(2026, 6, 1)
        )
        db.session.add(exp)
        db.session.commit()
        exp_id = exp.id
        
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'Password123!'})
    
    response = client.post(f'/expenses/edit/{exp_id}', data={
        'amount': '120.00',
        'currency': 'USD',
        'conversion_rate': '1.0',
        'category': 'Utilities',
        'expense_date': '2026-06-01',
        'payee': 'Electric Co',
        'payment_mode': 'NetBanking',
        'description': 'Updated electricity bill'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Expense updated successfully.' in response.data
    
    with app.app_context():
        updated = Expense.query.get(exp_id)
        assert float(updated.amount) == 120.00
        assert updated.payee == 'Electric Co'
        assert updated.description == 'Updated electricity bill'


def test_delete_expense(client, app, test_user):
    """Tests deleting an expense record."""
    with app.app_context():
        ukey = EncryptionService.get_user_key()
        if not ukey:
            EncryptionService.set_override_key(EncryptionService.generate_fernet_key())
        exp = Expense(
            user_id=test_user.id,
            amount=Decimal('50.00'),
            category='Shopping',
            expense_date=date(2026, 6, 2)
        )
        db.session.add(exp)
        db.session.commit()
        exp_id = exp.id
        
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'Password123!'})
    
    response = client.post(f'/expenses/delete/{exp_id}', follow_redirects=True)
    assert response.status_code == 200
    assert b'Expense deleted successfully.' in response.data
    
    with app.app_context():
        deleted = Expense.query.get(exp_id)
        assert deleted is None


def test_legacy_json_import(app, test_user):
    """Tests the legacy CLI database.json import parser, validation, mapping and duplicates."""
    legacy_data = {
        "expenses": {
            "Sep 11, 2022": [
                {
                    "amount": 516.15,
                    "category": "Toiletries",
                    "mode": "Phonepe",
                    "payee": "Star Bazzar",
                    "date": "Sep 11, 2022",
                    "message": "Engage Body Spray"
                },
                {
                    "amount": 10.0,
                    "category": "Travel",
                    "mode": "Cash",
                    "payee": "BMTC",
                    "date": "Sep 11, 2022",
                    "message": "Bus to Arcade Mall"
                }
            ]
        }
    }
    
    with app.app_context():
        ukey = EncryptionService.get_user_key()
        if not ukey:
            EncryptionService.set_override_key(EncryptionService.generate_fernet_key())
        result = ImportService.import_legacy_json(test_user.id, legacy_data)
        
        assert result['success'] is True
        assert result['success_count'] == 2
        assert result['duplicate_count'] == 0
        assert result['error_count'] == 0
        
        # Test duplicate check by re-importing the same payload
        result_dup = ImportService.import_legacy_json(test_user.id, legacy_data)
        assert result_dup['success'] is True
        assert result_dup['success_count'] == 0
        assert result_dup['duplicate_count'] == 2



def test_standard_json_import(app, test_user):
    """Tests standard JSON backup import rebuilding the user's dataset."""
    # First, seed an expense
    with app.app_context():
        ukey = EncryptionService.get_user_key()
        if not ukey:
            EncryptionService.set_override_key(EncryptionService.generate_fernet_key())
        exp = Expense(
            user_id=test_user.id,
            amount=Decimal('99.99'),
            category='Rent',
            expense_date=date(2026, 6, 24)
        )
        db.session.add(exp)
        db.session.commit()
        assert Expense.query.filter_by(user_id=test_user.id).count() == 1

    # Standard JSON export format content
    standard_json_content = [
        {
            "amount": 10.50,
            "category": "Food",
            "payee": "Starbucks",
            "payment_mode": "Card",
            "expense_date": "2026-06-25",
            "description": "Coffee",
            "original_amount": 10.50,
            "original_currency": "USD",
            "conversion_rate": 1.0,
            "converted_amount": 10.50
        },
        {
            "amount": 25.00,
            "category": "Travel",
            "payee": "Uber",
            "payment_mode": "Cash",
            "expense_date": "2026-06-26",
            "description": "Ride home",
            "original_amount": 25.00,
            "original_currency": "USD",
            "conversion_rate": 1.0,
            "converted_amount": 25.00
        }
    ]

    with app.app_context():
        result = ImportService.import_standard_json(test_user.id, json.dumps(standard_json_content))
        assert result['success'] is True
        assert result['success_count'] == 2
        assert result['duplicate_count'] == 0
        
        # Verify that the seeded expense of 99.99 is deleted, and only the 2 imported expenses exist
        expenses = Expense.query.filter_by(user_id=test_user.id).all()
        assert len(expenses) == 2
        amounts = [float(e.amount) for e in expenses]
        assert 99.99 not in amounts
        assert 10.50 in amounts
        assert 25.00 in amounts


def test_v2_json_import_valid(app, test_user):
    """Tests importing a valid v2.0 JSON backup with categories, payment methods, and expenses."""
    from app.models.expense import Category, PaymentMethod, Expense
    from app.models.user import User
    
    backup_data = {
        "export_version": "2.0",
        "created_at": "2026-06-24T20:33:00Z",
        "user_preferences": {
            "default_currency": "EUR"
        },
        "categories": [
            {
                "id": "e0b8e723-5e93-4c9f-bbd5-a332a683bb90",
                "name": "Food & Drinks",
                "color": "#ff5500",
                "created_at": "2026-06-24T14:29:09Z"
            }
        ],
        "payment_methods": [
            {
                "id": "c1f7a14e-e19c-4ebc-8822-6b998248c8b4",
                "name": "Digital Wallet",
                "color": "#11aa22",
                "created_at": "2026-06-24T14:29:09Z"
            }
        ],
        "expenses": [
            {
                "id": "a90b6d21-fbb3-4ca2-8a9d-195b0ffea108",
                "amount": 75.50,
                "category_id": "e0b8e723-5e93-4c9f-bbd5-a332a683bb90",
                "payment_method_id": "c1f7a14e-e19c-4ebc-8822-6b998248c8b4",
                "expense_date": "2026-06-24",
                "description": "Lunch meeting",
                "payee": "Bistro",
                "original_amount": 75.50,
                "original_currency": "EUR",
                "conversion_rate": 1.0,
                "converted_amount": 75.50,
                "created_at": "2026-06-24T14:29:09Z"
            }
        ]
    }

    with app.app_context():
        # Setup override key for encryption
        ukey = EncryptionService.get_user_key()
        if not ukey:
            EncryptionService.set_override_key(EncryptionService.generate_fernet_key())

        result = ImportService.import_standard_json(test_user.id, json.dumps(backup_data))
        assert result['success'] is True
        assert result['success_count'] == 1
        
        # Verify default currency updated
        user_reloaded = User.query.get(test_user.id)
        assert user_reloaded.default_currency == "EUR"
        
        # Verify Category details (Option B UUID mapping check)
        cat = Category.query.filter_by(user_id=test_user.id, name="Food & Drinks").first()
        assert cat is not None
        assert cat.color == "#ff5500"
        assert cat.id != "e0b8e723-5e93-4c9f-bbd5-a332a683bb90" # Must be generated new ID (Option B)
        
        # Verify Payment Method details
        pm = PaymentMethod.query.filter_by(user_id=test_user.id, name="Digital Wallet").first()
        assert pm is not None
        assert pm.color == "#11aa22"
        assert pm.id != "c1f7a14e-e19c-4ebc-8822-6b998248c8b4" # Must be generated new ID (Option B)
        
        # Verify Expense
        exp = Expense.query.filter_by(user_id=test_user.id).first()
        assert exp is not None
        assert float(exp.amount) == 75.50
        assert exp.category == "Food & Drinks"
        assert exp.payment_mode == "Digital Wallet"
        assert exp.id != "a90b6d21-fbb3-4ca2-8a9d-195b0ffea108" # Must be generated new ID (Option B)
        assert exp.user_id == test_user.id # Ownership verified


def test_v2_json_import_invalid_schema(app, test_user):
    """Tests various validation checklist failures for version 2.0 JSON schema."""
    with app.app_context():
        ukey = EncryptionService.get_user_key()
        if not ukey:
            EncryptionService.set_override_key(EncryptionService.generate_fernet_key())

        # Test Case 1: Bad Export Version
        bad_version = {"export_version": "3.0", "categories": [], "payment_methods": [], "expenses": []}
        res1 = ImportService.import_standard_json(test_user.id, json.dumps(bad_version))
        assert res1['success'] is False
        assert "Unsupported export version" in res1['error']
        
        # Test Case 2: Missing Section
        missing_section = {"export_version": "2.0", "categories": [], "expenses": []}
        res2 = ImportService.import_standard_json(test_user.id, json.dumps(missing_section))
        assert res2['success'] is False
        assert "Missing or invalid" in res2['error']
        
        # Test Case 3: Invalid UUID Format
        bad_uuid = {
            "export_version": "2.0",
            "categories": [{"id": "bad-uuid-123", "name": "Food", "color": "#ff5500"}],
            "payment_methods": [],
            "expenses": []
        }
        res3 = ImportService.import_standard_json(test_user.id, json.dumps(bad_uuid))
        assert res3['success'] is False
        assert "has invalid UUID" in res3['error']
        
        # Test Case 4: Category reference error
        missing_cat_ref = {
            "export_version": "2.0",
            "categories": [{"id": "e0b8e723-5e93-4c9f-bbd5-a332a683bb90", "name": "Food", "color": "#ff5500"}],
            "payment_methods": [],
            "expenses": [
                {
                    "id": "a90b6d21-fbb3-4ca2-8a9d-195b0ffea108",
                    "amount": 20.0,
                    "category_id": "8c459be3-4e4f-4d37-8f5b-1ff2f0d922bb", # Non-existent cat ID
                    "expense_date": "2026-06-24"
                }
            ]
        }
        res4 = ImportService.import_standard_json(test_user.id, json.dumps(missing_cat_ref))
        assert res4['success'] is False
        assert "references non-existent category_id" in res4['error']
        
        # Test Case 5: Payment method reference error
        missing_pm_ref = {
            "export_version": "2.0",
            "categories": [{"id": "e0b8e723-5e93-4c9f-bbd5-a332a683bb90", "name": "Food", "color": "#ff5500"}],
            "payment_methods": [{"id": "c1f7a14e-e19c-4ebc-8822-6b998248c8b4", "name": "Cash", "color": "#000000"}],
            "expenses": [
                {
                    "id": "a90b6d21-fbb3-4ca2-8a9d-195b0ffea108",
                    "amount": 20.0,
                    "category_id": "e0b8e723-5e93-4c9f-bbd5-a332a683bb90",
                    "payment_method_id": "8c459be3-4e4f-4d37-8f5b-1ff2f0d922bb", # Non-existent pm ID
                    "expense_date": "2026-06-24"
                }
            ]
        }
        res5 = ImportService.import_standard_json(test_user.id, json.dumps(missing_pm_ref))
        assert res5['success'] is False
        assert "references non-existent payment_method_id" in res5['error']

        # Test Case 6: Invalid Expense Amount
        bad_amount = {
            "export_version": "2.0",
            "categories": [{"id": "e0b8e723-5e93-4c9f-bbd5-a332a683bb90", "name": "Food", "color": "#ff5500"}],
            "payment_methods": [],
            "expenses": [
                {
                    "id": "a90b6d21-fbb3-4ca2-8a9d-195b0ffea108",
                    "amount": -5.0, # Negative amount
                    "category_id": "e0b8e723-5e93-4c9f-bbd5-a332a683bb90",
                    "expense_date": "2026-06-24"
                }
            ]
        }
        res6 = ImportService.import_standard_json(test_user.id, json.dumps(bad_amount))
        assert res6['success'] is False
        assert "has non-positive amount" in res6['error']


def test_v2_json_import_duplicate_merging(app, test_user):
    """Tests merging categories and payment methods by name during v2.0 import (updating colors to match backup)."""
    from app.models.expense import Category, PaymentMethod
    
    with app.app_context():
        ukey = EncryptionService.get_user_key()
        if not ukey:
            EncryptionService.set_override_key(EncryptionService.generate_fernet_key())

        # Look up existing seeded 'Food' and 'Card' and modify their colors first
        seeded_cat = Category.query.filter_by(user_id=test_user.id, name="Food").first()
        seeded_pm = PaymentMethod.query.filter_by(user_id=test_user.id, name="Card").first()
        
        seeded_cat.color = "#111111"
        seeded_pm.color = "#222222"
        db.session.commit()
        
        seeded_cat_id = seeded_cat.id
        seeded_pm_id = seeded_pm.id
        
        backup_data = {
            "export_version": "2.0",
            "categories": [{"id": "e0b8e723-5e93-4c9f-bbd5-a332a683bb90", "name": "Food", "color": "#ff5500"}],
            "payment_methods": [{"id": "c1f7a14e-e19c-4ebc-8822-6b998248c8b4", "name": "Card", "color": "#11aa22"}],
            "expenses": []
        }
        
        result = ImportService.import_standard_json(test_user.id, json.dumps(backup_data))
        assert result['success'] is True
        
        # Verify color updated, but ID preserved
        cat = Category.query.filter_by(user_id=test_user.id, name="Food").first()
        assert cat.color == "#ff5500"
        assert cat.id == seeded_cat_id
        
        pm = PaymentMethod.query.filter_by(user_id=test_user.id, name="Card").first()
        assert pm.color == "#11aa22"
        assert pm.id == seeded_pm_id


def test_v2_json_import_empty_export(app, test_user):
    """Tests importing an empty but valid v2.0 JSON backup clears existing expenses."""
    from app.models.expense import Expense
    
    with app.app_context():
        ukey = EncryptionService.get_user_key()
        if not ukey:
            EncryptionService.set_override_key(EncryptionService.generate_fernet_key())

        # Seed an expense
        db.session.add(Expense(user_id=test_user.id, amount=Decimal('50.00'), category='Food', expense_date=date(2026, 6, 24)))
        db.session.commit()
        assert Expense.query.filter_by(user_id=test_user.id).count() == 1
        
        empty_backup = {
            "export_version": "2.0",
            "categories": [],
            "payment_methods": [],
            "expenses": []
        }
        
        result = ImportService.import_standard_json(test_user.id, json.dumps(empty_backup))
        assert result['success'] is True
        assert result['success_count'] == 0
        
        # Verify database is cleared of user's expenses
        assert Expense.query.filter_by(user_id=test_user.id).count() == 0


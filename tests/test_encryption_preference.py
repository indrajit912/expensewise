import pytest
from app import db
from app.models.user import User
from app.models.expense import Expense
from app.services.encryption_service import EncryptionService

def test_encryption_toggling_and_migration(app, client):
    """Verifies that a user can toggle encryption ON/OFF, and records migrate successfully without data loss."""
    with app.app_context():
        # 1. Register a new user with encryption enabled (default)
        user = User(
            name="Crypto User",
            username="cryptouser",
            email="crypto@example.com",
            encryption_enabled=True
        )
        user.set_password("Password123!")
        db.session.add(user)
        db.session.commit()
        
        # 2. Add an expense while encryption is enabled
        fernet_key = EncryptionService.decrypt_fernet_key(
            user.server_encrypted_fernet_key,
            EncryptionService.get_server_master_key()
        )
        EncryptionService.set_override_key(fernet_key)
        
        expense = Expense(
            user_id=user.id,
            amount="100.50",
            category="Dining",
            description="Nice dinner",
            payee="Restaurant",
            payment_mode="Card",
            expense_date="2026-06-29"
        )
        db.session.add(expense)
        db.session.commit()
        
        # Verify it was stored encrypted in the database columns
        assert expense.category_enc != "Dining"
        assert expense.description_enc != "Nice dinner"
        
        # Verify property read returns decrypted data
        assert expense.category == "Dining"
        assert expense.description == "Nice dinner"
        assert float(expense.amount) == 100.50

        # 3. Toggle encryption to DISABLED
        # This triggers migrate_user_encryption
        EncryptionService.migrate_user_encryption(user, False)
        user.encryption_enabled = False
        db.session.commit()

        # Reload expense from DB
        db.session.refresh(expense)

        # Verify details are now stored as plaintext in the database columns
        assert expense.category_enc == "Dining"
        assert expense.description_enc == "Nice dinner"

        # Verify property read still returns correct data
        assert expense.category == "Dining"
        assert expense.description == "Nice dinner"
        assert float(expense.amount) == 100.50

        # 4. Toggle encryption back to ENABLED
        EncryptionService.migrate_user_encryption(user, True)
        user.encryption_enabled = True
        db.session.commit()

        # Reload expense from DB
        db.session.refresh(expense)

        # Verify details are stored encrypted again in the database columns
        assert expense.category_enc != "Dining"
        assert expense.description_enc != "Nice dinner"

        # Verify property read is correct
        assert expense.category == "Dining"
        assert expense.description == "Nice dinner"
        assert float(expense.amount) == 100.50

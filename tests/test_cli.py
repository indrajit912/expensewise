import os
import io
import json
import pytest
from unittest.mock import patch
from app.models.user import User
from app.models.expense import Expense
from app.services.encryption_service import EncryptionService
from app.extensions import db

def test_create_admin_cli(app):
    """Tests the flask create-admin CLI command execution."""
    runner = app.test_cli_runner()
    
    # Simulate first admin creation via CLI prompts: Name, Username, Email, Password, Confirmation
    result = runner.invoke(
        args=['create-admin'],
        input="Indrajit Ghosh\nghostrix\nindrajitghosh912@gmail.com\nUSD\nPassword123!\nPassword123!\n"
    )
    
    assert result.exit_code == 0
    assert "created successfully" in result.output
    
    with app.app_context():
        user = User.query.filter_by(username='ghostrix').first()
        assert user is not None
        assert user.is_admin is True
        assert user.is_super_admin is True
        assert user.is_active is True


def test_create_admin_cli_already_exists(app, test_user):
    """Tests that create-admin refuses to run if an administrator already exists."""
    # Mark the test user as an admin
    with app.app_context():
        user = User.query.filter_by(email=test_user.email).first()
        user.is_admin = True
        db.session.commit()
        
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=['create-admin'],
        input="Indrajit Ghosh\nghostrix\nindrajitghosh912@gmail.com\nPassword123!\nPassword123!\n"
    )
    
    assert "Error: An administrator already exists" in result.output


def test_bootstrap_system_cli(app, tmp_path):
    """Tests the flask bootstrap-system CLI command legacy JSON import."""
    # Prepare dummy legacy database.json file content
    legacy_data = {
        "expenses": {
            "Sep 11, 2022": [
                {
                    "amount": 500.0,
                    "category": "Rent",
                    "mode": "Cash",
                    "payee": "Landlord",
                    "date": "Sep 11, 2022",
                    "message": "September rent"
                }
            ]
        }
    }
    
    # Write to a temporary file
    temp_json = tmp_path / "database.json"
    with open(temp_json, "w", encoding="utf-8") as f:
        json.dump(legacy_data, f)
        
    runner = app.test_cli_runner()
    
    # Patch the hardcoded path in app.cli.__init__ with the temp file path
    with patch('app.cli.os.path.exists', return_value=True), \
         patch('app.cli.open', lambda filepath, *args, **kwargs: open(temp_json, *args, **kwargs)):
        
        # Simulate prompts: Password, Confirmation
        result = runner.invoke(
            args=['bootstrap-system'],
            input="Password123!\nPassword123!\n"
        )
        
        assert result.exit_code == 0
        assert "System bootstrap complete" in result.output
        
    with app.app_context():
        user = User.query.filter_by(username='ghostrix').first()
        assert user is not None
        assert user.is_super_admin is True
        
        # Derive key from the user's password to decrypt data in test environment
        derived = EncryptionService.derive_key("Password123!", user.kdf_salt)
        ukey = EncryptionService.decrypt_fernet_key(user.encrypted_fernet_key, derived)
        EncryptionService.set_override_key(ukey)
            
        expenses = Expense.query.filter_by(user_id=user.id).all()
        assert len(expenses) == 1
        assert float(expenses[0].amount) == 500.0
        assert expenses[0].category == 'Rent'


def test_create_guest_cli(app):
    """Tests the flask create-guest CLI command execution."""
    runner = app.test_cli_runner()
    
    # Run the command to create the guest user
    result = runner.invoke(args=['create-guest'])
    
    assert result.exit_code == 0
    assert "created successfully" in result.output
    
    with app.app_context():
        guest = User.query.filter_by(username='guest').first()
        assert guest is not None
        assert guest.is_admin is False
        assert guest.is_active is True
        assert guest.email == 'guest@expensewise.local'

    # Run the command again to test existing guest path
    result_repeat = runner.invoke(args=['create-guest'])
    assert result_repeat.exit_code == 0
    assert "already exists. Re-setting password to 'password'" in result_repeat.output


def test_setup_project_cli_abort(app):
    """Tests that flask setup-project CLI aborts when confirmation is declined."""
    runner = app.test_cli_runner()
    
    # Input 'n' to decline confirmation
    result = runner.invoke(args=['setup-project'], input="n\n")
    assert "Setup aborted by user" in result.output
    assert result.exit_code == 0


def test_setup_project_cli_success(app):
    """Tests successful execution flow of flask setup-project CLI command using mocks."""
    runner = app.test_cli_runner()
    
    with patch('app.cli.shutil.rmtree') as mock_rmtree, \
         patch('app.cli.os.path.exists', return_value=True), \
         patch('app.cli.subprocess.run') as mock_run:
        
        # Mock subprocess.run to return a success code
        class MockCompletedProcess:
            returncode = 0
        mock_run.return_value = MockCompletedProcess()
        
        # Input 'y' to confirm
        result = runner.invoke(args=['setup-project'], input="y\n")
        
        assert result.exit_code == 0
        assert "WARNING: This command will permanently delete" in result.output
        assert "Deleted instance directory successfully." in result.output
        assert "Deleted migrations directory successfully." in result.output
        assert "Project has been initialized and set up successfully!" in result.output
        
        # Check that rmtree was called on instance and migrations paths
        assert mock_rmtree.call_count == 2
        
        # Check that subprocess.run was called for the 5 setup steps
        assert mock_run.call_count == 5

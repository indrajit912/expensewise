import pytest
from datetime import datetime, timezone
from app import create_app, db
from app.models.user import User, APIToken
from app.models.expense import Expense

@pytest.fixture
def app():
    """Initializes the Flask app with TestingConfig."""
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    """Provides a Flask test client."""
    return app.test_client()

@pytest.fixture
def test_user(app):
    """Provides a pre-created test user in the database."""
    user = User(
        name="Test User",
        username="testuser",
        email="test@example.com",
        is_active=True,
        is_email_verified=True
    )
    user.set_password("Password123!")
    db.session.add(user)
    db.session.commit()
    user.seed_defaults()
    return user

@pytest.fixture
def api_headers(app, test_user):
    """Provides authorization headers containing a valid API Token."""
    token = test_user.generate_token(expires_in_days=1)
    return {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

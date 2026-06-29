import pytest
from unittest.mock import patch
from app import db
from app.models.user import User, AuditLog
from app.services.email_service import EmailService

def test_support_page_access_and_validation(client, test_user):
    """Tests that unauthenticated users are blocked and validation triggers for empty submissions."""
    # 1. Unauthenticated access should redirect to login
    response = client.get('/support')
    assert response.status_code == 302
    assert '/auth/login' in response.headers['Location']

    # 2. Log in the test user
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'Password123!'})
    
    # 3. Authenticated access should return 200
    response = client.get('/support')
    assert response.status_code == 200
    assert b'Contact Support' in response.data

    # 4. Try submitting an empty message
    response = client.post('/support', data={'message': ''}, follow_redirects=True)
    assert response.status_code == 200
    assert b'Message content cannot be empty.' in response.data or b'This field is required.' in response.data

def test_support_submission_email_dispatch(client, app, test_user):
    """Tests that a valid support request generates an email and logs an audit trail."""
    # Log in
    client.post('/auth/login', data={'email': 'test@example.com', 'password': 'Password123!'})

    # Setup an admin user in DB so that we can verify they receive the email
    with app.app_context():
        admin = User(
            name="Admin User",
            username="adminuser",
            email="admin@example.com",
            is_admin=True
        )
        admin.set_password("Password123!")
        db.session.add(admin)
        db.session.commit()

    # Mock send_email to inspect its arguments
    with patch.object(EmailService, 'send_email', return_value={"success": True}) as mock_send:
        response = client.post('/support', data={'message': 'Hello, I need help with my budget calculations.'}, follow_redirects=True)
        assert response.status_code == 200
        assert b'Your message has been sent successfully' in response.data

        # Verify that send_email was called
        mock_send.assert_called_once()
        
        # Verify recipients and sender info
        args, kwargs = mock_send.call_args
        to_emails = args[0]
        subject = args[1]
        body_html = kwargs.get('body_html')
        from_email = kwargs.get('from_email')

        assert "admin@example.com" in to_emails
        assert "Support Request" in subject
        assert from_email == "test@example.com"
        assert "Hello, I need help with my budget calculations." in body_html
        
        # Verify that audit log was generated
        with app.app_context():
            logs = AuditLog.query.filter_by(action="Support Message Sent").all()
            assert len(logs) > 0
            assert "testuser" in logs[0].details

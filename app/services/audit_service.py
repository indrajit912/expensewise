from flask import has_request_context, request
from flask_login import current_user
from app.extensions import db
from app.models.user import AuditLog

class AuditService:
    """Service to record system actions for security audit logging."""

    @staticmethod
    def log(action: str, details: str = None, user_id: str = None):
        """Creates an audit log entry in the database."""
        ip = None
        if has_request_context():
            # Parse IP address, handling potential reverse proxy forward headers
            ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            if ip and ',' in ip:
                ip = ip.split(',')[0].strip()
            
        uid = user_id
        if not uid and has_request_context() and current_user and current_user.is_authenticated:
            uid = current_user.id

        log_entry = AuditLog(
            user_id=uid,
            action=action,
            details=details,
            ip_address=ip
        )
        try:
            db.session.add(log_entry)
            db.session.commit()
        except Exception:
            db.session.rollback()

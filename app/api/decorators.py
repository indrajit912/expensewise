from functools import wraps
from flask import request, jsonify, g
from app.models.user import APIToken

def token_required(f):
    """Decorator to enforce secure API token validation on endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == 'bearer':
                token = parts[1]
                
        if not token:
            return jsonify({
                'error': 'Unauthorized', 
                'message': 'API Token is missing in Authorization Header.'
            }), 401
            
        api_token = APIToken.query.filter_by(token=token).first()
        
        if not api_token or not api_token.is_valid:
            return jsonify({
                'error': 'Unauthorized', 
                'message': 'API Token is invalid, revoked, or expired.'
            }), 401
            
        # Bind the authorized user and current token to the thread-local globals
        g.current_user = api_token.user
        g.current_token = api_token
        return f(*args, **kwargs)
        
    return decorated

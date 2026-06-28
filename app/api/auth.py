import re
import random
from flask import request, jsonify, g
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from app.models.user import User, APIToken, UserOTP
from app.api import api
from app.api.decorators import token_required
from app.api.schemas import UserSchema
from app.services.email_service import EmailService
from app.services.encryption_service import EncryptionService
from app.services.audit_service import AuditService

user_schema = UserSchema()

def check_password_strength(password):
    """Enforces standard complexity checks for API passwords."""
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if not any(c.isupper() for c in password):
        return "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one number."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return "Password must contain at least one special character."
    return None


@api.route('/v1/auth/register', methods=['POST'])
def api_register():
    """Endpoint to register a new user via API. Account is inactive until OTP verification."""
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    username = data.get('username', '').strip().lower()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not name or not username or not email or not password:
        return jsonify({'error': 'Bad Request', 'message': 'Name, username, email, and password are required fields.'}), 400

    # Validation checks
    strength_err = check_password_strength(password)
    if strength_err:
        return jsonify({'error': 'Bad Request', 'message': strength_err}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Conflict', 'message': 'An account with this email address already exists.'}), 409

    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Conflict', 'message': 'This username is already taken.'}), 409

    try:
        user = User(name=name, username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        user.seed_defaults()

        # Generate and send registration OTP
        otp = f"{random.randint(100000, 999999)}"
        otp_hash = generate_password_hash(otp)
        
        otp_entry = UserOTP(
            user_id=user.id,
            otp_hash=otp_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)
        )
        db.session.add(otp_entry)
        db.session.commit()

        try:
            EmailService.send_otp_email(user.email, otp)
        except Exception:
            pass

        return jsonify({
            'message': 'Account registered! A verification OTP has been sent to your email. Please verify at /api/v1/auth/verify-otp before logging in.',
            'user_id': user.id,
            'user': user_schema.dump(user)
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@api.route('/v1/auth/verify-otp', methods=['POST'])
def api_verify_otp():
    """Endpoint to verify OTP and activate account."""
    data = request.get_json() or {}
    user_id = data.get('user_id')
    email = data.get('email')
    entered_otp = data.get('otp', '').strip()

    if not entered_otp or (not user_id and not email):
        return jsonify({'error': 'Bad Request', 'message': 'Provide otp and either user_id or email.'}), 400

    user = None
    if user_id:
        user = User.query.get(user_id)
    else:
        user = User.query.filter_by(email=email.strip().lower()).first()

    if not user:
        return jsonify({'error': 'Not Found', 'message': 'User account not found.'}), 404

    otp_entry = UserOTP.query.filter_by(user_id=user.id).first()
    if not otp_entry:
        return jsonify({'error': 'Bad Request', 'message': 'No active verification code found.'}), 400

    if otp_entry.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        db.session.delete(otp_entry)
        db.session.commit()
        return jsonify({'error': 'Bad Request', 'message': 'Verification code has expired.'}), 400

    if otp_entry.attempts >= 3:
        db.session.delete(otp_entry)
        db.session.commit()
        return jsonify({'error': 'Bad Request', 'message': 'Too many incorrect attempts. Request a new OTP.'}), 400

    if check_password_hash(otp_entry.otp_hash, entered_otp):
        user.is_active = True
        user.is_email_verified = True
        db.session.delete(otp_entry)
        db.session.commit()

        AuditService.log("Registration Complete", f"Activated email verified account via API", user_id=user.id)
        return jsonify({'message': 'Email verified and account activated successfully! You may now login.'}), 200
    else:
        otp_entry.attempts += 1
        db.session.commit()
        attempts_left = 3 - otp_entry.attempts
        return jsonify({'error': 'Unauthorized', 'message': f'Incorrect OTP. Attempts remaining: {attempts_left}'}), 401


@api.route('/v1/auth/resend-otp', methods=['POST'])
def api_resend_otp():
    """Generates and sends a new registration OTP code via API."""
    data = request.get_json() or {}
    user_id = data.get('user_id')
    email = data.get('email')

    if not user_id and not email:
        return jsonify({'error': 'Bad Request', 'message': 'Provide user_id or email.'}), 400

    user = None
    if user_id:
        user = User.query.get(user_id)
    else:
        user = User.query.filter_by(email=email.strip().lower()).first()

    if not user:
        return jsonify({'error': 'Not Found', 'message': 'User account not found.'}), 404

    # Enforce security requirements 1 & 2
    if user.is_email_verified:
        return jsonify({'error': 'Bad Request', 'message': 'This account is already verified.'}), 400

    # Requirement 5: Rate Limiting
    existing_otp = UserOTP.query.filter_by(user_id=user.id).first()
    if existing_otp:
        time_elapsed = datetime.now(timezone.utc) - existing_otp.created_at.replace(tzinfo=timezone.utc)
        if time_elapsed.total_seconds() < 60:
            seconds_to_wait = int(60 - time_elapsed.total_seconds())
            return jsonify({
                'error': 'Too Many Requests',
                'message': f'Please wait {seconds_to_wait} seconds before requesting another verification code.'
            }), 429

    # Invalidate previous OTPs (Requirement 3)
    if existing_otp:
        db.session.delete(existing_otp)

    # Create fresh OTP (Requirement 4)
    otp = f"{random.randint(100000, 999999)}"
    otp_hash = generate_password_hash(otp)
    
    otp_entry = UserOTP(
        user_id=user.id,
        otp_hash=otp_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)
    )
    db.session.add(otp_entry)
    db.session.commit()
    
    try:
        EmailService.send_otp_email(user.email, otp)
    except Exception:
        pass
        
    return jsonify({'message': 'A fresh verification OTP has been sent to your email address.'}), 200


@api.route('/v1/auth/login', methods=['POST'])
def api_login():
    """Endpoint to exchange user credentials for an API authorization token."""
    data = request.get_json() or {}
    email_input = data.get('email', '').strip().lower()
    
    if email_input == 'guest':
        email_input = 'guest@expensewise.local'
        
    password = data.get('password', '')

    if not email_input or not password:
        return jsonify({'error': 'Bad Request', 'message': 'Email/Username and password are required fields.'}), 400

    user = User.query.filter((User.email == email_input) | (User.username == email_input)).first()
    if not user:
        AuditService.log("Failed Login Attempt", f"API login attempt for non-existent account: {email_input}")
        return jsonify({'error': 'Unauthorized', 'message': 'Invalid email/username or password.'}), 401

    # Check brute force Lockouts
    if user.lockout_until and user.lockout_until.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
        seconds_left = int((user.lockout_until.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).total_seconds())
        minutes_left = (seconds_left // 60) + 1
        return jsonify({'error': 'Locked', 'message': f'Account locked due to consecutive failures. Try again in {minutes_left} minutes.'}), 423

    if user.check_password(password):
        if not user.is_email_verified:
            # Check if OTP has expired
            otp_entry = UserOTP.query.filter_by(user_id=user.id).first()
            expired = not otp_entry or otp_entry.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc)
            
            message = 'Your email address has not yet been verified.'
            if expired:
                message += ' Your previous verification code has expired.'
                
            return jsonify({
                'error': 'Unverified',
                'message': message,
                'user_id': user.id,
                'email': user.email
            }), 403
            
        if not user.is_active:
            return jsonify({'error': 'Unauthorized', 'message': 'This account has not been activated.'}), 401

        # Derive key and decrypt data Fernet key
        try:
            derived_key = EncryptionService.derive_key(password, user.kdf_salt)
            fernet_key = EncryptionService.decrypt_fernet_key(user.encrypted_fernet_key, derived_key)
            
            # Lazy migration for existing users
            if not user.server_encrypted_fernet_key:
                try:
                    server_derived = EncryptionService.get_server_master_key()
                    user.server_encrypted_fernet_key = EncryptionService.encrypt_fernet_key(fernet_key, server_derived)
                except Exception:
                    pass
        except Exception as e:
            return jsonify({'error': 'Server Error', 'message': 'Failed to unlock secure vault.'}), 500

        # Reset failed lockouts
        user.failed_login_attempts = 0
        user.lockout_until = None
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()

        # Generate token
        expires_in_days = 1
        custom_days = data.get('expires_in_days')
        if custom_days is not None:
            try:
                custom_days_val = int(custom_days)
                if custom_days_val != 1:
                    if not user.can_create_custom_tokens:
                        return jsonify({
                            'error': 'Forbidden',
                            'message': 'You do not have permission to specify a custom API token lifetime.'
                        }), 403
                    if custom_days_val < 1 or custom_days_val > 365:
                        return jsonify({
                            'error': 'Bad Request',
                            'message': 'Token lifespan must be between 1 and 365 days.'
                        }), 400
                    expires_in_days = custom_days_val
            except (ValueError, TypeError):
                return jsonify({
                    'error': 'Bad Request',
                    'message': 'Lifespan must be a valid integer.'
                }), 400

        try:
            token_str = user.generate_token(expires_in_days=expires_in_days)
            token_obj = APIToken.query.filter_by(token=token_str).first()
            
            # Store decrypted key in cache keyed by token
            EncryptionService.store_user_key(user.id, fernet_key, token=token_str)
            
            # Log audit
            AuditService.log("Login", "Successful API login", user_id=user.id)

            return jsonify({
                'token': token_str,
                'token_type': 'Bearer',
                'expires_at': token_obj.expires_at.isoformat(),
                'user': user_schema.dump(user)
            }), 200
        except Exception as e:
            return jsonify({'error': 'Server Error', 'message': str(e)}), 500
    else:
        # Increment failed count
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.lockout_until = datetime.now(timezone.utc) + timedelta(minutes=15)
            db.session.commit()
            AuditService.log("Account Lockout", f"API account lockout for 15 minutes due to 5 failures", user_id=user.id)
            return jsonify({'error': 'Locked', 'message': 'Too many failed attempts. Account locked for 15 minutes.'}), 423
        else:
            db.session.commit()
            AuditService.log("Failed Login Attempt", f"Incorrect API password for user {user.email}", user_id=user.id)
            return jsonify({'error': 'Unauthorized', 'message': 'Invalid email/username or password.'}), 401


@api.route('/v1/auth/logout', methods=['POST'])
@token_required
def api_logout():
    """Endpoint to invalidate the current active API token and purge keys."""
    try:
        token_obj = g.current_token
        user_id = token_obj.user_id
        email = token_obj.user.email
        
        # Purge key from in-memory cache
        EncryptionService.clear_user_key(token=token_obj.token)
        
        # Delete database token record
        db.session.delete(token_obj)
        db.session.commit()
        
        # Audit log
        AuditService.log("Logout", "Successful API logout", user_id=user_id)
        
        return jsonify({'message': 'Logged out successfully. Token invalidated.'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@api.route('/v1/auth/me', methods=['GET'])
@token_required
def api_me():
    """Retrieve details of the currently authenticated user."""
    user = g.current_user
    return jsonify({
        'id': user.id,
        'name': user.name,
        'username': user.username,
        'email': user.email,
        'default_currency': user.default_currency,
        'is_active': user.is_active,
        'is_admin': user.is_admin,
        'created_at': user.date_joined.isoformat()
    }), 200


@api.route('/v1/auth/change-password', methods=['POST'])
@token_required
def api_change_password():
    """Updates user's password securely, ensuring KDF values and secure keys remain in sync."""
    data = request.get_json() or {}
    current_pw = data.get('current_password', '')
    new_pw = data.get('new_password', '')
    
    if not current_pw or not new_pw:
        return jsonify({'error': 'Bad Request', 'message': 'Both current_password and new_password fields are required.'}), 400
        
    user = g.current_user
    if not user.check_password(current_pw):
        return jsonify({'error': 'Unauthorized', 'message': 'Incorrect current password.'}), 401
        
    if len(new_pw) < 8:
        return jsonify({'error': 'Bad Request', 'message': 'New password must be at least 8 characters long.'}), 400
    if not any(c.isupper() for c in new_pw):
        return jsonify({'error': 'Bad Request', 'message': 'Password must contain at least one uppercase letter.'}), 400
    if not any(c.islower() for c in new_pw):
        return jsonify({'error': 'Bad Request', 'message': 'Password must contain at least one lowercase letter.'}), 400
    if not any(c.isdigit() for c in new_pw):
        return jsonify({'error': 'Bad Request', 'message': 'Password must contain at least one number.'}), 400
        
    import re
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", new_pw):
        return jsonify({'error': 'Bad Request', 'message': 'Password must contain at least one special character.'}), 400
        
    try:
        user.set_password(new_pw)
        db.session.commit()
        
        # Log audit
        AuditService.log("Password Change", "Successfully changed password via API settings", user_id=user.id)
        return jsonify({'message': 'Your password has been changed successfully.'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500

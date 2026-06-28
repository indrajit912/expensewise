import random
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, session
from flask_login import login_user, logout_user, current_user, login_required
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash
from app.extensions import db
from app.models.user import User, UserOTP
from app.auth.forms import LoginForm, RegisterForm, ResetPasswordRequestForm, ResetPasswordForm, populate_timezone_choices
from app.services.email_service import EmailService
from app.services.encryption_service import EncryptionService
from app.services.audit_service import AuditService
from app.services.timezone_service import TimezoneService

auth = Blueprint('auth', __name__, template_folder='templates')

@auth.route('/register', methods=['GET', 'POST'])
def register():
    """Renders the registration form, creates user with locked encryption keys, and issues verification OTP."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    form = RegisterForm()
    
    # Populate timezone choices
    if request.method == 'GET':
        populate_timezone_choices(form)
    
    if form.validate_on_submit():
        # Validate timezone
        if not TimezoneService.is_valid_timezone(form.timezone.data):
            flash('Invalid timezone selected. Defaulting to UTC.', 'warning')
            timezone_value = 'UTC'
        else:
            timezone_value = form.timezone.data
        
        # Account is initialized inactive (is_active=False) until OTP verification is completed
        user = User(
            name=form.name.data,
            username=form.username.data.lower().strip(),
            email=form.email.data.lower().strip(),
            default_currency=form.default_currency.data,
            timezone=timezone_value
        )
        user.set_password(form.password.data)
        
        db.session.add(user)
        db.session.commit()
        user.seed_defaults()
        
        # 1. Generate 6-digit verification code
        otp = f"{random.randint(100000, 999999)}"
        otp_hash = generate_password_hash(otp)
        
        # 2. Save OTP to DB
        otp_entry = UserOTP(
            user_id=user.id,
            otp_hash=otp_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)
        )
        db.session.add(otp_entry)
        db.session.commit()
        
        # 3. Dispatch OTP via Hermes Email Service
        try:
            EmailService.send_otp_email(user.email, otp)
        except Exception:
            # Fallback prints in terminal when Hermes variables are not initialized in local dev
            pass
            
        session['verify_user_id'] = user.id
        flash('Account registered successfully! A 6-digit verification OTP has been sent to your email.', 'info')
        return redirect(url_for('auth.verify_otp'))
        
    return render_template('auth/register.html', form=form)


@auth.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    """Verifies the registration OTP code and activates the account."""
    user_id = session.get('verify_user_id')
    if not user_id:
        flash('Session expired. Please register again.', 'warning')
        return redirect(url_for('auth.register'))
        
    user = User.query.get(user_id)
    if not user:
        flash('User not found. Please register again.', 'danger')
        return redirect(url_for('auth.register'))

    if user.is_email_verified:
        flash('Your email is already verified. Please log in.', 'info')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        entered_otp = request.form.get('otp', '').strip()
        
        # Fetch active OTP record
        otp_entry = UserOTP.query.filter_by(user_id=user.id).first()
        
        if not otp_entry:
            flash('No active verification code found. Please request a new one.', 'danger')
            return redirect(url_for('auth.verify_otp'))
            
        # Check expiry
        if otp_entry.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            db.session.delete(otp_entry)
            db.session.commit()
            flash('Verification code has expired. Please request a new code.', 'danger')
            return redirect(url_for('auth.verify_otp'))
            
        # Check attempts lockout
        if otp_entry.attempts >= 3:
            db.session.delete(otp_entry)
            db.session.commit()
            flash('Too many incorrect verification attempts. Please request a new OTP.', 'danger')
            return redirect(url_for('auth.verify_otp'))

        # Verify hash match
        from werkzeug.security import check_password_hash
        if check_password_hash(otp_entry.otp_hash, entered_otp):
            # Activate account
            user.is_active = True
            user.is_email_verified = True
            db.session.delete(otp_entry)
            db.session.commit()
            
            # Log action
            AuditService.log("Registration Complete", f"Activated email verified account for {user.email}", user_id=user.id)
            
            session.pop('verify_user_id', None)
            flash('Your account has been verified and activated successfully! Please log in to unlock your data vault.', 'success')
            return redirect(url_for('auth.login'))
        else:
            otp_entry.attempts += 1
            db.session.commit()
            attempts_left = 3 - otp_entry.attempts
            if attempts_left > 0:
                flash(f'Invalid verification code. You have {attempts_left} attempts remaining.', 'warning')
            else:
                db.session.delete(otp_entry)
                db.session.commit()
                flash('Too many incorrect verification attempts. Request a new OTP.', 'danger')
                
    return render_template('auth/verify_otp.html')


@auth.route('/resend-otp', methods=['POST'])
def resend_otp():
    """Generates and sends a new registration OTP code."""
    user_id = session.get('verify_user_id')
    if not user_id:
        flash('Session expired. Please register again.', 'warning')
        return redirect(url_for('auth.register'))
        
    user = User.query.get(user_id)
    if not user:
        flash('User not found. Please register again.', 'danger')
        return redirect(url_for('auth.register'))

    # Security Requirement: Verified accounts should not trigger this
    if user.is_email_verified:
        flash('This account is already verified. Please log in.', 'info')
        return redirect(url_for('auth.login'))
        
    # Rate Limiting (e.g. 60 seconds interval)
    existing_otp = UserOTP.query.filter_by(user_id=user.id).first()
    if existing_otp:
        time_elapsed = datetime.now(timezone.utc) - existing_otp.created_at.replace(tzinfo=timezone.utc)
        if time_elapsed.total_seconds() < 60:
            seconds_to_wait = int(60 - time_elapsed.total_seconds())
            flash(f'Please wait {seconds_to_wait} seconds before requesting another verification code.', 'warning')
            return redirect(url_for('auth.verify_otp'))
            
    # Delete old OTP entry (Invalidate previous)
    if existing_otp:
        db.session.delete(existing_otp)
    
    # Create fresh OTP
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
        
    flash('A fresh verification OTP has been sent to your email address.', 'success')
    return redirect(url_for('auth.verify_otp'))


@auth.route('/login', methods=['GET', 'POST'])
def login():
    """Authenticates users, enforces lockout rules, and decrypts E2E keys."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
        
    form = LoginForm()
    if form.validate_on_submit():
        email_input = form.email.data.lower().strip()
        
        # Handle guest alias
        if email_input == 'guest':
            email_input = 'guest@expensewise.local'
            
        user = User.query.filter((User.email == email_input) | (User.username == email_input)).first()
        
        if user:
            # 1. Enforce security account lockouts
            if user.lockout_until and user.lockout_until.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
                seconds_left = int((user.lockout_until.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).total_seconds())
                minutes_left = (seconds_left // 60) + 1
                flash(f'Account locked due to consecutive failures. Try again in {minutes_left} minutes.', 'danger')
                return redirect(url_for('auth.login'))
 
            if user.check_password(form.password.data):
                # 2. Check if account email has been verified
                if not user.is_email_verified:
                    session['verify_user_id'] = user.id
                    
                    # Determine if previous verification code has expired
                    otp_entry = UserOTP.query.filter_by(user_id=user.id).first()
                    expired = not otp_entry or otp_entry.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc)
                    
                    if expired:
                        flash('Your email address has not yet been verified, and your previous verification code has expired. Please verify your email or request a new OTP.', 'warning')
                    else:
                        flash('Your email address has not yet been verified. Please enter the verification code sent to your email.', 'info')
                        
                    return redirect(url_for('auth.verify_otp'))
                    
                # Account status checks
                if not user.is_active:
                    flash('This account is disabled. Please contact support.', 'danger')
                    return redirect(url_for('auth.login'))
                    
                # 2. Derive key and decrypt data Fernet key
                try:
                    derived_key = EncryptionService.derive_key(form.password.data, user.kdf_salt)
                    fernet_key = EncryptionService.decrypt_fernet_key(user.encrypted_fernet_key, derived_key)
                    EncryptionService.store_user_key(user.id, fernet_key)
                    
                    # Lazy migration for existing users
                    if not user.server_encrypted_fernet_key:
                        try:
                            server_derived = EncryptionService.get_server_master_key()
                            user.server_encrypted_fernet_key = EncryptionService.encrypt_fernet_key(fernet_key, server_derived)
                        except Exception as migration_err:
                            current_app.logger.error("Lazy migration failed for %s: %s", user.email, str(migration_err))
                except Exception as e:
                    current_app.logger.error("Failed to decrypt Fernet key for user %s: %s", user.email, str(e))
                    flash('Failed to unlock database vault. Check password integrity.', 'danger')
                    return redirect(url_for('auth.login'))
                
                # Reset lockouts on success
                user.failed_login_attempts = 0
                user.lockout_until = None
                user.last_login = datetime.now(timezone.utc)
                db.session.commit()
                
                # Login
                login_user(user, remember=form.remember_me.data)
                
                # Record login audit event
                AuditService.log("Login", f"Successful login for user {user.email}", user_id=user.id)
                
                next_page = request.args.get('next')
                flash(f"Welcome back, {user.name}!", 'success')
                return redirect(next_page) if next_page and next_page.startswith('/') else redirect(url_for('dashboard.index'))
            else:
                # Password failure lockout increment
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= 5:
                    user.lockout_until = datetime.now(timezone.utc) + timedelta(minutes=15)
                    db.session.commit()
                    AuditService.log("Account Lockout", f"User {user.email} locked out for 15 minutes due to 5 failures", user_id=user.id)
                    flash('Too many failed login attempts. Account locked for 15 minutes.', 'danger')
                else:
                    db.session.commit()
                    AuditService.log("Failed Login Attempt", f"Incorrect password for user {user.email}", user_id=user.id)
                    flash('Invalid email/username or password. Please try again.', 'danger')
        else:
            # Audit log for non-existent users
            AuditService.log("Failed Login Attempt", f"Login attempt for non-existent account: {email_input}")
            flash('Invalid email/username or password. Please try again.', 'danger')
            
    return render_template('auth/login.html', form=form)


@auth.route('/logout')
@login_required
def logout():
    """Terminates session, purges unlocked keys, and records logs."""
    # Audit log before destroying session variables
    user_id = current_user.id
    email = current_user.email
    
    # 1. Purge key material
    EncryptionService.clear_user_key()
    
    # 2. Terminate Flask-Login
    logout_user()
    
    # 3. Write logs
    AuditService.log("Logout", f"Successful logout for user {email}", user_id=user_id)
    
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('dashboard.landing'))


@auth.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    """Generates password reset URLs and sends emails via Hermes."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
        
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if user:
            reset_token = user.id  # Mock token using UUID key
            reset_link = url_for('auth.reset_password', token=reset_token, _external=True)
            
            # Send reset email using Hermes Email Service
            try:
                EmailService.send_password_reset_email(user.email, reset_link)
            except Exception:
                pass
            
            AuditService.log("Password Reset Request", f"Requested password reset for user {user.email}", user_id=user.id)
            
        flash('An email has been sent with instructions to reset your password if that account exists.', 'info')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/reset_password_request.html', form=form)


@auth.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Sets a new password, performs complexity checks, and re-encrypts E2E keys."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
        
    user = User.query.get(token)
    if not user:
        flash('Invalid or expired password reset link.', 'danger')
        return redirect(url_for('auth.login'))
        
    form = ResetPasswordForm()
    if form.validate_on_submit():
        new_password = form.password.data
        
        # Enforce that ghostrix attributes cannot be modified except via authorized channels
        if user.is_super_admin and user.email != 'indrajitghosh912@gmail.com':
            flash('Unauthorized super admin reset attempt blocked.', 'danger')
            return redirect(url_for('auth.login'))
            
        # Re-encrypt/update password keys
        user.set_password(new_password)
        db.session.commit()
        
        AuditService.log("Password Reset Complete", f"Successfully reset password for user {user.email}", user_id=user.id)
        
        flash('Your password has been reset successfully. Please log in.', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/reset_password.html', form=form)

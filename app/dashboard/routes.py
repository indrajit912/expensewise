import os
import re
import json
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, abort, current_app
from flask_login import login_required, current_user
from datetime import datetime, timezone, timedelta, date
from app.extensions import db
from app.models.user import User, APIToken, AuditLog
from app.models.expense import Expense, Category, PaymentMethod
from app.services.analytics_service import AnalyticsService
from app.services.audit_service import AuditService
from app.services.timezone_service import TimezoneService

dashboard = Blueprint('dashboard', __name__, template_folder='templates')

HEX_COLOR_RE = re.compile(r'^#([0-9a-fA-F]{6})$')

def parse_color(value):
    if not value:
        return None
    clean_value = value.strip()
    return clean_value if HEX_COLOR_RE.match(clean_value) else None

@dashboard.route('/')
def landing():
    """Renders the welcoming landing page for anonymous guests."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    return render_template('landing.html')


@dashboard.route('/dashboard')
@login_required
def index():
    """Compiles dashboard analytics and charts to display to the user."""
    user_id = current_user.id
    
    # 1. Compute summary calculations (handled inside AnalyticsService with Python decryption)
    metrics = AnalyticsService.get_summary_metrics(user_id)
    comp_metrics = AnalyticsService.get_comparison_metrics(user_id)
    
    # 2. Fetch chart datasets
    # Query strictly the last 30 days consistently
    _today = date.today()
    start_date = _today - timedelta(days=30)
    daily_labels, daily_values = AnalyticsService.get_daily_trend(user_id, days=30)
    category_dist = AnalyticsService.get_category_distribution(user_id=user_id, start_date=start_date, end_date=_today)
    
    # 3. Grab recent expenses (limit 5) for quick overview
    # Sort in memory since dates are encrypted in database
    expenses = Expense.query.filter_by(user_id=user_id).all()
    expenses.sort(key=lambda x: x.expense_date or datetime.min.date(), reverse=True)
    recent_expenses = expenses[:8]
        
    return render_template(
        'dashboard/index.html',
        metrics=metrics,
        comp_metrics=comp_metrics,
        daily_labels=daily_labels,
        daily_values=daily_values,
        category_dist=category_dist,
        recent_expenses=recent_expenses
    )


@dashboard.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Manages profile details, API Tokens, categories, and payment methods."""
    user_tokens = APIToken.query.filter_by(user_id=current_user.id).order_by(APIToken.created_at.desc()).all()
    categories = Category.query.filter_by(user_id=current_user.id).order_by(Category.name).all()
    payment_methods = PaymentMethod.query.filter_by(user_id=current_user.id).order_by(PaymentMethod.name).all()
    
    # In-memory expense count per category/payment method
    user_expenses = Expense.query.filter_by(user_id=current_user.id).all()
    category_counts = {}
    payment_method_counts = {}
    for e in user_expenses:
        try:
            cat_name = e.category
            if cat_name:
                category_counts[cat_name] = category_counts.get(cat_name, 0) + 1
        except Exception:
            pass
        try:
            pm_name = e.payment_mode
            if pm_name:
                payment_method_counts[pm_name] = payment_method_counts.get(pm_name, 0) + 1
        except Exception:
            pass
    
    # Retrieve new token if generated in this session (one-time display)
    new_token = session.pop('new_token', None)

    if request.method == 'POST':
        action = request.form.get('action')
        
        # Password Change Action
        if action == 'change_password':
            current_pw = request.form.get('current_password', '')
            new_pw = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')
            
            # Validation
            if not current_pw or not new_pw or not confirm_pw:
                flash("All password fields are required.", "danger")
            elif not current_user.check_password(current_pw):
                flash("Incorrect current password.", "danger")
            elif new_pw != confirm_pw:
                flash("New passwords do not match.", "danger")
            elif len(new_pw) < 8:
                flash("New password must be at least 8 characters long.", "danger")
            elif not any(c.isupper() for c in new_pw):
                flash('Password must contain at least one uppercase letter.', 'danger')
            elif not any(c.islower() for c in new_pw):
                flash('Password must contain at least one lowercase letter.', 'danger')
            elif not any(c.isdigit() for c in new_pw):
                flash('Password must contain at least one number.', 'danger')
            else:
                import re
                if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", new_pw):
                    flash('Password must contain at least one special character.', 'danger')
                else:
                    # Update password
                    # Since user is logged in, their decrypted key is in the session/context
                    # Calling user.set_password will re-encrypt it under the new password
                    current_user.set_password(new_pw)
                    db.session.commit()
                    AuditService.log("Password Change", "Successfully changed password from settings", user_id=current_user.id)
                    flash("Your password has been changed successfully.", "success")
            return redirect(url_for('dashboard.settings'))

        # Token Actions
        elif action == 'generate_token':
            expires_in_days = 1
            if current_user.can_create_custom_tokens:
                custom_days_str = request.form.get('expires_in_days', '').strip()
                if custom_days_str:
                    try:
                        custom_days = int(custom_days_str)
                        if custom_days < 1 or custom_days > 365:
                            flash("Lifespan must be between 1 and 365 days.", "danger")
                            return redirect(url_for('dashboard.settings'))
                        expires_in_days = custom_days
                    except ValueError:
                        flash("Invalid lifespan value. Please enter a valid integer.", "danger")
                        return redirect(url_for('dashboard.settings'))
            token_str = current_user.generate_token(expires_in_days=expires_in_days)
            session['new_token'] = token_str
            
            # Cache decrypted key for API token auth
            from app.services.encryption_service import EncryptionService
            ukey = EncryptionService.get_user_key()
            if ukey:
                EncryptionService.store_user_key(current_user.id, ukey, token=token_str)
                
            AuditService.log("API Key Generation", "Generated new API access token")
            flash("New API Token generated successfully.", "success")
            return redirect(url_for('dashboard.settings'))
            
        elif action == 'revoke_token':
            token_to_revoke = request.form.get('token')
            api_tok = APIToken.query.filter_by(token=token_to_revoke, user_id=current_user.id).first()
            if api_tok:
                # Invalidate in cache
                from app.services.encryption_service import EncryptionService
                EncryptionService.clear_user_key(token=token_to_revoke)
                
                db.session.delete(api_tok)
                db.session.commit()
                AuditService.log("API Key Revocation", "Revoked API access token")
                flash("API Token successfully revoked.", "info")
            else:
                flash("Token not found or unauthorized.", "danger")
            return redirect(url_for('dashboard.settings'))

        # Category Actions
        elif action == 'add_category':
            name = request.form.get('name', '').strip()
            color = parse_color(request.form.get('color', '').strip()) or '#475569'
            if not name:
                flash("Category name cannot be empty.", "danger")
            elif Category.query.filter_by(user_id=current_user.id, name=name).first():
                flash("Category already exists.", "warning")
            else:
                db.session.add(Category(user_id=current_user.id, name=name, color=color))
                db.session.commit()
                flash("Category added successfully.", "success")
            
            next_url = request.args.get('next')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect(url_for('dashboard.settings'))

        elif action == 'update_category':
            cat_id = request.form.get('category_id')
            new_name = request.form.get('name', '').strip()
            color_value = request.form.get('color', '').strip()
            category = Category.query.filter_by(id=cat_id, user_id=current_user.id).first()
            parsed_color = parse_color(color_value) if color_value else None
            if not category or not new_name:
                flash("Invalid category or name.", "danger")
            elif parsed_color is None and color_value:
                flash("Invalid category color. Use a hex code like #RRGGBB.", "danger")
            elif Category.query.filter(Category.user_id == current_user.id, Category.name == new_name, Category.id != cat_id).first():
                flash("Another category with this name already exists.", "warning")
            else:
                old_name = category.name
                category.name = new_name
                if parsed_color:
                    category.color = parsed_color
                # Cascade rename inside Expenses
                # Category is encrypted in DB, so we must load and save to re-encrypt
                expenses_to_update = Expense.query.filter_by(user_id=current_user.id).all()
                for e in expenses_to_update:
                    try:
                        if e.category == old_name:
                            e.category = new_name
                    except Exception:
                        continue
                db.session.commit()
                flash("Category updated successfully.", "success")
            return redirect(url_for('dashboard.settings'))

        elif action == 'delete_category':
            cat_id = request.form.get('category_id')
            category = Category.query.filter_by(id=cat_id, user_id=current_user.id).first()
            if not category:
                flash("Category not found.", "danger")
            else:
                # Check for associated expenses (decrypted categories compare)
                has_expenses = False
                all_exps = Expense.query.filter_by(user_id=current_user.id).all()
                for e in all_exps:
                    try:
                        if e.category == category.name:
                            has_expenses = True
                            break
                    except Exception:
                        continue
                if has_expenses:
                    flash(f"Cannot delete category '{category.name}' because existing expenses are associated with it.", "danger")
                else:
                    db.session.delete(category)
                    db.session.commit()
                    flash("Category deleted successfully.", "success")
            return redirect(url_for('dashboard.settings'))

        # Payment Method Actions
        elif action == 'add_payment_method':
            name = request.form.get('name', '').strip()
            color = parse_color(request.form.get('color', '').strip()) or '#475569'
            if not name:
                flash("Payment method name cannot be empty.", "danger")
            elif PaymentMethod.query.filter_by(user_id=current_user.id, name=name).first():
                flash("Payment method already exists.", "warning")
            else:
                db.session.add(PaymentMethod(user_id=current_user.id, name=name, color=color))
                db.session.commit()
                flash("Payment method added successfully.", "success")
            
            next_url = request.args.get('next')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect(url_for('dashboard.settings'))

        elif action == 'update_payment_method':
            pm_id = request.form.get('payment_method_id')
            new_name = request.form.get('name', '').strip()
            color_value = request.form.get('color', '').strip()
            pm = PaymentMethod.query.filter_by(id=pm_id, user_id=current_user.id).first()
            parsed_color = parse_color(color_value) if color_value else None
            if not pm or not new_name:
                flash("Invalid payment method or name.", "danger")
            elif parsed_color is None and color_value:
                flash("Invalid payment method color. Use a hex code like #RRGGBB.", "danger")
            elif PaymentMethod.query.filter(PaymentMethod.user_id == current_user.id, PaymentMethod.name == new_name, PaymentMethod.id != pm_id).first():
                flash("Another payment method with this name already exists.", "warning")
            else:
                old_name = pm.name
                pm.name = new_name
                if parsed_color:
                    pm.color = parsed_color
                # Cascade rename inside Expenses
                expenses_to_update = Expense.query.filter_by(user_id=current_user.id).all()
                for e in expenses_to_update:
                    try:
                        if e.payment_mode == old_name:
                            e.payment_mode = new_name
                    except Exception:
                        continue
                db.session.commit()
                flash("Payment method updated successfully.", "success")
            return redirect(url_for('dashboard.settings'))

        elif action == 'delete_payment_method':
            pm_id = request.form.get('payment_method_id')
            pm = PaymentMethod.query.filter_by(id=pm_id, user_id=current_user.id).first()
            if not pm:
                flash("Payment method not found.", "danger")
            else:
                # Check for associated expenses (decrypted modes compare)
                has_expenses = False
                all_exps = Expense.query.filter_by(user_id=current_user.id).all()
                for e in all_exps:
                    try:
                        if e.payment_mode == pm.name:
                            has_expenses = True
                            break
                    except Exception:
                        continue
                if has_expenses:
                    flash(f"Cannot delete payment method '{pm.name}' because existing expenses are associated with it.", "danger")
                else:
                    db.session.delete(pm)
                    db.session.commit()
                    flash("Payment method deleted successfully.", "success")
            return redirect(url_for('dashboard.settings'))

        elif action == 'update_currency':
            from decimal import Decimal
            new_currency = request.form.get('default_currency', '').strip().upper()
            convert_historical = request.form.get('convert_historical') == '1'
            
            if new_currency not in ['INR', 'USD', 'EUR', 'GBP', 'JPY', 'AUD', 'CAD']:
                flash("Invalid currency selection.", "danger")
                return redirect(url_for('dashboard.settings'))
                
            old_currency = current_user.default_currency
            
            if old_currency == new_currency:
                flash("Default currency was not changed.", "info")
                return redirect(url_for('dashboard.settings'))
                
            if convert_historical:
                rate_val = request.form.get('conversion_rate', '').strip()
                if not rate_val:
                    flash("Conversion rate is required to scale historical expenses.", "danger")
                    return redirect(url_for('dashboard.settings'))
                try:
                    rate = Decimal(str(rate_val))
                    if rate <= 0:
                        raise ValueError()
                except Exception:
                    flash("Invalid conversion rate. Must be a positive decimal.", "danger")
                    return redirect(url_for('dashboard.settings'))
                    
                user_expenses = Expense.query.filter_by(user_id=current_user.id).all()
                
                # Fetch key to pass to background thread
                from app.services.encryption_service import EncryptionService
                ukey = EncryptionService.get_user_key()
                
                if len(user_expenses) > 100:
                    from threading import Thread
                    
                    def run_async_conversion(app, user_id, active_key, old_curr, new_curr, rate_dec):
                        with app.app_context():
                            from app.services.encryption_service import EncryptionService
                            EncryptionService.set_override_key(active_key)
                            
                            u = User.query.get(user_id)
                            exps = Expense.query.filter_by(user_id=user_id).all()
                            
                            for e in exps:
                                try:
                                    e.amount = e.amount * rate_dec
                                    e.conversion_rate = e.conversion_rate * rate_dec
                                    e.converted_amount = e.amount
                                except Exception:
                                    continue
                            
                            u.default_currency = new_curr
                            db.session.commit()
                            EncryptionService.clear_user_key()
                            
                    thr = Thread(target=run_async_conversion, args=(current_app._get_current_object(), current_user.id, ukey, old_currency, new_currency, rate))
                    thr.start()
                    
                    current_user.default_currency = new_currency
                    db.session.commit()
                    
                    AuditService.log("Currency Migration", f"Started background migration from {old_currency} to {new_currency} with rate {rate}")
                    flash("Historical conversion started in the background. Your default currency has been updated.", "info")
                else:
                    for e in user_expenses:
                        try:
                            e.amount = e.amount * rate
                            e.conversion_rate = e.conversion_rate * rate
                            e.converted_amount = e.amount
                        except Exception:
                            continue
                            
                    current_user.default_currency = new_currency
                    db.session.commit()
                    
                    AuditService.log("Currency Migration", f"Synchronously migrated expenses from {old_currency} to {new_currency} with rate {rate}")
                    flash("All historical expenses scaled and default currency updated successfully.", "success")
            else:
                current_user.default_currency = new_currency
                db.session.commit()
                AuditService.log("Currency Settings Update", f"Changed default currency from {old_currency} to {new_currency} without scaling history.")
                flash("Default currency updated. Historical transactions remain unmodified.", "success")
                
            return redirect(url_for('dashboard.settings'))
        
        # Timezone Update Action
        elif action == 'update_timezone':
            new_timezone = request.form.get('timezone', '').strip()
            
            if not TimezoneService.is_valid_timezone(new_timezone):
                flash("Invalid timezone selected.", "danger")
                return redirect(url_for('dashboard.settings'))
            
            old_timezone = current_user.timezone
            
            if old_timezone == new_timezone:
                flash("Timezone was not changed.", "info")
                return redirect(url_for('dashboard.settings'))
            
            current_user.timezone = new_timezone
            db.session.commit()
            AuditService.log("Timezone Settings Update", f"Changed timezone from {old_timezone} to {new_timezone}")
            flash(f"Timezone updated to {new_timezone}. All timestamps will now display in your local timezone.", "success")
            
            return redirect(url_for('dashboard.settings'))

        # Encryption Mode Update Action
        elif action == 'update_encryption':
            enable_enc = request.form.get('encryption_enabled') == '1'
            old_enc = current_user.encryption_enabled
            
            if old_enc != enable_enc:
                from app.services.encryption_service import EncryptionService
                EncryptionService.migrate_user_encryption(current_user, enable_enc)
                current_user.encryption_enabled = enable_enc
                db.session.commit()
                
                state_str = "enabled" if enable_enc else "disabled"
                AuditService.log("Encryption Toggle", f"Changed encryption preference to {state_str}")
                flash(f"Data encryption has been {state_str} successfully. Existing data has been migrated.", "success")
            else:
                flash("Encryption setting was not changed.", "info")
                
            return redirect(url_for('dashboard.settings'))

    return render_template(
        'dashboard/settings.html', 
        tokens=user_tokens, 
        categories=categories, 
        payment_methods=payment_methods,
        new_token=new_token,
        category_counts=category_counts,
        payment_method_counts=payment_method_counts
    )


# ======================================================================
#                       ADMINISTRATIVE SYSTEM
# ======================================================================
@dashboard.route('/admin')
@login_required
def admin_panel():
    """Renders the secure administrative command dashboard."""
    if not current_user.is_admin:
        abort(403) # Forbidden
        
    search_q = request.args.get('search', '').strip()
    
    # 1. Monitoring statistics
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    
    # New registrations past 30 days
    cutoff_30d = datetime.now(timezone.utc) - timedelta(days=30)
    new_regs = User.query.filter(User.date_joined >= cutoff_30d).count()
    
    # Activity metrics from AuditLog
    login_activity = AuditLog.query.filter_by(action="Login").count()
    failed_attempts = AuditLog.query.filter_by(action="Failed Login Attempt").count()
    
    # SQLite file size measurement
    db_file_path = os.path.join(current_app.instance_path, 'expensewise.db')
    db_size_mb = 0.0
    if os.path.exists(db_file_path):
        db_size_mb = os.path.getsize(db_file_path) / (1024 * 1024)
        
    # Expense counts
    total_expenses = Expense.query.count()
    avg_expenses = total_expenses / total_users if total_users > 0 else 0.0
    
    metrics = {
        'total_users': total_users,
        'active_users': active_users,
        'new_registrations': new_regs,
        'login_activity': login_activity,
        'failed_attempts': failed_attempts,
        'db_size_mb': db_size_mb,
        'total_expenses': total_expenses,
        'avg_expenses': avg_expenses
    }

    # 2. User list with search
    user_query = User.query
    if search_q:
        user_query = user_query.filter(
            (User.name.ilike(f"%{search_q}%")) |
            (User.email.ilike(f"%{search_q}%")) |
            (User.username.ilike(f"%{search_q}%"))
        )
    users = user_query.order_by(User.date_joined.desc()).all()
    
    # 3. System audit logs (limit to recent 100)
    audit_logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all()

    return render_template(
        'dashboard/admin.html',
        metrics=metrics,
        users=users,
        audit_logs=audit_logs,
        search=search_q,
        datetime_now=datetime.utcnow()
    )


@dashboard.route('/admin/user/<user_id>/suspend', methods=['POST'])
@login_required
def admin_suspend_user(user_id):
    """Deactivates a user account (ghostrix is protected)."""
    if not current_user.is_admin:
        abort(403)
        
    user = User.query.get_or_404(user_id)
    if user.is_super_admin or user.username == 'ghostrix':
        flash('The super administrator account cannot be suspended.', 'danger')
        return redirect(url_for('dashboard.admin_panel'))
        
    user.is_active = False
    db.session.commit()
    
    AuditService.log("User Suspension", f"Suspended account for user {user.email}", user_id=current_user.id)
    flash(f"User account for '{user.name}' has been suspended successfully.", "success")
    return redirect(url_for('dashboard.admin_panel'))


@dashboard.route('/admin/user/<user_id>/reactivate', methods=['POST'])
@login_required
def admin_reactivate_user(user_id):
    """Activates a suspended user account."""
    if not current_user.is_admin:
        abort(403)
        
    user = User.query.get_or_404(user_id)
    user.is_active = True
    db.session.commit()
    
    AuditService.log("User Reactivation", f"Reactivated account for user {user.email}", user_id=current_user.id)
    flash(f"User account for '{user.name}' has been reactivated successfully.", "success")
    return redirect(url_for('dashboard.admin_panel'))


@dashboard.route('/admin/user/<user_id>/toggle-custom-tokens', methods=['POST'])
@login_required
def admin_toggle_custom_tokens(user_id):
    """Grants or revokes permission to create custom API token lifetimes for a user."""
    if not current_user.is_admin:
        abort(403)
        
    user = User.query.get_or_404(user_id)
    if user.is_super_admin or user.is_admin or user.username == 'ghostrix':
        flash('Administrator accounts automatically have custom API token lifetime permissions.', 'info')
        return redirect(url_for('dashboard.admin_panel'))
        
    user.can_create_custom_api_tokens = not user.can_create_custom_api_tokens
    db.session.commit()
    
    state = "Granted" if user.can_create_custom_api_tokens else "Revoked"
    AuditService.log("Permission Toggle", f"{state} custom API token permission for user {user.email}", user_id=current_user.id)
    flash(f"Custom API token lifetime permission has been {state.lower()} for '{user.name}'.", "success")
    return redirect(url_for('dashboard.admin_panel'))


@dashboard.route('/admin/user/<user_id>/promote', methods=['POST'])
@login_required
def admin_promote_user(user_id):
    """Grants administrative rights to a standard user."""
    if not current_user.is_admin:
        abort(403)
        
    user = User.query.get_or_404(user_id)
    user.is_admin = True
    db.session.commit()
    
    AuditService.log("Role Promotion", f"Promoted user {user.email} to administrator role", user_id=current_user.id)
    flash(f"User '{user.name}' has been promoted to Administrator role.", "success")
    return redirect(url_for('dashboard.admin_panel'))


@dashboard.route('/admin/user/<user_id>/revoke', methods=['POST'])
@login_required
def admin_revoke_user(user_id):
    """Revokes administrative rights (ghostrix is protected)."""
    if not current_user.is_admin:
        abort(403)
        
    # Only super-admins may revoke administrator rights
    if not current_user.is_super_admin:
        flash('Only the super administrator may revoke administrator rights.', 'danger')
        return redirect(url_for('dashboard.admin_panel'))
        
    user = User.query.get_or_404(user_id)
    if user.is_super_admin or user.username == 'ghostrix':
        flash('Super administrator privileges cannot be revoked.', 'danger')
        return redirect(url_for('dashboard.admin_panel'))
        
    user.is_admin = False
    db.session.commit()
    
    AuditService.log("Role Demotion", f"Revoked administrator privileges for user {user.email}", user_id=current_user.id)
    flash(f"Administrator privileges for '{user.name}' have been revoked.", "success")
    return redirect(url_for('dashboard.admin_panel'))


@dashboard.route('/admin/user/<user_id>/delete', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    """Deletes a user account entirely (ghostrix is protected)."""
    if not current_user.is_admin:
        abort(403)
        
    user = User.query.get_or_404(user_id)
    
    try:
        # DB deletion triggers prevent_super_admin_deletion event listener check
        db.session.delete(user)
        db.session.commit()
        AuditService.log("User Deletion", f"Permanently deleted account for user {user.email}", user_id=current_user.id)
        flash("User account deleted successfully.", "success")
    except ValueError as val_err:
        db.session.rollback()
        flash(str(val_err), "danger")
    except Exception as e:
        db.session.rollback()
        flash(f"Deletion failed: {str(e)}", "danger")
        
    return redirect(url_for('dashboard.admin_panel'))


@dashboard.route('/budget', methods=['GET', 'POST'])
@login_required
def budget():
    """Budget planning route."""
    from decimal import Decimal
    from datetime import date
    from app.models.expense import Budget
    
    # Calculate upcoming month as default (YYYY-MM)
    now = datetime.now()
    if now.month == 12:
        upcoming_year = now.year + 1
        upcoming_month = 1
    else:
        upcoming_year = now.year
        upcoming_month = now.month + 1
    default_month = f"{upcoming_year}-{upcoming_month:02d}"
    
    target_month = request.args.get('month', default_month)
    
    # Validate target_month matches YYYY-MM format
    if not re.match(r'^\d{4}-\d{2}$', target_month):
        target_month = default_month

    # Load categories
    categories = Category.query.filter_by(user_id=current_user.id).order_by(Category.name).all()
    cat_names = [c.name for c in categories]

    # Save logic
    if request.method == 'POST':
        for cat in categories:
            amount_str = request.form.get(f"budget_{cat.name}", "").strip()
            if amount_str:
                try:
                    amount_val = Decimal(amount_str)
                    if amount_val < 0:
                        amount_val = Decimal('0.00')
                except Exception:
                    amount_val = Decimal('0.00')
                
                # Check if budget already exists
                budget_entry = Budget.query.filter_by(
                    user_id=current_user.id,
                    month=target_month,
                    category_name=cat.name
                ).first()
                
                if budget_entry:
                    budget_entry.amount = amount_val
                else:
                    budget_entry = Budget(
                        user_id=current_user.id,
                        month=target_month,
                        category_name=cat.name,
                        amount=amount_val
                    )
                    db.session.add(budget_entry)
            else:
                # If blank, remove budget constraint
                budget_entry = Budget.query.filter_by(
                    user_id=current_user.id,
                    month=target_month,
                    category_name=cat.name
                ).first()
                if budget_entry:
                    db.session.delete(budget_entry)
        
        db.session.commit()
        AuditService.log("Budget Save", f"Saved monthly budget for {target_month}", user_id=current_user.id)
        flash(f"Budgets for {target_month} saved successfully.", "success")
        return redirect(url_for('dashboard.budget', month=target_month))

    # Calculate 3-month historical averages
    # We use complete months prior to the target_month
    try:
        t_year, t_month = map(int, target_month.split('-'))
        t_first_day = date(t_year, t_month, 1)
    except Exception:
        t_first_day = date(now.year, now.month, 1)
        
    # Standard history range: 3 complete months preceding target_month's first day
    hist_start_month = t_first_day.month - 3
    hist_start_year = t_first_day.year
    while hist_start_month <= 0:
        hist_start_month += 12
        hist_start_year -= 1
    start_date = date(hist_start_year, hist_start_month, 1)
    end_date = t_first_day - timedelta(days=1)
    
    # Calculate target month end date
    next_month = t_first_day.month + 1
    next_year = t_first_day.year
    if next_month > 12:
        next_month = 1
        next_year += 1
    t_end_day = date(next_year, next_month, 1) - timedelta(days=1)

    # Fetch all user expenses (filtering/decryption happens in Python memory)
    all_user_expenses = Expense.query.filter_by(user_id=current_user.id).all()

    # Filter in python
    history_expenses = []
    target_month_expenses = []
    earliest_date = None
    
    for exp in all_user_expenses:
        try:
            exp_d = exp.expense_date
            if isinstance(exp_d, datetime):
                exp_d = exp_d.date()
            elif isinstance(exp_d, str):
                exp_d = datetime.strptime(exp_d, "%Y-%m-%d").date()
                
            if exp_d:
                if earliest_date is None or exp_d < earliest_date:
                    earliest_date = exp_d
                
                if start_date <= exp_d <= end_date:
                    history_expenses.append(exp)
                elif t_first_day <= exp_d <= t_end_day:
                    target_month_expenses.append(exp)
        except Exception:
            continue
            
    # Sum spending per category
    category_totals = {name: Decimal('0.00') for name in cat_names}
    for exp in history_expenses:
        try:
            cat_name = exp.category
            if cat_name in category_totals:
                category_totals[cat_name] += exp.amount
        except Exception:
            continue
            
    # Calculate months count of history
    if earliest_date:
        days_history = (t_first_day - earliest_date).days
        months_history = max(1, min(3, (days_history + 15) // 30))
    else:
        months_history = 3
        
    suggestions = {}
    for name, total in category_totals.items():
        suggestions[name] = round(total / Decimal(str(months_history)), 2)

    # Load existing budgets
    saved_budgets = {b.category_name: b.amount for b in Budget.query.filter_by(user_id=current_user.id, month=target_month).all()}

    # Calculate actual spending for target_month
    actual_spent = {name: Decimal('0.00') for name in cat_names}
    for exp in target_month_expenses:
        try:
            cat_name = exp.category
            if cat_name in actual_spent:
                actual_spent[cat_name] += exp.amount
        except Exception:
            continue

    # Prepare spending tracking items
    budget_vs_spent = []
    total_budgeted = Decimal('0.00')
    total_spent = Decimal('0.00')
    
    for cat in categories:
        b_amt = saved_budgets.get(cat.name, Decimal('0.00'))
        s_amt = actual_spent.get(cat.name, Decimal('0.00'))
        total_budgeted += b_amt
        total_spent += s_amt
        
        pct = 0
        if b_amt > 0:
            pct = int((s_amt / b_amt) * 100)
            
        budget_vs_spent.append({
            'category': cat.name,
            'color': cat.color,
            'budgeted': b_amt,
            'spent': s_amt,
            'pct': pct
        })

    budget_vs_spent.sort(key=lambda x: x['category'])

    return render_template(
        'dashboard/budget.html',
        target_month=target_month,
        categories=categories,
        suggestions=suggestions,
        saved_budgets=saved_budgets,
        budget_vs_spent=budget_vs_spent,
        total_budgeted=total_budgeted,
        total_spent=total_spent,
        months_history=months_history
    )


@dashboard.route('/docs')
def api_docs():
    """Renders the comprehensive in-app API developer portal and documentation."""
    openapi_path = os.path.join(current_app.root_path, 'static', 'openapi.json')
    openapi_data = {}
    if os.path.exists(openapi_path):
        try:
            with open(openapi_path, 'r', encoding='utf-8') as f:
                openapi_data = json.load(f)
        except Exception:
            pass
            
    paths = openapi_data.get('paths', {})
    grouped_endpoints = {}
    
    for path, methods_dict in paths.items():
        for method, details in methods_dict.items():
            tags = details.get('tags', ['General'])
            tag = tags[0] if tags else 'General'
            
            endpoint_info = {
                'path': path,
                'method': method.upper(),
                'summary': details.get('summary', ''),
                'description': details.get('description', ''),
                'parameters': details.get('parameters', []),
                'requestBody': details.get('requestBody', {}),
                'responses': details.get('responses', {}),
                'security': details.get('security', [])
            }
            
            if tag not in grouped_endpoints:
                grouped_endpoints[tag] = []
            grouped_endpoints[tag].append(endpoint_info)
            
    default_currency = current_user.default_currency if current_user.is_authenticated else 'USD'
    return render_template(
        'dashboard/api_docs.html',
        grouped_endpoints=grouped_endpoints,
        default_currency=default_currency
    )


@dashboard.route('/docs/swagger')
def api_swagger():
    """Renders the interactive Swagger UI interface referencing openapi.json."""
    return render_template('dashboard/swagger.html')


@dashboard.route('/docs/redoc')
def api_redoc():
    """Renders the modern ReDoc documentation viewer referencing openapi.json."""
    return render_template('dashboard/redoc.html')


from flask_wtf import FlaskForm
from wtforms import TextAreaField
from wtforms.validators import DataRequired, Length

class SupportForm(FlaskForm):
    """Form to submit contact support messages."""
    message = TextAreaField('Message', validators=[
        DataRequired(message="Message content cannot be empty."),
        Length(min=1, max=5000, message="Message must be between 1 and 5000 characters.")
    ])


@dashboard.route('/support', methods=['GET', 'POST'])
@login_required
def support():
    """Renders the contact support form and handles email dispatch to administrators."""
    form = SupportForm()
    if form.validate_on_submit():
        message_content = form.message.data.strip()
        try:
            from app.services.email_service import EmailService
            EmailService.send_support_email(current_user, message_content)
            
            # Log support request for auditing purposes
            AuditService.log(
                "Support Message Sent",
                f"User {current_user.username} (UUID: {current_user.id}) sent a support message."
            )
            
            flash("Your message has been sent successfully to the administration team.", "success")
            return redirect(url_for('dashboard.support'))
        except Exception as e:
            current_app.logger.error("Failed to send support email: %s", str(e))
            flash("An error occurred while sending your message. Please try again later.", "danger")
            
    return render_template('dashboard/support.html', form=form)

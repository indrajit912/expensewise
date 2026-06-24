import os
import re
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, abort, current_app
from flask_login import login_required, current_user
from datetime import datetime, timezone, timedelta
from app.extensions import db
from app.models.user import User, APIToken, AuditLog
from app.models.expense import Expense, Category, PaymentMethod
from app.services.analytics_service import AnalyticsService
from app.services.audit_service import AuditService

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
    daily_labels, daily_values = AnalyticsService.get_daily_trend(user_id, days=30)
    category_dist = AnalyticsService.get_category_distribution(user_id)
    
    # 3. Grab recent expenses (limit 5) for quick overview
    # Sort in memory since dates are encrypted in database
    expenses = Expense.query.filter_by(user_id=user_id).all()
    expenses.sort(key=lambda x: x.expense_date or datetime.min.date(), reverse=True)
    recent_expenses = expenses[:5]
        
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
        
        # Token Actions
        if action == 'generate_token':
            token_str = current_user.generate_token(expires_in_days=30)
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

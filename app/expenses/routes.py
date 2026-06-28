import os
import uuid
import json
from decimal import Decimal
from datetime import datetime, date
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, Response, session
from flask_login import login_required, current_user
from app.extensions import db
from app.models.expense import Expense, Category, PaymentMethod
from app.expenses.forms import ExpenseForm
from app.services.import_service import ImportService
from app.services.export_service import ExportService
from app.services.audit_service import AuditService

expenses = Blueprint('expenses', __name__, template_folder='templates')

class SimplePagination:
    """Manual in-memory pagination helper matching Flask-SQLAlchemy signature."""
    def __init__(self, items, page, per_page):
        self.total = len(items)
        self.page = page
        self.per_page = per_page
        self.pages = (self.total + per_page - 1) // per_page if self.total > 0 else 1
        
        start = (page - 1) * per_page
        end = start + per_page
        self.items = items[start:end]
        
        self.has_next = page < self.pages
        self.has_prev = page > 1

    @property
    def prev_num(self):
        return self.page - 1 if self.has_prev else None

    @property
    def next_num(self):
        return self.page + 1 if self.has_next else None

    def iter_pages(self, left_edge=2, left_current=2, right_current=5, right_edge=2):
        last = 0
        for num in range(1, self.pages + 1):
            if (
                num <= left_edge
                or (
                    num > self.page - left_current - 1
                    and num < self.page + right_current
                )
                or num > self.pages - right_edge
            ):
                if last + 1 != num:
                    yield None
                yield num
                last = num


@expenses.route('/')
@login_required
def list_expenses():
    """Lists expenses with in-memory filtering, sorting, and pagination, including full analysis and charting metrics."""
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()
    
    start_date_str = request.args.get('start_date', '').strip()
    end_date_str = request.args.get('end_date', '').strip()
    
    sort_by = request.args.get('sort_by', 'expense_date')
    order = request.args.get('order', 'desc')

    # Fetch all user expenses (since date/categories are encrypted in DB, we must filter in Python)
    from datetime import timedelta
    all_expenses = Expense.query.filter_by(user_id=current_user.id).all()
    filtered_items = []

    # Parse date filters
    start_date = None
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    end_date = None
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    for e in all_expenses:
        try:
            # 1. Category Filter
            if category_filter and e.category != category_filter:
                continue

            # 2. Date Filter
            e_date = e.expense_date
            if start_date and e_date < start_date:
                continue
            if end_date and e_date > end_date:
                continue

            # 3. Search text filter (case-insensitive)
            if search_query:
                q = search_query.lower()
                desc = (e.description or '').lower()
                payee = (e.payee or '').lower()
                if q not in desc and q not in payee:
                    continue

            filtered_items.append(e)
        except Exception:
            # Skip records if key is locked or decryption fails
            continue

    # =========================================================================
    #                   ANALYTICS & INSIGHTS CALCULATIONS
    # =========================================================================
    total_spending = Decimal('0.00')
    num_expenses = len(filtered_items)
    highest_expense = None
    lowest_expense = None
    
    daily_spending_map = {}
    weekly_spending_map = {}
    monthly_spending_map = {}
    
    category_spending_map = {}
    category_counts_map = {}
    
    payment_spending_map = {}
    payment_counts_map = {}

    for e in filtered_items:
        amount = e.amount or Decimal('0.00')
        total_spending += amount
        
        # Min/Max single expense
        if highest_expense is None or amount > (highest_expense.amount or Decimal('0.00')):
            highest_expense = e
        if lowest_expense is None or amount < (lowest_expense.amount or Decimal('0.00')):
            lowest_expense = e
            
        # Grouping by date
        d = e.expense_date
        if d:
            # Daily
            day_str = d.isoformat()
            daily_spending_map[day_str] = daily_spending_map.get(day_str, Decimal('0.00')) + amount
            
            # Weekly
            start_of_week = d - timedelta(days=d.weekday())
            week_str = f"Week of {start_of_week.strftime('%b %d, %Y')}"
            weekly_spending_map[week_str] = weekly_spending_map.get(week_str, Decimal('0.00')) + amount
            
            # Monthly
            month_str = d.strftime('%B %Y')
            monthly_spending_map[month_str] = monthly_spending_map.get(month_str, Decimal('0.00')) + amount
            
        # Grouping by category
        cat = e.category or 'Other'
        category_spending_map[cat] = category_spending_map.get(cat, Decimal('0.00')) + amount
        category_counts_map[cat] = category_counts_map.get(cat, 0) + 1
        
        # Grouping by payment mode
        pm = e.payment_mode or 'Other'
        payment_spending_map[pm] = payment_spending_map.get(pm, Decimal('0.00')) + amount
        payment_counts_map[pm] = payment_counts_map.get(pm, 0) + 1

    # Date range duration logic
    dates = [e.expense_date for e in filtered_items if e.expense_date]
    min_date = min(dates) if dates else None
    max_date = max(dates) if dates else None
    
    range_days = 0
    if start_date and end_date:
        range_days = (end_date - start_date).days + 1
    elif min_date and max_date:
        range_days = (max_date - min_date).days + 1
    elif min_date:
        range_days = 1
        
    avg_expense = total_spending / num_expenses if num_expenses > 0 else Decimal('0.00')
    avg_daily = total_spending / range_days if range_days > 0 else Decimal('0.00')
    avg_weekly = avg_daily * Decimal('7') if range_days > 0 else Decimal('0.00')
    avg_monthly = avg_daily * Decimal('30.44') if range_days > 0 else Decimal('0.00')

    # Extremes date-based
    highest_day = max(daily_spending_map.items(), key=lambda x: x[1], default=('N/A', Decimal('0.00')))
    lowest_day = min(daily_spending_map.items(), key=lambda x: x[1], default=('N/A', Decimal('0.00')))
    highest_week = max(weekly_spending_map.items(), key=lambda x: x[1], default=('N/A', Decimal('0.00')))
    highest_month = max(monthly_spending_map.items(), key=lambda x: x[1], default=('N/A', Decimal('0.00')))

    # Category insights
    top_cat = 'N/A'
    top_cat_amount = Decimal('0.00')
    top_cat_pct = 0.0
    
    lowest_cat = 'N/A'
    lowest_cat_amount = Decimal('0.00')
    lowest_cat_pct = 0.0
    
    if category_spending_map:
        t_cat, t_amt = max(category_spending_map.items(), key=lambda x: x[1])
        top_cat = t_cat
        top_cat_amount = t_amt
        if total_spending > 0:
            top_cat_pct = float((t_amt / total_spending) * 100)
            
        l_cat, l_amt = min(category_spending_map.items(), key=lambda x: x[1])
        lowest_cat = l_cat
        lowest_cat_amount = l_amt
        if total_spending > 0:
            lowest_cat_pct = float((l_amt / total_spending) * 100)

    # Payment method insights
    most_used_pm = 'N/A'
    most_used_pm_count = 0
    most_used_pm_amount = Decimal('0.00')
    
    least_used_pm = 'N/A'
    least_used_pm_count = 0
    least_used_pm_amount = Decimal('0.00')
    
    highest_spending_pm = 'N/A'
    highest_spending_pm_count = 0
    highest_spending_pm_amount = Decimal('0.00')
    
    lowest_spending_pm = 'N/A'
    lowest_spending_pm_count = 0
    lowest_spending_pm_amount = Decimal('0.00')
    
    if payment_counts_map:
        mu_pm, mu_cnt = max(payment_counts_map.items(), key=lambda x: x[1])
        most_used_pm = mu_pm
        most_used_pm_count = mu_cnt
        most_used_pm_amount = payment_spending_map.get(mu_pm, Decimal('0.00'))
        
        lu_pm, lu_cnt = min(payment_counts_map.items(), key=lambda x: x[1])
        least_used_pm = lu_pm
        least_used_pm_count = lu_cnt
        least_used_pm_amount = payment_spending_map.get(lu_pm, Decimal('0.00'))
        
    if payment_spending_map:
        hs_pm, hs_amt = max(payment_spending_map.items(), key=lambda x: x[1])
        highest_spending_pm = hs_pm
        highest_spending_pm_amount = hs_amt
        highest_spending_pm_count = payment_counts_map.get(hs_pm, 0)
        
        ls_pm, ls_amt = min(payment_spending_map.items(), key=lambda x: x[1])
        lowest_spending_pm = ls_pm
        lowest_spending_pm_amount = ls_amt
        lowest_spending_pm_count = payment_counts_map.get(ls_pm, 0)

    # Preceding period trend calculations
    today_dt = date.today()
    if start_date:
        current_start = start_date
    else:
        all_dates = [e.expense_date for e in all_expenses if e.expense_date]
        current_start = min(all_dates) if all_dates else today_dt - timedelta(days=29)
        
    if end_date:
        current_end = end_date
    else:
        all_dates = [e.expense_date for e in all_expenses if e.expense_date]
        current_end = max(all_dates) if all_dates else today_dt

    delta_days = (current_end - current_start).days + 1
    preceding_start = current_start - timedelta(days=delta_days)
    preceding_end = current_start - timedelta(days=1)
    
    preceding_total = Decimal('0.00')
    preceding_category_spending = {}
    
    for e in all_expenses:
        try:
            if category_filter and e.category != category_filter:
                continue
            if search_query:
                q = search_query.lower()
                desc = (e.description or '').lower()
                payee = (e.payee or '').lower()
                if q not in desc and q not in payee:
                    continue
                    
            e_date = e.expense_date
            if preceding_start <= e_date <= preceding_end:
                amount = e.amount or Decimal('0.00')
                preceding_total += amount
                cat = e.category or 'Other'
                preceding_category_spending[cat] = preceding_category_spending.get(cat, Decimal('0.00')) + amount
        except Exception:
            continue
            
    trend_spending_diff = total_spending - preceding_total
    if preceding_total > 0:
        trend_spending_pct = float((trend_spending_diff / preceding_total) * 100)
    else:
        trend_spending_pct = 100.0 if total_spending > 0 else 0.0
        
    trend_category_changes = []
    union_categories = set(category_spending_map.keys()).union(set(preceding_category_spending.keys()))
    for cat in union_categories:
        curr_val = category_spending_map.get(cat, Decimal('0.00'))
        prec_val = preceding_category_spending.get(cat, Decimal('0.00'))
        cat_diff = curr_val - prec_val
        if prec_val > 0:
            cat_pct = float((cat_diff / prec_val) * 100)
        else:
            cat_pct = 100.0 if curr_val > 0 else 0.0
        trend_category_changes.append({
            'category': cat,
            'current': curr_val,
            'preceding': prec_val,
            'diff': cat_diff,
            'pct': cat_pct
        })
    trend_category_changes.sort(key=lambda x: abs(x['diff']), reverse=True)

    # =========================================================================
    #                   CHART DATAS GENERATION
    # =========================================================================
    trend_dates = []
    if range_days > 0 and range_days <= 100:
        curr = current_start
        while curr <= current_end:
            trend_dates.append(curr)
            curr += timedelta(days=1)
    else:
        date_set = set()
        for e in filtered_items:
            if e.expense_date:
                date_set.add(e.expense_date)
        trend_dates = sorted(list(date_set))
        
    trend_labels = [d.strftime('%b %d, %Y') for d in trend_dates]
    trend_values = [float(daily_spending_map.get(d.isoformat(), Decimal('0.00'))) for d in trend_dates]

    # Dynamic colors fetch from user categories & payment methods
    db_categories = Category.query.filter_by(user_id=current_user.id).all()
    cat_color_map = {c.name: c.color for c in db_categories}
    
    cat_chart_labels = list(category_spending_map.keys())
    cat_chart_values = [float(v) for v in category_spending_map.values()]
    cat_chart_colors = [cat_color_map.get(cat, '#475569') for cat in cat_chart_labels]

    db_payment_methods = PaymentMethod.query.filter_by(user_id=current_user.id).all()
    pm_color_map = {pm.name: pm.color for pm in db_payment_methods}
    
    pm_chart_labels = list(payment_spending_map.keys())
    pm_chart_values = [float(v) for v in payment_spending_map.values()]
    pm_chart_colors = [pm_color_map.get(pm, '#475569') for pm in pm_chart_labels]

    # In-memory sorting for final registry table display
    if sort_by == 'amount':
        key_func = lambda x: x.amount or Decimal('0.00')
    elif sort_by == 'category':
        key_func = lambda x: x.category or ''
    elif sort_by == 'payee':
        key_func = lambda x: x.payee or ''
    elif sort_by == 'payment_mode':
        key_func = lambda x: x.payment_mode or ''
    else:
        key_func = lambda x: x.expense_date or date.min

    filtered_items.sort(key=key_func, reverse=(order == 'desc'))

    # Paginate manually
    pagination = SimplePagination(filtered_items, page, 15)
    expense_items = pagination.items

    return render_template(
        'expenses/list.html',
        expenses=expense_items,
        pagination=pagination,
        search=search_query,
        category=category_filter,
        start_date=start_date_str,
        end_date=end_date_str,
        sort_by=sort_by,
        order=order,
        
        # Insights summaries
        total_spending=total_spending,
        num_expenses=num_expenses,
        avg_expense=avg_expense,
        avg_daily=avg_daily,
        avg_weekly=avg_weekly,
        avg_monthly=avg_monthly,
        highest_expense=highest_expense,
        lowest_expense=lowest_expense,
        
        # Date extremes
        highest_day=highest_day,
        lowest_day=lowest_day,
        highest_week=highest_week,
        highest_month=highest_month,
        
        # Category insights
        top_cat=top_cat,
        top_cat_amount=top_cat_amount,
        top_cat_pct=top_cat_pct,
        lowest_cat=lowest_cat,
        lowest_cat_amount=lowest_cat_amount,
        lowest_cat_pct=lowest_cat_pct,
        
        # Payment insights
        most_used_pm=most_used_pm,
        most_used_pm_count=most_used_pm_count,
        most_used_pm_amount=most_used_pm_amount,
        least_used_pm=least_used_pm,
        least_used_pm_count=least_used_pm_count,
        least_used_pm_amount=least_used_pm_amount,
        highest_spending_pm=highest_spending_pm,
        highest_spending_pm_count=highest_spending_pm_count,
        highest_spending_pm_amount=highest_spending_pm_amount,
        lowest_spending_pm=lowest_spending_pm,
        lowest_spending_pm_count=lowest_spending_pm_count,
        lowest_spending_pm_amount=lowest_spending_pm_amount,
        
        # Comparison trends
        preceding_start=preceding_start,
        preceding_end=preceding_end,
        trend_spending_diff=trend_spending_diff,
        trend_spending_pct=trend_spending_pct,
        trend_category_changes=trend_category_changes,
        
        # Charts datasets
        trend_labels=trend_labels,
        trend_values=trend_values,
        cat_chart_labels=cat_chart_labels,
        cat_chart_values=cat_chart_values,
        cat_chart_colors=cat_chart_colors,
        pm_chart_labels=pm_chart_labels,
        pm_chart_values=pm_chart_values,
        pm_chart_colors=pm_chart_colors
    )


@expenses.route('/add', methods=['GET', 'POST'])
@login_required
def add_expense():
    """Adds a new expense record (automatically encrypted on write)."""
    form = ExpenseForm()
    form.category.choices = [(c.name, c.name) for c in Category.query.filter_by(user_id=current_user.id).order_by(Category.name).all()]
    form.payment_mode.choices = [('', 'Select Payment Mode (Optional)')] + [(p.name, p.name) for p in PaymentMethod.query.filter_by(user_id=current_user.id).order_by(PaymentMethod.name).all()]
    
    if request.method == 'GET':
        form.currency.data = current_user.default_currency

    if form.validate_on_submit():
        rate = Decimal('1.0000')
        is_valid = True
        
        if form.currency.data != current_user.default_currency:
            if not form.conversion_rate.data:
                form.conversion_rate.errors.append("Conversion rate is required for different currencies.")
                is_valid = False
            else:
                try:
                    rate = Decimal(str(form.conversion_rate.data))
                    if rate <= Decimal('0.0000'):
                        form.conversion_rate.errors.append("Conversion rate must be greater than zero.")
                        is_valid = False
                except Exception:
                    form.conversion_rate.errors.append("Invalid conversion rate.")
                    is_valid = False
        else:
            rate = Decimal('1.0000')

        if is_valid:
            orig_amount = form.amount.data
            canonical_amount = orig_amount * rate
            
            expense = Expense(
                user_id=current_user.id,
                amount=canonical_amount,
                category=form.category.data,
                expense_date=form.expense_date.data,
                payee=form.payee.data.strip() or None,
                payment_mode=form.payment_mode.data or None,
                description=form.description.data.strip() or None,
                original_amount=orig_amount,
                original_currency=form.currency.data,
                conversion_rate=rate,
                converted_amount=canonical_amount
            )
            db.session.add(expense)
            db.session.commit()
            
            # Log action to audit logs
            AuditService.log("Expense Creation", f"Created expense of {expense.amount:.2f} {current_user.default_currency} under {expense.category}")
            
            flash('Expense recorded successfully.', 'success')
            return redirect(url_for('expenses.list_expenses'))
            
    return render_template('expenses/add_edit.html', form=form, title="Add Expense")


@expenses.route('/edit/<uuid_str>', methods=['GET', 'POST'])
@login_required
def edit_expense(uuid_str):
    """Edits an existing expense record."""
    expense = Expense.query.filter_by(id=uuid_str, user_id=current_user.id).first_or_404()
    form = ExpenseForm()
    form.category.choices = [(c.name, c.name) for c in Category.query.filter_by(user_id=current_user.id).order_by(Category.name).all()]
    form.payment_mode.choices = [('', 'Select Payment Mode (Optional)')] + [(p.name, p.name) for p in PaymentMethod.query.filter_by(user_id=current_user.id).order_by(PaymentMethod.name).all()]
    
    if request.method == 'GET':
        form.amount.data = expense.original_amount
        form.currency.data = expense.original_currency
        form.conversion_rate.data = expense.conversion_rate
        form.category.data = expense.category
        form.expense_date.data = expense.expense_date
        form.payee.data = expense.payee
        form.payment_mode.data = expense.payment_mode
        form.description.data = expense.description
        
    if form.validate_on_submit():
        rate = Decimal('1.0000')
        is_valid = True
        
        if form.currency.data != current_user.default_currency:
            if not form.conversion_rate.data:
                form.conversion_rate.errors.append("Conversion rate is required for different currencies.")
                is_valid = False
            else:
                try:
                    rate = Decimal(str(form.conversion_rate.data))
                    if rate <= Decimal('0.0000'):
                        form.conversion_rate.errors.append("Conversion rate must be greater than zero.")
                        is_valid = False
                except Exception:
                    form.conversion_rate.errors.append("Invalid conversion rate.")
                    is_valid = False
        else:
            rate = Decimal('1.0000')

        if is_valid:
            old_amount = expense.amount
            old_category = expense.category
            
            orig_amount = form.amount.data
            canonical_amount = orig_amount * rate
            
            expense.amount = canonical_amount
            expense.category = form.category.data
            expense.expense_date = form.expense_date.data
            expense.payee = form.payee.data.strip() or None
            expense.payment_mode = form.payment_mode.data or None
            expense.description = form.description.data.strip() or None
            
            expense.original_amount = orig_amount
            expense.original_currency = form.currency.data
            expense.conversion_rate = rate
            expense.converted_amount = canonical_amount
            
            db.session.commit()
            
            # Log modification to audit logs
            AuditService.log(
                "Expense Modification", 
                f"Modified expense {uuid_str}: Changed amount from {old_amount:.2f} to {expense.amount:.2f}, category '{old_category}' to '{expense.category}'"
            )
            
            flash('Expense updated successfully.', 'success')
            return redirect(url_for('expenses.list_expenses'))
            
    return render_template('expenses/add_edit.html', form=form, title="Edit Expense", expense=expense)


@expenses.route('/delete/<uuid_str>', methods=['POST'])
@login_required
def delete_expense(uuid_str):
    """Deletes an expense record."""
    expense = Expense.query.filter_by(id=uuid_str, user_id=current_user.id).first_or_404()
    amount = expense.amount
    category = expense.category
    
    db.session.delete(expense)
    db.session.commit()
    
    # Log deletion to audit logs
    AuditService.log("Expense Deletion", f"Deleted expense of ${amount:.2f} under {category}")
    
    flash('Expense deleted successfully.', 'success')
    return redirect(url_for('expenses.list_expenses'))


@expenses.route('/import', methods=['GET', 'POST'])
@login_required
def import_backup():
    """Handles JSON backup file uploads, preparing a staging file."""
    if request.method == 'POST':
        if 'backup_file' not in request.files:
            flash('No file part in the request', 'danger')
            return redirect(request.url)
            
        file = request.files['backup_file']
        if file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(request.url)
            
        if file and file.filename.endswith('.json'):
            filename = f"backup_{current_user.id}_{uuid.uuid4().hex}.json"
            upload_folder = os.path.join(current_app.instance_path, 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)
            
            # Save configuration parameters to session for preview
            session['import_file'] = file_path
            session['import_file_type'] = 'json'
            return redirect(url_for('expenses.preview_import'))
        else:
            flash('Invalid file format. Please upload a standard JSON backup file.', 'danger')
            
    return render_template('expenses/import_backup.html')


@expenses.route('/import/preview', methods=['GET', 'POST'])
@login_required
def preview_import():
    """Generates preview statistics of the uploaded backup file before committing changes."""
    file_path = session.get('import_file')
    
    if not file_path or not os.path.exists(file_path):
        flash('No file uploaded or session expired. Please upload again.', 'warning')
        return redirect(url_for('expenses.import_backup'))

    is_valid = True
    checklist = None
    error_msg = None

    try:
        # Load JSON content
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        headers = ['Amount', 'Category', 'Payee', 'Payment Mode', 'Date', 'Description']
        preview_rows = []
        
        if isinstance(data, dict):
            # v2.0 backup JSON
            is_valid, checklist, error_msg = ImportService.validate_backup_json(data)
            
            cat_map = {c['id']: c['name'] for c in data.get('categories', [])}
            pm_map = {pm['id']: pm['name'] for pm in data.get('payment_methods', [])}
            
            for r in data.get('expenses', [])[:8]:
                preview_rows.append({
                    'Amount': r.get('amount'),
                    'Category': cat_map.get(r.get('category_id'), 'Other'),
                    'Payee': r.get('payee') or '-',
                    'Payment Mode': pm_map.get(r.get('payment_method_id')) if r.get('payment_method_id') else '-',
                    'Date': r.get('expense_date'),
                    'Description': r.get('description') or '-'
                })
            total_rows = len(data.get('expenses', []))
        elif isinstance(data, list):
            # legacy list JSON
            for r in data[:8]:
                preview_rows.append({
                    'Amount': r.get('amount'),
                    'Category': r.get('category') or r.get('category_id') or 'Other',
                    'Payee': r.get('payee') or '-',
                    'Payment Mode': r.get('payment_mode') or r.get('payment_method_id') or '-',
                    'Date': r.get('expense_date') or r.get('date'),
                    'Description': r.get('description') or '-'
                })
            total_rows = len(data)
        else:
            is_valid = False
            total_rows = 0
            error_msg = "Invalid JSON structure. Root element must be an object or a list."
            
    except Exception as e:
        flash(f"Error reading staging file: {str(e)}", 'danger')
        if os.path.exists(file_path):
            os.remove(file_path)
        session.pop('import_file', None)
        session.pop('import_file_type', None)
        return redirect(url_for('expenses.import_backup'))

    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'confirm':
            # Block confirm if validation failed
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    chk_data = json.load(f)
                if isinstance(chk_data, dict):
                    is_valid_chk, _, error_msg_chk = ImportService.validate_backup_json(chk_data)
                    if not is_valid_chk:
                        flash(f"Import failed: Validation error: {error_msg_chk}", 'danger')
                        return redirect(url_for('expenses.import_backup'))
            except Exception as e:
                flash(f"Import failed: Invalid file: {str(e)}", 'danger')
                return redirect(url_for('expenses.import_backup'))

            # Perform import
            result = ImportService.import_standard_json(current_user.id, file_path)
                
            os.remove(file_path)
            session.pop('import_file', None)
            session.pop('import_file_type', None)
            
            if result.get('success'):
                # Audit log entry
                AuditService.log(
                    "Import", 
                    f"User imported data via JSON: Added {result['success_count']} expenses, skipped {result['duplicate_count']} duplicates, errors {result['error_count']}"
                )
                
                flash(
                    f"Import completed successfully! "
                    f"Added: {result['success_count']}, "
                    f"Skipped Duplicates: {result['duplicate_count']}, "
                    f"Errors: {result['error_count']}", 
                    'success'
                )
            else:
                flash(f"Import failed: {result.get('error')}", 'danger')
                
            return redirect(url_for('expenses.list_expenses'))
            
        elif action == 'cancel':
            # Dismiss staging files
            os.remove(file_path)
            session.pop('import_file', None)
            session.pop('import_file_type', None)
            flash('Import cancelled.', 'info')
            return redirect(url_for('expenses.import_backup'))

    return render_template(
        'expenses/preview_import.html', 
        headers=headers, 
        rows=preview_rows, 
        total_rows=total_rows,
        is_valid=is_valid,
        checklist=checklist,
        error_msg=error_msg,
        file_type='json'
    )


@expenses.route('/export')
@login_required
def export_expenses():
    """Generates file attachments to export current user's expenses (records in audit logs)."""
    # Grab all user expenses
    expenses_list = Expense.query.filter_by(user_id=current_user.id).all()
    # Sort in memory
    expenses_list.sort(key=lambda x: x.expense_date or date.min, reverse=True)
    
    # Audit log entry
    AuditService.log("Export", "User exported account data in JSON format")
        
    json_data = ExportService.generate_json(current_user)
    return Response(
        json_data,
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment;filename=expenses_export.json'}
    )

import re
from decimal import Decimal
from datetime import datetime, date, timezone, timedelta
from flask import request, jsonify, g
from app.api import api
from app.api.decorators import token_required
from app.extensions import db
from app.models.expense import Expense, Category, Budget

@api.route('/v1/budget', methods=['GET'])
@token_required
def api_get_budget():
    """Retrieves standard suggestions, saved budgets, and actual spending comparison for target month."""
    now = datetime.now(timezone.utc)
    if now.month == 12:
        upcoming_year = now.year + 1
        upcoming_month = 1
    else:
        upcoming_year = now.year
        upcoming_month = now.month + 1
    default_month = f"{upcoming_year}-{upcoming_month:02d}"
    
    target_month = request.args.get('month', default_month)
    if not re.match(r'^\d{4}-\d{2}$', target_month):
        target_month = default_month

    # Retrieve categories
    categories = Category.query.filter_by(user_id=g.current_user.id).order_by(Category.name).all()
    cat_names = [c.name for c in categories]

    # Calculate t_first_day and standard ranges
    try:
        t_year, t_month = map(int, target_month.split('-'))
        t_first_day = date(t_year, t_month, 1)
    except Exception:
        t_first_day = date(now.year, now.month, 1)
        
    hist_start_month = t_first_day.month - 3
    hist_start_year = t_first_day.year
    while hist_start_month <= 0:
        hist_start_month += 12
        hist_start_year -= 1
    start_date = date(hist_start_year, hist_start_month, 1)
    end_date = t_first_day - timedelta(days=1)
    
    next_month = t_first_day.month + 1
    next_year = t_first_day.year
    if next_month > 12:
        next_month = 1
        next_year += 1
    t_end_day = date(next_year, next_month, 1) - timedelta(days=1)

    # Fetch all user expenses (since they are encrypted, decrypt in memory)
    all_user_expenses = Expense.query.filter_by(user_id=g.current_user.id).all()

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

    category_totals = {name: Decimal('0.00') for name in cat_names}
    for exp in history_expenses:
        try:
            cat_name = exp.category
            if cat_name in category_totals:
                category_totals[cat_name] += exp.amount
        except Exception:
            continue

    if earliest_date:
        days_history = (t_first_day - earliest_date).days
        months_history = max(1, min(3, (days_history + 15) // 30))
    else:
        months_history = 3

    suggestions = {}
    for name, total in category_totals.items():
        suggestions[name] = float(round(total / Decimal(str(months_history)), 2))

    saved_budgets = {b.category_name: float(b.amount) for b in Budget.query.filter_by(user_id=g.current_user.id, month=target_month).all()}

    actual_spent = {name: Decimal('0.00') for name in cat_names}
    for exp in target_month_expenses:
        try:
            cat_name = exp.category
            if cat_name in actual_spent:
                actual_spent[cat_name] += exp.amount
        except Exception:
            continue

    budget_vs_spent = []
    total_budgeted = 0.0
    total_spent = 0.0

    for cat in categories:
        b_amt = saved_budgets.get(cat.name, 0.0)
        s_amt = float(actual_spent.get(cat.name, Decimal('0.00')))
        total_budgeted += b_amt
        total_spent += s_amt
        
        pct = 0
        if b_amt > 0:
            pct = int((s_amt / b_amt) * 100)

        budget_vs_spent.append({
            'category': cat.name,
            'color': cat.color,
            'budgeted': b_amt,
            'suggested': suggestions.get(cat.name, 0.0),
            'spent': s_amt,
            'pct': pct
        })

    budget_vs_spent.sort(key=lambda x: x['category'])

    return jsonify({
        'month': target_month,
        'total_budgeted': total_budgeted,
        'total_spent': total_spent,
        'months_history': months_history,
        'categories': budget_vs_spent
    }), 200

@api.route('/v1/budget', methods=['POST'])
@token_required
def api_post_budget():
    """Saves or updates budget settings for specified month."""
    data = request.get_json() or {}
    target_month = data.get('month', '').strip()
    if not target_month or not re.match(r'^\d{4}-\d{2}$', target_month):
        return jsonify({'error': 'Bad Request', 'message': 'Valid target month YYYY-MM is required.'}), 400

    budgets_dict = data.get('budgets', {})
    if not isinstance(budgets_dict, dict):
        return jsonify({'error': 'Bad Request', 'message': 'budgets parameter must be a JSON dictionary.'}), 400

    # Ensure categories are loaded to match names
    categories = Category.query.filter_by(user_id=g.current_user.id).all()
    cat_names = {c.name for c in categories}

    for cat_name, amt in budgets_dict.items():
        if cat_name not in cat_names:
            continue
        
        if amt is None or str(amt).strip() == '':
            # Clear budget limit
            entry = Budget.query.filter_by(
                user_id=g.current_user.id,
                month=target_month,
                category_name=cat_name
            ).first()
            if entry:
                db.session.delete(entry)
        else:
            try:
                amt_val = Decimal(str(amt))
                if amt_val < 0:
                    amt_val = Decimal('0.00')
            except Exception:
                amt_val = Decimal('0.00')

            entry = Budget.query.filter_by(
                user_id=g.current_user.id,
                month=target_month,
                category_name=cat_name
            ).first()

            if entry:
                entry.amount = amt_val
            else:
                entry = Budget(
                    user_id=g.current_user.id,
                    month=target_month,
                    category_name=cat_name,
                    amount=amt_val
                )
                db.session.add(entry)

    db.session.commit()
    return jsonify({'message': f'Budgets for {target_month} have been successfully updated.'}), 200

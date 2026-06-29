from flask import Blueprint, render_template, request, session
from flask_login import login_required, current_user
from app.services.analytics_service import AnalyticsService
from datetime import date, timedelta

analytics = Blueprint('analytics', __name__, template_folder='templates')

@analytics.route('/')
@login_required
def index():
    """Compiles detailed historical analytics, growth rates, category distribution, and predictions."""
    user_id = current_user.id
    
    # Resolve reporting period in a single place and persist in session
    months = request.args.get('months', type=int)
    if months is not None:
        if months <= 0:
            months = 6
        session['analytics_months'] = months
    else:
        months = session.get('analytics_months', 6)
        
    # 1. Fetch aggregate history
    history = AnalyticsService.get_monthly_spending_history(user_id, months_back=months)
    
    # 2. Get comparative changes vs prior month
    comp_metrics = AnalyticsService.get_comparison_metrics(user_id)
    
    # 3. Get category allocation ratios
    today = date.today()
    start_date = today.replace(day=1) - timedelta(days=30 * (months - 1))
    start_date = start_date.replace(day=1) 
    category_dist = AnalyticsService.get_category_distribution(user_id=user_id, start_date=start_date, end_date=today)
    
    # 4. Predict spending for the next month
    forecast_spending = AnalyticsService.predict_next_month_spending(user_id)
    
    # Separate history dictionary into lists for Chart.js rendering
    history_months = list(history.keys())
    history_amounts = list(history.values())
    
    return render_template(
        'analytics/index.html',
        history_months=history_months,
        history_amounts=history_amounts,
        comp_metrics=comp_metrics,
        category_dist=category_dist,
        forecast_spending=forecast_spending,
        selected_months=months
    )

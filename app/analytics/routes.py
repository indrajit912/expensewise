from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.services.analytics_service import AnalyticsService

analytics = Blueprint('analytics', __name__, template_folder='templates')

@analytics.route('/')
@login_required
def index():
    """Compiles detailed historical analytics, growth rates, category distribution, and predictions."""
    user_id = current_user.id
    
    # 1. Fetch 6-month aggregate history
    history = AnalyticsService.get_monthly_spending_history(user_id, months_back=6)
    
    # 2. Get comparative changes vs prior month
    comp_metrics = AnalyticsService.get_comparison_metrics(user_id)
    
    # 3. Get category allocation ratios
    category_dist = AnalyticsService.get_category_distribution(user_id)
    
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
        forecast_spending=forecast_spending
    )

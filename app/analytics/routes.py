from flask import Blueprint, render_template, request, session, jsonify
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


@analytics.route('/api/trends-over-time')
@login_required
def get_trends_over_time_json():
    """Returns JSON spending trends for AJAX frontend requests."""
    user_id = current_user.id
    
    interval = request.args.get('interval', 'month').strip().lower()
    start_date_str = request.args.get('start_date', '').strip()
    end_date_str = request.args.get('end_date', '').strip()
    
    try:
        moving_average_window = int(request.args.get('moving_average_window', '3').strip())
    except ValueError:
        moving_average_window = 3
        
    from datetime import datetime
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
            
    try:
        trends = AnalyticsService.get_spending_trends(
            user_id,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
            moving_average_window=moving_average_window
        )
        return jsonify(trends), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500

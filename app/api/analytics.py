from flask import jsonify, g
from app.api import api
from app.api.decorators import token_required
from app.services.analytics_service import AnalyticsService

@api.route('/v1/analytics/summary', methods=['GET'])
@token_required
def api_analytics_summary():
    """Endpoint returning key financial indicators (rolling 30-day summary, volatility, comparisons)."""
    user_id = g.current_user.id
    
    try:
        metrics = AnalyticsService.get_summary_metrics(user_id)
        comp_metrics = AnalyticsService.get_comparison_metrics(user_id)
        
        return jsonify({
            'metrics': metrics,
            'comparison': comp_metrics,
            'default_currency': g.current_user.default_currency
        }), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@api.route('/v1/analytics/trends', methods=['GET'])
@token_required
def api_analytics_trends():
    """Endpoint returning category allocations and 6-month historical totals."""
    user_id = g.current_user.id
    
    try:
        category_dist = AnalyticsService.get_category_distribution(user_id)
        history = AnalyticsService.get_monthly_spending_history(user_id, months_back=6)
        daily_labels, daily_values = AnalyticsService.get_daily_trend(user_id, days=30)
        
        return jsonify({
            'category_distribution': category_dist,
            'monthly_history': history,
            'daily_trend': {
                'labels': daily_labels,
                'values': daily_values
            },
            'default_currency': g.current_user.default_currency
        }), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@api.route('/v1/analytics/forecast', methods=['GET'])
@token_required
def api_analytics_forecast():
    """Endpoint returning linear regression predictions for next month's total spending."""
    user_id = g.current_user.id
    
    try:
        forecast_spending = AnalyticsService.predict_next_month_spending(user_id)
        
        return jsonify({
            'predicted_next_month_spending': forecast_spending,
            'method': 'Ordinary Least Squares (OLS) Linear Regression over monthly totals, fallback to rolling daily rate.',
            'default_currency': g.current_user.default_currency
        }), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500

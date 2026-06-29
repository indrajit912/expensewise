from flask import jsonify, g
from app.api import api
from app.api.decorators import token_required
from app.services.analytics_service import AnalyticsService

@api.route('/v1/analytics/summary', methods=['GET'])
@token_required
def api_analytics_summary():
    """Endpoint returning key financial indicators, supporting custom filters and breakdowns."""
    user_id = g.current_user.id
    
    from flask import request
    from datetime import datetime
    from decimal import Decimal
    from app.models.expense import Expense
    
    start_date_str = request.args.get('start_date', '').strip()
    end_date_str = request.args.get('end_date', '').strip()
    category_filter = request.args.get('category', '').strip()
    
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
            
    # If custom filter dates or categories are provided, compute customized summary metrics
    if start_date or end_date or category_filter:
        filtered = Expense.get_filtered_expenses(
            user_id=user_id,
            category=category_filter,
            start_date=start_date,
            end_date=end_date
        )
        
        total_spending = Decimal('0.00')
        category_spending = {}
        category_counts = {}
        dates = []
        
        for e in filtered:
            amt = e.amount or Decimal('0.00')
            total_spending += amt
            
            cat = e.category or 'Other'
            category_spending[cat] = category_spending.get(cat, Decimal('0.00')) + amt
            category_counts[cat] = category_counts.get(cat, 0) + 1
            if e.expense_date:
                dates.append(e.expense_date)
                
        total_count = len(filtered)
        avg_amount = float(total_spending / total_count) if total_count > 0 else 0.0
        
        # Calculate range days for daily average
        min_date = min(dates) if dates else None
        max_date = max(dates) if dates else None
        
        range_days = 0
        if start_date and end_date:
            range_days = (end_date - start_date).days + 1
        elif min_date and max_date:
            range_days = (max_date - min_date).days + 1
        elif min_date:
            range_days = 1
            
        daily_average = float(total_spending / range_days) if range_days > 0 else 0.0
        
        # Format category breakdown list
        category_list = []
        for cat, amt in category_spending.items():
            cnt = category_counts.get(cat, 0)
            pct = float((amt / total_spending) * 100) if total_spending > 0 else 0.0
            category_list.append({
                'category': cat,
                'total': float(amt),
                'count': cnt,
                'pct': pct
            })
        category_list.sort(key=lambda x: x['total'], reverse=True)
        
        return jsonify({
            'custom': True,
            'start_date': start_date.isoformat() if start_date else (min_date.isoformat() if min_date else None),
            'end_date': end_date.isoformat() if end_date else (max_date.isoformat() if max_date else None),
            'metrics': {
                'total_spending': float(total_spending),
                'total_count': total_count,
                'average_transaction': avg_amount,
                'daily_average': daily_average
            },
            'categories': category_list,
            'default_currency': g.current_user.default_currency
        }), 200
        
    try:
        metrics = AnalyticsService.get_summary_metrics(user_id)
        comp_metrics = AnalyticsService.get_comparison_metrics(user_id)
        
        # Extract rolling 30-day category allocations and counts
        category_dist = AnalyticsService.get_category_distribution(user_id)
        from collections import Counter
        from datetime import date, timedelta
        
        all_expenses = Expense.query.filter_by(user_id=user_id).all()
        today = date.today()
        thirty_days_ago = today - timedelta(days=30)
        
        last_30_days_exps = []
        for e in all_expenses:
            try:
                if e.expense_date and thirty_days_ago <= e.expense_date <= today:
                    last_30_days_exps.append(e)
            except:
                pass
                
        cat_counts = Counter(e.category or 'Other' for e in last_30_days_exps)
        total_spending = sum(category_dist.values())
        
        category_list = []
        for cat, amt in category_dist.items():
            cnt = cat_counts.get(cat, 0)
            pct = (amt / total_spending) * 100 if total_spending > 0 else 0.0
            category_list.append({
                'category': cat,
                'total': float(amt),
                'count': cnt,
                'pct': pct
            })
        category_list.sort(key=lambda x: x['total'], reverse=True)
        
        return jsonify({
            'custom': False,
            'metrics': {
                'total_spending': metrics.get('total_spending', 0.0),
                'total_count': len(last_30_days_exps),
                'average_transaction': (metrics.get('total_spending', 0.0) / len(last_30_days_exps)) if len(last_30_days_exps) > 0 else 0.0,
                'daily_average': metrics.get('daily_average', 0.0)
            },
            'comparison': comp_metrics,
            'categories': category_list,
            'default_currency': g.current_user.default_currency
        }), 200
    except Exception as e:
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@api.route('/v1/analytics/trends', methods=['GET'])
@token_required
def api_analytics_trends():
    """Endpoint returning category allocations and 6-month historical totals."""
    user_id = g.current_user.id
    
    from flask import request
    from datetime import datetime
    
    start_date_str = request.args.get('start_date', '').strip()
    end_date_str = request.args.get('end_date', '').strip()
    category_filter = request.args.get('category', '').strip()
    
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
        category_dist = AnalyticsService.get_category_distribution(user_id, start_date=start_date, end_date=end_date)
        if category_filter:
            category_dist = {k: v for k, v in category_dist.items() if k.lower() == category_filter.lower()}
            
        try:
            months_back = int(request.args.get('months', '6').strip())
        except ValueError:
            months_back = 6
        history = AnalyticsService.get_monthly_spending_history(user_id, months_back=months_back)
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


@api.route('/v1/analytics/trends-over-time', methods=['GET'])
@token_required
def api_analytics_trends_over_time():
    """Endpoint returning spending totals and moving average aggregated by interval."""
    user_id = g.current_user.id
    
    from flask import request
    from datetime import datetime
    
    interval = request.args.get('interval', 'month').strip().lower()
    start_date_str = request.args.get('start_date', '').strip()
    end_date_str = request.args.get('end_date', '').strip()
    
    try:
        moving_average_window = int(request.args.get('moving_average_window', '3').strip())
    except ValueError:
        moving_average_window = 3
        
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

from datetime import datetime, date, timedelta
from decimal import Decimal
import pandas as pd
import numpy as np
from sqlalchemy import func
from app.extensions import db
from app.models.expense import Expense

class AnalyticsService:
    """Service to compute advanced financial analytics and forecasts using Pandas."""

    @staticmethod
    def get_user_expenses_df(user_id, start_date=None, end_date=None):
        """Helper to load user expenses into a Pandas DataFrame, cached per Flask request context."""
        from flask import has_request_context, g
        
        df = None
        if has_request_context():
            cache_key = f"_user_expenses_df_{user_id}"
            if hasattr(g, cache_key):
                df = getattr(g, cache_key)
                
        if df is None:
            expenses = Expense.query.filter_by(user_id=user_id).all()
            if not expenses:
                df = pd.DataFrame()
            else:
                data = []
                for e in expenses:
                    try:
                        e_date = e.expense_date
                        if not e_date:
                            continue
                        data.append({
                            'amount': float(e.amount) if e.amount else 0.0,
                            'category': e.category or 'Other',
                            'expense_date': pd.to_datetime(e_date),
                            'payee': e.payee or '',
                            'payment_mode': e.payment_mode or ''
                        })
                    except Exception:
                        continue
                df = pd.DataFrame(data)
                
            if has_request_context():
                setattr(g, cache_key, df)
                
        if df.empty:
            return df
            
        # Apply date filters to the cached DataFrame
        filtered_df = df
        if start_date:
            filtered_df = filtered_df[filtered_df['expense_date'] >= pd.to_datetime(start_date)]
        if end_date:
            filtered_df = filtered_df[filtered_df['expense_date'] <= pd.to_datetime(end_date)]
            
        return filtered_df

    @classmethod
    def get_summary_metrics(cls, user_id):
        """Computes summary metrics for the last 30 days using UTC date boundaries."""
        # Use UTC date for consistency across timezones
        today = datetime.now().astimezone().date()  # Use server's local date for now; consider user timezone if needed
        thirty_days_ago = today - timedelta(days=30)
        
        df = cls.get_user_expenses_df(user_id, start_date=thirty_days_ago, end_date=today)
        
        metrics = {
            'total_spending': 0.0,
            'daily_average': 0.0,
            'highest_spending_day': {'date': None, 'amount': 0.0},
            'lowest_spending_day': {'date': None, 'amount': 0.0},
            'top_category': 'None',
            'top_category_amount': 0.0
        }
        
        if df.empty:
            return metrics
            
        # Total Spending
        metrics['total_spending'] = df['amount'].sum()
        
        # Daily Average (using actual 30 days divisor for standard metric)
        metrics['daily_average'] = metrics['total_spending'] / 30.0
        
        # Group by date
        daily_df = df.groupby('expense_date')['amount'].sum().reset_index()
        
        if not daily_df.empty:
            highest_row = daily_df.loc[daily_df['amount'].idxmax()]
            metrics['highest_spending_day'] = {
                'date': highest_row['expense_date'].strftime('%Y-%m-%d'),
                'amount': float(highest_row['amount'])
            }
            
            # For lowest spending day, search within the 30 days. 
            # Days with zero spending are technically lowest, but let's find the lowest positive spending day.
            lowest_row = daily_df.loc[daily_df['amount'].idxmin()]
            metrics['lowest_spending_day'] = {
                'date': lowest_row['expense_date'].strftime('%Y-%m-%d'),
                'amount': float(lowest_row['amount'])
            }
            
        # Group by category
        cat_df = df.groupby('category')['amount'].sum().reset_index()
        if not cat_df.empty:
            top_cat_row = cat_df.loc[cat_df['amount'].idxmax()]
            metrics['top_category'] = top_cat_row['category']
            metrics['top_category_amount'] = float(top_cat_row['amount'])
            
        return metrics

    @classmethod
    def get_category_distribution(cls, user_id, start_date=None, end_date=None):
        """Returns category totals for chart rendering."""
        df = cls.get_user_expenses_df(user_id, start_date, end_date)
        if df.empty:
            return {}
            
        cat_shares = df.groupby('category')['amount'].sum().sort_values(ascending=False)
        return cat_shares.to_dict()

    @classmethod
    def get_monthly_spending_history(cls, user_id, months_back=6):
        """Aggregates spending by month for the last N months."""
        today = date.today()
        start_date = today.replace(day=1) - timedelta(days=30 * (months_back - 1))
        start_date = start_date.replace(day=1)
        
        df = cls.get_user_expenses_df(user_id, start_date=start_date, end_date=today)
        if df.empty:
            return {}
            
        # Extract Month-Year representation
        df['month_year'] = df['expense_date'].dt.to_period('M')
        monthly_totals = df.groupby('month_year')['amount'].sum().sort_index()
        
        return {str(k): float(v) for k, v in monthly_totals.to_dict().items()}

    @classmethod
    def get_daily_trend(cls, user_id, days=30):
        """Returns sorted list of dates and spending amounts for line charts."""
        today = date.today()
        start_date = today - timedelta(days=days)
        
        df = cls.get_user_expenses_df(user_id, start_date=start_date, end_date=today)
        
        # Build list of all dates in the range
        date_range = pd.date_range(start=start_date, end=today)
        
        if df.empty:
            return [d.strftime('%b %d') for d in date_range], [0.0] * len(date_range)
            
        # Group and index by date
        daily_df = df.groupby('expense_date')['amount'].sum().reindex(date_range, fill_value=0.0)
        
        return [d.strftime('%b %d') for d in daily_df.index], [float(v) for v in daily_df.values]

    @classmethod
    def get_comparison_metrics(cls, user_id):
        """Compares this month's spending vs. previous month's spending."""
        today = date.today()
        
        # Current Month Boundaries
        this_month_start = today.replace(day=1)
        
        # Previous Month Boundaries
        prev_month_end = this_month_start - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)
        
        df_this = cls.get_user_expenses_df(user_id, start_date=this_month_start, end_date=today)
        df_prev = cls.get_user_expenses_df(user_id, start_date=prev_month_start, end_date=prev_month_end)
        
        this_total = df_this['amount'].sum() if not df_this.empty else 0.0
        prev_total = df_prev['amount'].sum() if not df_prev.empty else 0.0
        
        difference = this_total - prev_total
        percentage = 0.0
        if prev_total > 0:
            percentage = (difference / prev_total) * 100.0
            
        # Find which category increased the most in amount
        cat_increase_name = 'N/A'
        cat_increase_amount = 0.0
        
        if not df_this.empty and not df_prev.empty:
            cat_this = df_this.groupby('category')['amount'].sum()
            cat_prev = df_prev.groupby('category')['amount'].sum()
            
            # Align categories
            cat_diff = cat_this.sub(cat_prev, fill_value=0.0)
            if not cat_diff.empty:
                max_inc_cat = cat_diff.idxmax()
                max_inc_val = cat_diff.max()
                if max_inc_val > 0:
                    cat_increase_name = max_inc_cat
                    cat_increase_amount = float(max_inc_val)
                    
        return {
            'this_month_total': float(this_total),
            'prev_month_total': float(prev_total),
            'difference': float(difference),
            'percentage_change': float(percentage),
            'most_increased_category': cat_increase_name,
            'most_increased_amount': cat_increase_amount
        }

    @classmethod
    def predict_next_month_spending(cls, user_id):
        """Predicts next month's spending using linear trend forecast or rolling averages."""
        df = cls.get_user_expenses_df(user_id)
        if df.empty or len(df) < 5:
            # Not enough data for mathematical forecast, fallback to basic sum
            return 0.0
            
        # Group by month
        df['month_year'] = df['expense_date'].dt.to_period('M')
        monthly_df = df.groupby('month_year')['amount'].sum().reset_index()
        
        # If we have less than 3 months of data, predict based on average daily rate times 30
        if len(monthly_df) < 3:
            total_days = (df['expense_date'].max() - df['expense_date'].min()).days + 1
            if total_days <= 0:
                total_days = 1
            daily_rate = df['amount'].sum() / total_days
            return float(daily_rate * 30.0)
            
        # Perform simple linear regression on monthly totals
        monthly_df['index'] = range(len(monthly_df))
        X = monthly_df['index'].values
        y = monthly_df['amount'].values
        
        # Find linear coefficients (y = mx + c)
        slope, intercept = np.polyfit(X, y, 1)
        
        # Predict next month (next index)
        next_index = len(monthly_df)
        prediction = slope * next_index + intercept
        
        # Ensure we don't predict negative spending
        return float(max(prediction, 0.0))

    @classmethod
    def get_spending_trends(cls, user_id, interval='month', start_date=None, end_date=None, moving_average_window=3):
        """
        Calculates spending trends over time aggregated by Day, Week, Month, or Year.
        Includes rolling moving average calculation.
        """
        df = cls.get_user_expenses_df(user_id, start_date, end_date)
        
        if df.empty:
            return {
                'labels': [],
                'totals': [],
                'moving_average': []
            }
            
        df['expense_date'] = pd.to_datetime(df['expense_date'])
        
        interval_map = {
            'day': 'D',
            'week': 'W-MON',
            'month': 'MS',
            'year': 'YS'
        }
        freq = interval_map.get(interval.lower(), 'MS')
        
        df_ts = df.set_index('expense_date').sort_index()
        resampled = df_ts['amount'].resample(freq).sum().fillna(0.0)
        
        labels = []
        for idx in resampled.index:
            if freq == 'D':
                labels.append(idx.strftime('%Y-%m-%d'))
            elif freq == 'W-MON':
                week_end = idx + timedelta(days=6)
                labels.append(f"{idx.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}")
            elif freq == 'MS':
                labels.append(idx.strftime('%b %Y'))
            elif freq == 'YS':
                labels.append(idx.strftime('%Y'))
                
        totals = [float(v) for v in resampled.values]
        
        moving_average = []
        if moving_average_window and len(resampled) >= 1:
            window = min(moving_average_window, len(resampled))
            rolling = resampled.rolling(window=window, min_periods=1).mean()
            moving_average = [float(round(v, 2)) for v in rolling.values]
        else:
            moving_average = totals.copy()
            
        return {
            'labels': labels,
            'totals': totals,
            'moving_average': moving_average
        }

    @classmethod
    def get_category_breakdown(cls, user_id, start_date=None, end_date=None):
        """
        Computes category breakdown including total amount, percentage, and transaction count.
        """
        df = cls.get_user_expenses_df(user_id, start_date, end_date)
        if df.empty:
            return []
            
        total_spending = df['amount'].sum()
        if total_spending <= 0:
            return []
            
        # Group by category
        grouped = df.groupby('category').agg(
            total_amount=('amount', 'sum'),
            transaction_count=('amount', 'size')
        ).reset_index()
        
        # Filter out categories with zero spending
        grouped = grouped[grouped['total_amount'] > 0]
        
        if grouped.empty:
            return []
            
        # Calculate percentage
        grouped['percentage'] = (grouped['total_amount'] / total_spending) * 100.0
        
        # Sort by total amount descending
        grouped = grouped.sort_values(by='total_amount', ascending=False)
        
        breakdown = []
        for _, row in grouped.iterrows():
            breakdown.append({
                'category': row['category'],
                'total_amount': float(round(row['total_amount'], 2)),
                'percentage': float(round(row['percentage'], 2)),
                'transaction_count': int(row['transaction_count'])
            })
            
        return breakdown

    @classmethod
    def get_spending_patterns(cls, user_id, start_date=None, end_date=None):
        """
        Computes day-of-week and day-of-month spending patterns and insights.
        """
        df = cls.get_user_expenses_df(user_id, start_date, end_date)
        if df.empty:
            return {
                'day_of_week': [],
                'time_of_month': [],
                'insights': {}
            }
            
        df['expense_date'] = pd.to_datetime(df['expense_date'])
        
        # 1. Day of Week Analysis
        # weekday: 0 = Monday, 6 = Sunday
        df['weekday'] = df['expense_date'].dt.weekday
        df['day_name'] = df['expense_date'].dt.day_name()
        
        weekday_map = {
            0: 'Monday', 1: 'Tuesday', 2: 'Wednesday',
            3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'
        }
        
        dow_list = []
        for w_code in range(7):
            d_name = weekday_map[w_code]
            sub = df[df['weekday'] == w_code]
            if sub.empty:
                dow_list.append({
                    'day_name': d_name,
                    'total_spending': 0.0,
                    'average_spending': 0.0,
                    'transaction_count': 0,
                    'top_category': 'None'
                })
            else:
                total_sp = float(round(sub['amount'].sum(), 2))
                count = int(sub['amount'].count())
                # Group by date to get daily average on that specific weekday
                daily_sums = sub.groupby(sub['expense_date'].dt.date)['amount'].sum()
                avg_sp = float(round(daily_sums.mean(), 2)) if not daily_sums.empty else 0.0
                
                # Top category on this day
                top_cat = sub.groupby('category')['amount'].sum().idxmax()
                
                dow_list.append({
                    'day_name': d_name,
                    'total_spending': total_sp,
                    'average_spending': avg_sp,
                    'transaction_count': count,
                    'top_category': top_cat
                })
                
        # 2. Time of Month (Days 1 to 31)
        df['day_num'] = df['expense_date'].dt.day
        
        dom_list = []
        for d_num in range(1, 32):
            sub = df[df['day_num'] == d_num]
            if sub.empty:
                dom_list.append({
                    'day_num': d_num,
                    'total_spending': 0.0,
                    'average_spending': 0.0,
                    'transaction_count': 0
                })
            else:
                total_sp = float(round(sub['amount'].sum(), 2))
                count = int(sub['amount'].count())
                
                # Get number of distinct years/months that have this day number in the dataset
                distinct_periods = sub['expense_date'].dt.to_period('M').nunique()
                avg_sp = float(round(total_sp / distinct_periods, 2)) if distinct_periods > 0 else 0.0
                
                dom_list.append({
                    'day_num': d_num,
                    'total_spending': total_sp,
                    'average_spending': avg_sp,
                    'transaction_count': count
                })
                
        # 3. Dynamic Insights Generation
        insights = {}
        valid_dow = [d for d in dow_list if d['transaction_count'] > 0]
        
        if valid_dow:
            highest_dow = max(valid_dow, key=lambda x: x['total_spending'])
            lowest_dow = min(dow_list, key=lambda x: x['total_spending'])
            
            insights['highest_spending_day'] = highest_dow['day_name']
            insights['highest_spending_day_amount'] = highest_dow['total_spending']
            insights['lowest_spending_day'] = lowest_dow['day_name']
            insights['lowest_spending_day_amount'] = lowest_dow['total_spending']
            insights['top_category_on_high_day'] = highest_dow['top_category']
            
            # Weekend (Sat/Sun) vs Weekday (Mon-Fri) average daily spending
            weekend_sub = df[df['weekday'].isin([5, 6])]
            weekday_sub = df[df['weekday'].isin([0, 1, 2, 3, 4])]
            
            weekend_daily = weekend_sub.groupby(weekend_sub['expense_date'].dt.date)['amount'].sum()
            weekday_daily = weekday_sub.groupby(weekday_sub['expense_date'].dt.date)['amount'].sum()
            
            insights['weekend_daily_avg'] = float(round(weekend_daily.mean(), 2)) if not weekend_daily.empty else 0.0
            insights['weekday_daily_avg'] = float(round(weekday_daily.mean(), 2)) if not weekday_daily.empty else 0.0
            
            if insights['weekday_daily_avg'] > 0:
                insights['weekend_vs_weekday_pct'] = float(round(
                    ((insights['weekend_daily_avg'] - insights['weekday_daily_avg']) / insights['weekday_daily_avg']) * 100.0, 1
                ))
            else:
                insights['weekend_vs_weekday_pct'] = 0.0
                
        # Time period of the month comparison: Days 1-10, 11-20, 21-31
        p1 = df[df['day_num'].between(1, 10)]['amount'].sum()
        p2 = df[df['day_num'].between(11, 20)]['amount'].sum()
        p3 = df[df['day_num'].between(21, 31)]['amount'].sum()
        
        periods = [
            {'range': 'Days 1-10', 'total': float(p1)},
            {'range': 'Days 11-20', 'total': float(p2)},
            {'range': 'Days 21-31', 'total': float(p3)}
        ]
        highest_period = max(periods, key=lambda x: x['total'])
        insights['highest_spending_period'] = highest_period['range']
        insights['highest_spending_period_amount'] = highest_period['total']
        
        return {
            'day_of_week': dow_list,
            'time_of_month': dom_list,
            'insights': insights
        }

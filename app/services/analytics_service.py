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
        """Helper to load user expenses into a Pandas DataFrame."""
        expenses = Expense.query.filter_by(user_id=user_id).all()
        if not expenses:
            return pd.DataFrame()
            
        data = []
        for e in expenses:
            try:
                e_date = e.expense_date
                if not e_date:
                    continue
                
                # Apply date filters in Python since DB fields are encrypted
                if start_date and e_date < start_date:
                    continue
                if end_date and e_date > end_date:
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
                
        return pd.DataFrame(data)

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

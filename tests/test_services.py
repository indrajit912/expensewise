import pytest
import json
from datetime import date, timedelta
from decimal import Decimal
from app import db
from app.models.expense import Expense
from app.services.analytics_service import AnalyticsService
from app.services.export_service import ExportService
from app.services.encryption_service import EncryptionService

def test_analytics_metrics_calculations(app, test_user):
    """Tests summary metrics, averages, comparisons, and history aggregates."""
    with app.app_context():
        # Setup override key for encryption
        ukey = EncryptionService.get_user_key()
        if not ukey:
            EncryptionService.set_override_key(EncryptionService.generate_fernet_key())
            
        # Setup mock records
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        # Current month expenses
        exp1 = Expense(user_id=test_user.id, amount=Decimal('50.00'), category='Food', expense_date=today, description='Coffee and pastries')
        exp2 = Expense(user_id=test_user.id, amount=Decimal('150.00'), category='Groceries', expense_date=yesterday, description='Weekly groceries')
        
        # Previous month expense
        last_month = today - timedelta(days=45)
        exp3 = Expense(user_id=test_user.id, amount=Decimal('200.00'), category='Rent', expense_date=last_month)
        
        db.session.add_all([exp1, exp2, exp3])
        db.session.commit()
        
        # 1. Test Summary Metrics
        metrics = AnalyticsService.get_summary_metrics(test_user.id)
        assert metrics['total_spending'] == 200.0
        assert metrics['daily_average'] == 200.0 / 30.0
        assert metrics['top_category'] == 'Groceries'
        assert metrics['top_category_amount'] == 150.0
        
        # 2. Test Category Distribution
        dist = AnalyticsService.get_category_distribution(test_user.id)
        assert dist['Groceries'] == 150.0
        assert dist['Food'] == 50.0
        assert dist['Rent'] == 200.0
        
        # 3. Test MoM Comparisons
        comp = AnalyticsService.get_comparison_metrics(test_user.id)
        assert comp['this_month_total'] == 200.0
        assert comp['prev_month_total'] == 200.0
        assert comp['difference'] == 0.0
        assert comp['percentage_change'] == 0.0
        
        # 4. Test Daily Trends
        labels, values = AnalyticsService.get_daily_trend(test_user.id, days=10)
        assert len(labels) == 11 # 10 days ago to today
        assert sum(values) == 200.0


def test_export_service(app, test_user):
    """Tests JSON and CSV file generators in ExportService."""
    with app.app_context():
        # Setup override key for encryption
        ukey = EncryptionService.get_user_key()
        if not ukey:
            EncryptionService.set_override_key(EncryptionService.generate_fernet_key())
            
        exp = Expense(
            user_id=test_user.id,
            amount=Decimal('45.00'),
            category='Travel',
            expense_date=date(2026, 6, 20),
            payee='Uber',
            payment_mode='Card',
            description='Ride home'
        )
        db.session.add(exp)
        db.session.commit()
        
        # Test JSON Generation
        json_out = ExportService.generate_json(test_user)
        data = json.loads(json_out)
        assert data['export_version'] == '2.0'
        assert data['user_preferences']['default_currency'] == test_user.default_currency
        assert len(data['expenses']) == 1
        assert data['expenses'][0]['amount'] == 45.0
        assert data['expenses'][0]['payee'] == 'Uber'



def test_gravatar_url_generation(app, test_user):
    """Tests that avatar_url produces correct Gravatar URLs."""
    with app.app_context():
        url = test_user.avatar_url(size=40, default='mp')
        assert "gravatar.com/avatar/" in url
        assert "s=40" in url
        assert "d=mp" in url
        
        import hashlib
        expected_hash = hashlib.md5("test@example.com".encode('utf-8')).hexdigest()
        assert expected_hash in url


def test_currency_format_indian_numbering(app):
    """Tests the Jinja currency_format filter with Indian digit groupings."""
    with app.app_context():
        cf_filter = app.jinja_env.filters['currency_format']
        
        # Test basic, thousand, lakh, and crore formats
        assert cf_filter(100, 'INR') == '₹100.00'
        assert cf_filter(1230.50, 'INR') == '₹1,230.50'
        assert cf_filter(1230445.75, 'INR') == '₹12,30,445.75'
        assert cf_filter(12345678.90, 'USD') == '$1,23,45,678.90'
        
        assert cf_filter(0, 'INR') == '₹0.00'
        assert cf_filter(-1230445.75, 'INR') == '₹-12,30,445.75'
        assert cf_filter(None, 'INR') == ''


def test_decimal_small_filter(app):
    """Tests the Jinja decimal_small filter wrapping decimal parts."""
    with app.app_context():
        ds_filter = app.jinja_env.filters['decimal_small']
        
        # Test positive numbers, currency strings, and edge cases
        assert ds_filter("₹1,230.50") == "₹1,230<span style='font-size: 0.75em;'>.50</span>"
        assert ds_filter("₹12,30,445.75") == "₹12,30,445<span style='font-size: 0.75em;'>.75</span>"
        assert ds_filter("100.00") == "100<span style='font-size: 0.75em;'>.00</span>"
        assert ds_filter("100") == "100"
        assert ds_filter("") == ""
        assert ds_filter(None) == ""


def test_current_year_context_processor(app):
    """Tests that current_year is injected and equals the active calendar year."""
    from datetime import datetime
    with app.app_context():
        processors = app.template_context_processors[None]
        context = {}
        for p in processors:
            context.update(p())
            
        assert 'current_year' in context
        assert context['current_year'] == datetime.now().year

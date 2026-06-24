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
        assert data['user_preferences']['default_currency'] == 'USD'
        assert len(data['expenses']) == 1
        assert data['expenses'][0]['amount'] == 45.0
        assert data['expenses'][0]['payee'] == 'Uber'
        
        # Test CSV Generation
        csv_out = ExportService.generate_csv([exp])
        lines = csv_out.strip().split('\n')
        assert len(lines) == 2 # Header + 1 record row
        assert 'Amount' in lines[0]
        assert '45.0' in lines[1]
        assert 'Uber' in lines[1]

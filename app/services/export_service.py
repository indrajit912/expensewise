import io
import csv
import json
from datetime import datetime, timezone
from decimal import Decimal

class ExportService:
    """Service to handle CSV and JSON export pipelines."""

    @staticmethod
    def generate_json(user):
        """Formats the entire user database state (Default currency + Categories + Payment Methods + Expenses) into versioned JSON backup."""
        from app.models.expense import Expense, Category, PaymentMethod
        
        # Grab categories
        categories = Category.query.filter_by(user_id=user.id).order_by(Category.name).all()
        cat_list = []
        cat_name_to_id = {}
        for c in categories:
            cat_name_to_id[c.name] = c.id
            cat_list.append({
                'id': c.id,
                'name': c.name,
                'color': c.color,
                'created_at': c.created_at.isoformat() if c.created_at else None
            })
            
        # Grab payment methods
        payment_methods = PaymentMethod.query.filter_by(user_id=user.id).order_by(PaymentMethod.name).all()
        pm_list = []
        pm_name_to_id = {}
        for pm in payment_methods:
            pm_name_to_id[pm.name] = pm.id
            pm_list.append({
                'id': pm.id,
                'name': pm.name,
                'color': pm.color,
                'created_at': pm.created_at.isoformat() if pm.created_at else None
            })
            
        # Grab expenses
        expenses = Expense.query.filter_by(user_id=user.id).all()
        exp_list = []
        for e in expenses:
            cat_id = cat_name_to_id.get(e.category)
            pm_id = pm_name_to_id.get(e.payment_mode) if e.payment_mode else None
            
            exp_list.append({
                'id': e.id,
                'amount': float(e.amount) if e.amount else 0.0,
                'category_id': cat_id,
                'payment_method_id': pm_id,
                'expense_date': e.expense_date.strftime('%Y-%m-%d') if e.expense_date else '',
                'description': e.description or '',
                'payee': e.payee or '',
                'original_amount': float(e.original_amount) if e.original_amount else (float(e.amount) if e.amount else 0.0),
                'original_currency': e.original_currency,
                'conversion_rate': float(e.conversion_rate) if e.conversion_rate else 1.0,
                'converted_amount': float(e.converted_amount) if e.converted_amount else (float(e.amount) if e.amount else 0.0),
                'created_at': e.created_at.isoformat() if e.created_at else None
            })
            
        data = {
            'export_version': '2.0',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'user_preferences': {
                'default_currency': user.default_currency
            },
            'categories': cat_list,
            'payment_methods': pm_list,
            'expenses': exp_list
        }
        
        return json.dumps(data, indent=4)

    @staticmethod
    def generate_csv(expenses):
        """Writes expense records into an in-memory CSV buffer."""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write CSV Headers
        writer.writerow([
            'Amount', 'Category', 'Payee', 'Payment Mode', 'Date', 'Description', 
            'Original Amount', 'Original Currency', 'Conversion Rate', 'Converted Amount'
        ])
        
        for e in expenses:
            writer.writerow([
                float(e.amount),
                e.category,
                e.payee or '',
                e.payment_mode or '',
                e.expense_date.strftime('%Y-%m-%d'),
                e.description or '',
                float(e.original_amount) if e.original_amount else float(e.amount),
                e.original_currency,
                float(e.conversion_rate) if e.conversion_rate else 1.0,
                float(e.converted_amount) if e.converted_amount else float(e.amount)
            ])
            
        return output.getvalue()

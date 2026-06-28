import os
from flask import request, jsonify, g, Response
from marshmallow import ValidationError
from decimal import Decimal
from datetime import datetime, date
from app.extensions import db
from app.models.expense import Expense
from app.api import api
from app.api.decorators import token_required
from app.api.schemas import ExpenseSchema
from app.services.import_service import ImportService
from app.services.export_service import ExportService
from app.services.audit_service import AuditService

expense_schema = ExpenseSchema()
expenses_schema = ExpenseSchema(many=True)

class SimplePagination:
    """Manual in-memory pagination helper matching Flask-SQLAlchemy signature."""
    def __init__(self, items, page, per_page):
        self.total = len(items)
        self.page = page
        self.per_page = per_page
        self.pages = (self.total + per_page - 1) // per_page if self.total > 0 else 1
        
        start = (page - 1) * per_page
        end = start + per_page
        self.items = items[start:end]
        
        self.has_next = page < self.pages
        self.has_prev = page > 1

    @property
    def prev_num(self):
        return self.page - 1 if self.has_prev else None

    @property
    def next_num(self):
        return self.page + 1 if self.has_next else None

    def iter_pages(self, left_edge=2, left_current=2, right_current=5, right_edge=2):
        last = 0
        for num in range(1, self.pages + 1):
            if (
                num <= left_edge
                or (
                    num > self.page - left_current - 1
                    and num < self.page + right_current
                )
                or num > self.pages - right_edge
            ):
                if last + 1 != num:
                    yield None
                yield num
                last = num


@api.route('/v1/expenses', methods=['GET'])
@token_required
def api_list_expenses():
    """Lists expenses with python filtering, sorting, and manual pagination."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 15, type=int)
    
    search_query = request.args.get('search', '').strip()
    category = request.args.get('category', '').strip()
    start_date_str = request.args.get('start_date', '').strip()
    end_date_str = request.args.get('end_date', '').strip()
    
    sort_by = request.args.get('sort_by', 'expense_date')
    order = request.args.get('order', 'desc')

    # Parse date filters
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

    filtered_items = Expense.get_filtered_expenses(
        user_id=g.current_user.id,
        category=category,
        start_date=start_date,
        end_date=end_date,
        search_query=search_query
    )

    # Sort
    if sort_by == 'amount':
        key_func = lambda x: x.amount or Decimal('0.00')
    elif sort_by == 'category':
        key_func = lambda x: x.category or ''
    elif sort_by == 'payee':
        key_func = lambda x: x.payee or ''
    elif sort_by == 'payment_mode':
        key_func = lambda x: x.payment_mode or ''
    else:
        key_func = lambda x: x.expense_date or date.min

    filtered_items.sort(key=key_func, reverse=(order == 'desc'))

    # Paginate
    pagination = SimplePagination(filtered_items, page, per_page)
    
    return jsonify({
        'expenses': expenses_schema.dump(pagination.items),
        'default_currency': g.current_user.default_currency,
        'pagination': {
            'total_items': pagination.total,
            'total_pages': pagination.pages,
            'current_page': pagination.page,
            'per_page': pagination.per_page,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev
        }
    }), 200


@api.route('/v1/expenses', methods=['POST'])
@token_required
def api_create_expense():
    """Creates a new expense record via JSON payload (encrypted at rest)."""
    json_data = request.get_json() or {}
    
    try:
        expense_data = expense_schema.load(json_data)
    except ValidationError as err:
        return jsonify({'error': 'Bad Request', 'message': err.messages}), 400

    expense_data.user_id = g.current_user.id
    
    default_currency = g.current_user.default_currency
    orig_currency = json_data.get('original_currency') or json_data.get('currency')
    if orig_currency:
        orig_currency = orig_currency.strip().upper()
    else:
        orig_currency = default_currency
        
    orig_amount = json_data.get('original_amount')
    if orig_amount is not None:
        try:
            orig_amount = Decimal(str(orig_amount))
        except Exception:
            return jsonify({'error': 'Bad Request', 'message': 'Invalid original_amount'}), 400
    else:
        orig_amount = expense_data.amount
        
    rate = Decimal('1.0000')
    rate_val = json_data.get('conversion_rate')
    if rate_val is not None:
        try:
            rate = Decimal(str(rate_val))
            if rate <= 0:
                raise ValueError()
        except Exception:
            return jsonify({'error': 'Bad Request', 'message': 'Invalid conversion_rate'}), 400
    elif orig_currency != default_currency:
        return jsonify({'error': 'Bad Request', 'message': 'conversion_rate is required when currency differs from default_currency.'}), 400
        
    if orig_currency != default_currency:
        canonical_amount = orig_amount * rate
    else:
        canonical_amount = orig_amount
        rate = Decimal('1.0000')
        
    expense_data.amount = canonical_amount
    expense_data.original_amount = orig_amount
    expense_data.original_currency = orig_currency
    expense_data.conversion_rate = rate
    expense_data.converted_amount = canonical_amount
    
    try:
        db.session.add(expense_data)
        db.session.commit()
        
        AuditService.log(
            "Expense Creation", 
            f"Created expense via API: {expense_data.amount:.2f} {default_currency} under {expense_data.category}", 
            user_id=g.current_user.id
        )
        
        return jsonify(expense_schema.dump(expense_data)), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@api.route('/v1/expenses/<uuid_str>', methods=['GET'])
@token_required
def api_get_expense(uuid_str):
    """Retrieves details of a single expense."""
    expense = Expense.query.filter_by(id=uuid_str, user_id=g.current_user.id).first_or_404()
    return jsonify(expense_schema.dump(expense)), 200


@api.route('/v1/expenses/<uuid_str>', methods=['PUT'])
@token_required
def api_update_expense(uuid_str):
    """Updates fields of an existing expense."""
    expense = Expense.query.filter_by(id=uuid_str, user_id=g.current_user.id).first_or_404()
    json_data = request.get_json() or {}
    
    try:
        expense_data = expense_schema.load(json_data, partial=True)
    except ValidationError as err:
        return jsonify({'error': 'Bad Request', 'message': err.messages}), 400

    old_amount = expense.amount
    old_category = expense.category

    default_currency = g.current_user.default_currency
    orig_currency = json_data.get('original_currency') or json_data.get('currency') or expense.original_currency
    orig_currency = orig_currency.strip().upper()
    
    orig_amount = json_data.get('original_amount')
    if orig_amount is not None:
        try:
            orig_amount = Decimal(str(orig_amount))
        except Exception:
            return jsonify({'error': 'Bad Request', 'message': 'Invalid original_amount'}), 400
    elif 'amount' in json_data:
        try:
            orig_amount = Decimal(str(json_data['amount']))
        except Exception:
            return jsonify({'error': 'Bad Request', 'message': 'Invalid amount'}), 400
    else:
        orig_amount = expense.original_amount

    rate = Decimal('1.0000')
    rate_val = json_data.get('conversion_rate')
    if rate_val is not None:
        try:
            rate = Decimal(str(rate_val))
            if rate <= 0:
                raise ValueError()
        except Exception:
            return jsonify({'error': 'Bad Request', 'message': 'Invalid conversion_rate'}), 400
    elif orig_currency != default_currency:
        rate = expense.conversion_rate
        if rate == Decimal('1.0000') or rate <= 0:
            return jsonify({'error': 'Bad Request', 'message': 'conversion_rate is required when currency differs from default_currency.'}), 400
            
    if orig_currency != default_currency:
        canonical_amount = orig_amount * rate
    else:
        canonical_amount = orig_amount
        rate = Decimal('1.0000')

    expense.amount = canonical_amount
    expense.original_amount = orig_amount
    expense.original_currency = orig_currency
    expense.conversion_rate = rate
    expense.converted_amount = canonical_amount

    if 'category' in json_data:
        expense.category = expense_data.category
    if 'expense_date' in json_data:
        expense.expense_date = expense_data.expense_date
    if 'payee' in json_data:
        expense.payee = expense_data.payee
    if 'payment_mode' in json_data:
        expense.payment_mode = expense_data.payment_mode
    if 'description' in json_data:
        expense.description = expense_data.description
        
    try:
        db.session.commit()
        
        # Log to audit trail
        AuditService.log(
            "Expense Modification", 
            f"Modified expense via API {uuid_str}: Changed amount {old_amount:.2f} -> {expense.amount:.2f}, category '{old_category}' -> '{expense.category}'",
            user_id=g.current_user.id
        )
        
        return jsonify(expense_schema.dump(expense)), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@api.route('/v1/expenses/<uuid_str>', methods=['DELETE'])
@token_required
def api_delete_expense(uuid_str):
    """Deletes an individual expense."""
    expense = Expense.query.filter_by(id=uuid_str, user_id=g.current_user.id).first_or_404()
    amount = expense.amount
    category = expense.category
    
    try:
        db.session.delete(expense)
        db.session.commit()
        
        # Log to audit trail
        AuditService.log(
            "Expense Deletion", 
            f"Deleted expense via API: ${amount:.2f} under {category}", 
            user_id=g.current_user.id
        )
        
        return jsonify({'message': 'Expense record deleted successfully.'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@api.route('/v1/export', methods=['GET'])
@token_required
def api_export_expenses():
    """Generates backup file content stream (records in audit logs)."""
    # Audit log entry
    AuditService.log("Export", "API requested data export in JSON format", user_id=g.current_user.id)
        
    json_data = ExportService.generate_json(g.current_user)
    return Response(
        json_data,
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment;filename=expenses_export.json'}
    )


@api.route('/v1/import', methods=['POST'])
@token_required
def api_import_expenses():
    """Performs bulk import from raw JSON backup structures (ownership checked)."""
    if request.is_json:
        json_payload = request.get_json()
        result = ImportService.import_standard_json(g.current_user.id, json_payload)
        status = 200 if result.get('success') else 400
        
        if result.get('success'):
            AuditService.log(
                "Import", 
                f"API imported JSON data: Added {result['success_count']} expenses, skipped {result['duplicate_count']}", 
                user_id=g.current_user.id
            )
        return jsonify(result), status

    if 'file' in request.files:
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'Bad Request', 'message': 'No file selected.'}), 400
            
        if file.filename.endswith('.json'):
            content = file.stream.read().decode('utf-8')
            result = ImportService.import_standard_json(g.current_user.id, content)
            status = 200 if result.get('success') else 400
            
            if result.get('success'):
                AuditService.log(
                    "Import", 
                    f"API imported JSON file: Added {result['success_count']} expenses, skipped {result['duplicate_count']}", 
                    user_id=g.current_user.id
                )
            return jsonify(result), status
        else:
            return jsonify({'error': 'Bad Request', 'message': 'Invalid format. Supported: JSON backup file attachments.'}), 400

    return jsonify({'error': 'Bad Request', 'message': 'Send either a JSON payload or a JSON multipart file.'}), 400

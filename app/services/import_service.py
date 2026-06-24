import json
import uuid
from datetime import datetime
import pandas as pd
from decimal import Decimal, InvalidOperation
from app.extensions import db
from app.models.user import User
from app.models.expense import Expense, Category, PaymentMethod

class ImportService:
    """Service to handle ingestion of standard CSV/JSON database exports and legacy databases."""
    
    # Map old/non-standard categories to our standard set
    CATEGORY_MAPPING = {
        'essentials': 'Other',
        'snacks': 'Food',
        'food': 'Food',
        'groceries': 'Groceries',
        'rent': 'Rent',
        'utilities': 'Utilities',
        'travel': 'Travel',
        'entertainment': 'Entertainment',
        'medical': 'Medical',
        'education': 'Education',
        'shopping': 'Shopping',
        'toiletries': 'Shopping',
        'other': 'Other'
    }

    @classmethod
    def normalize_category(cls, category_str):
        """Maps a category string to one of the standard category names."""
        if not category_str:
            return 'Other'
        cleaned = category_str.strip().lower()
        return cls.CATEGORY_MAPPING.get(cleaned, 'Other')

    @classmethod
    def check_duplicate(cls, user_id, amount, expense_date, category, description):
        """Checks if a matching expense record already exists to avoid duplication (compares decrypted fields in Python)."""
        all_expenses = Expense.query.filter_by(user_id=user_id).all()
        for e in all_expenses:
            try:
                if (e.amount == amount and 
                    e.expense_date == expense_date and 
                    e.category == category and 
                    (e.description == description or (not e.description and not description))):
                    return True
            except Exception:
                continue
        return False

    @classmethod
    def import_legacy_json(cls, user_id, json_filepath_or_content):
        """Parses and imports the database.json structure from the legacy CLI app (utilized in bootstrap-system)."""
        try:
            if isinstance(json_filepath_or_content, str) and not json_filepath_or_content.strip().startswith('{'):
                with open(json_filepath_or_content, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = json.loads(json_filepath_or_content) if isinstance(json_filepath_or_content, str) else json_filepath_or_content
        except (json.JSONDecodeError, OSError) as e:
            return {'success': False, 'error': f"Failed to load JSON structure: {str(e)}", 'success_count': 0, 'error_count': 1, 'duplicate_count': 0}

        expenses_dict = data.get('expenses', {})
        success_count = 0
        duplicate_count = 0
        error_count = 0
        skipped_records = []
        new_expenses = []

        # JSON keys are date strings, value is list of expense records
        for date_key, records in expenses_dict.items():
            for idx, record in enumerate(records):
                try:
                    raw_amount = record.get('amount')
                    if raw_amount is None:
                        raise ValueError("Missing amount")
                    amount = Decimal(str(raw_amount))
                    if amount <= 0:
                        raise ValueError("Amount must be positive")

                    raw_date = record.get('date', date_key)
                    try:
                        expense_date = datetime.strptime(raw_date.strip(), "%b %d, %Y").date()
                    except ValueError:
                        expense_date = datetime.strptime(raw_date.strip(), "%Y-%m-%d").date()

                    category = cls.normalize_category(record.get('category', 'Other'))
                    payee = record.get('payee', '').strip() or None
                    payment_mode = record.get('mode', '').strip() or None
                    description = record.get('message', '').strip() or None

                    # Ensure Category exists in user registry
                    if not Category.query.filter_by(user_id=user_id, name=category).first():
                        db.session.add(Category(user_id=user_id, name=category))
                        db.session.commit()

                    # Ensure Payment Method exists in user registry
                    if payment_mode:
                        if not PaymentMethod.query.filter_by(user_id=user_id, name=payment_mode).first():
                            db.session.add(PaymentMethod(user_id=user_id, name=payment_mode))
                            db.session.commit()

                    if cls.check_duplicate(user_id, amount, expense_date, category, description):
                        duplicate_count += 1
                        continue

                    user = User.query.get(user_id)
                    default_currency = user.default_currency if user else 'USD'

                    # Attributes are automatically encrypted via setter properties
                    expense = Expense(
                        user_id=user_id,
                        amount=amount,
                        category=category,
                        description=description,
                        payee=payee,
                        payment_mode=payment_mode,
                        expense_date=expense_date,
                        original_amount=amount,
                        original_currency=default_currency,
                        conversion_rate=Decimal('1.0000'),
                        converted_amount=amount
                    )
                    new_expenses.append(expense)
                    success_count += 1

                except (ValueError, InvalidOperation, TypeError) as val_err:
                    error_count += 1
                    skipped_records.append({
                        'record': record,
                        'reason': str(val_err)
                    })

        if new_expenses:
            try:
                db.session.add_all(new_expenses)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                return {'success': False, 'error': f"Database save error: {str(e)}", 'success_count': 0, 'error_count': error_count, 'duplicate_count': 0}

        return {
            'success': True,
            'success_count': success_count,
            'duplicate_count': duplicate_count,
            'error_count': error_count,
            'errors': skipped_records
        }

    @classmethod
    def validate_backup_json(cls, data):
        """Validates the version 2.0 backup JSON structure.
        Returns a tuple: (is_valid, checklist, error_message)
        """
        checklist = {
            'structure': {'title': 'JSON Structure Check', 'status': False, 'message': 'Pending verification'},
            'version': {'title': 'Version Verification', 'status': False, 'message': 'Pending verification'},
            'sections': {'title': 'Required Sections Check', 'status': False, 'message': 'Pending verification'},
            'uuid': {'title': 'UUID Format Verification', 'status': False, 'message': 'Pending verification'},
            'category_ref': {'title': 'Category References Check', 'status': False, 'message': 'Pending verification'},
            'payment_ref': {'title': 'Payment Method References Check', 'status': False, 'message': 'Pending verification'},
            'expense_format': {'title': 'Expense Formats Verification', 'status': False, 'message': 'Pending verification'}
        }
        
        # 1. Structure Check
        if not isinstance(data, dict):
            checklist['structure']['message'] = 'Root element must be a JSON object (dictionary).'
            return False, checklist, "Root element is not a JSON object."
        
        checklist['structure']['status'] = True
        checklist['structure']['message'] = 'Root element is a valid JSON object.'
        
        # 2. Version Check
        version = data.get('export_version')
        if version != '2.0':
            checklist['version']['message'] = f'Expected version "2.0", found "{version or "none"}".'
            return False, checklist, f"Unsupported export version: {version or 'none'}."
            
        checklist['version']['status'] = True
        checklist['version']['message'] = 'Backup version 2.0 verified.'
        
        # 3. Sections Check
        categories = data.get('categories')
        payment_methods = data.get('payment_methods')
        expenses = data.get('expenses')
        
        if categories is None or not isinstance(categories, list):
            checklist['sections']['message'] = 'Missing or invalid "categories" array.'
            return False, checklist, 'Missing or invalid "categories" array.'
        if payment_methods is None or not isinstance(payment_methods, list):
            checklist['sections']['message'] = 'Missing or invalid "payment_methods" array.'
            return False, checklist, 'Missing or invalid "payment_methods" array.'
        if expenses is None or not isinstance(expenses, list):
            checklist['sections']['message'] = 'Missing or invalid "expenses" array.'
            return False, checklist, 'Missing or invalid "expenses" array.'
            
        checklist['sections']['status'] = True
        checklist['sections']['message'] = 'All required sections (categories, payment_methods, expenses) are present.'
        
        # Helper for UUID validation
        def is_valid_uuid(val):
            if not isinstance(val, str):
                return False
            try:
                uuid.UUID(val)
                return True
            except ValueError:
                return False
                
        # 4. UUID Integrity
        for c in categories:
            cid = c.get('id')
            if not is_valid_uuid(cid):
                checklist['uuid']['message'] = f'Category "{c.get("name", "Unknown")}" has invalid UUID: {cid}.'
                return False, checklist, f'Category "{c.get("name", "Unknown")}" has invalid UUID: {cid}.'
                
        for pm in payment_methods:
            pmid = pm.get('id')
            if not is_valid_uuid(pmid):
                checklist['uuid']['message'] = f'Payment method "{pm.get("name", "Unknown")}" has invalid UUID: {pmid}.'
                return False, checklist, f'Payment method "{pm.get("name", "Unknown")}" has invalid UUID: {pmid}.'
                
        for e in expenses:
            eid = e.get('id')
            if eid and not is_valid_uuid(eid):
                checklist['uuid']['message'] = f'Expense with amount {e.get("amount")} has invalid UUID: {eid}.'
                return False, checklist, f'Expense with amount {e.get("amount")} has invalid UUID: {eid}.'
                
        checklist['uuid']['status'] = True
        checklist['uuid']['message'] = 'All category, payment method, and expense IDs match standard UUID string formats.'
        
        # 5. Category References
        backup_cat_ids = {c['id'] for c in categories}
        for e in expenses:
            cat_id = e.get('category_id')
            if not cat_id or cat_id not in backup_cat_ids:
                checklist['category_ref']['message'] = f'Expense references non-existent category_id: {cat_id}.'
                return False, checklist, f'Expense references non-existent category_id: {cat_id}.'
                
        checklist['category_ref']['status'] = True
        checklist['category_ref']['message'] = 'All expense records map to valid categories in the backup.'
        
        # 6. Payment Method References
        backup_pm_ids = {pm['id'] for pm in payment_methods}
        for e in expenses:
            pm_id = e.get('payment_method_id')
            if pm_id and pm_id not in backup_pm_ids:
                checklist['payment_ref']['message'] = f'Expense references non-existent payment_method_id: {pm_id}.'
                return False, checklist, f'Expense references non-existent payment_method_id: {pm_id}.'
                
        checklist['payment_ref']['status'] = True
        checklist['payment_ref']['message'] = 'All expense records map to valid payment methods in the backup.'
        
        # 7. Expense Format & Values
        for idx, e in enumerate(expenses):
            # Amount check
            raw_amount = e.get('amount')
            if raw_amount is None:
                checklist['expense_format']['message'] = f'Expense at index {idx} is missing amount.'
                return False, checklist, f'Expense at index {idx} is missing amount.'
            try:
                amt = Decimal(str(raw_amount))
                if amt <= 0:
                    checklist['expense_format']['message'] = f'Expense at index {idx} has non-positive amount: {amt}.'
                    return False, checklist, f'Expense at index {idx} has non-positive amount: {amt}.'
            except (ValueError, InvalidOperation):
                checklist['expense_format']['message'] = f'Expense at index {idx} has non-numeric amount: {raw_amount}.'
                return False, checklist, f'Expense at index {idx} has non-numeric amount: {raw_amount}.'
                
            # Date check
            raw_date = e.get('expense_date')
            if not raw_date:
                checklist['expense_format']['message'] = f'Expense at index {idx} is missing expense_date.'
                return False, checklist, f'Expense at index {idx} is missing expense_date.'
            try:
                datetime.strptime(raw_date.strip(), "%Y-%m-%d")
            except ValueError:
                checklist['expense_format']['message'] = f'Expense at index {idx} has invalid date format: {raw_date}.'
                return False, checklist, f'Expense at index {idx} has invalid date format: {raw_date}.'
                
        checklist['expense_format']['status'] = True
        checklist['expense_format']['message'] = 'All expense amounts are positive, and date formats match YYYY-MM-DD.'
        
        return True, checklist, None

    @classmethod
    def import_standard_json(cls, user_id, json_filepath_or_content):
        """Parses and imports the standard JSON export format for the current user."""
        try:
            if isinstance(json_filepath_or_content, str):
                trimmed = json_filepath_or_content.strip()
                if trimmed.startswith('{') or trimmed.startswith('['):
                    data = json.loads(trimmed)
                else:
                    with open(json_filepath_or_content, 'r', encoding='utf-8') as f:
                        data = json.load(f)
            else:
                data = json_filepath_or_content
        except Exception as e:
            return {'success': False, 'error': f"Failed to parse JSON: {str(e)}", 'success_count': 0, 'error_count': 1, 'duplicate_count': 0}

        if isinstance(data, list):
            # Clear existing expenses to rebuild entirely from JSON
            try:
                Expense.query.filter_by(user_id=user_id).delete()
                db.session.flush()
            except Exception as e:
                db.session.rollback()
                return {'success': False, 'error': f"Failed to clear existing user expenses: {str(e)}", 'success_count': 0, 'error_count': 1, 'duplicate_count': 0}

            success_count = 0
            duplicate_count = 0
            error_count = 0
            skipped_records = []
            new_expenses = []

            for idx, record in enumerate(data):
                try:
                    raw_amount = record.get('amount')
                    if raw_amount is None:
                        raise ValueError("Missing amount")
                    amount = Decimal(str(raw_amount))
                    if amount <= 0:
                        raise ValueError("Amount must be positive")

                    raw_date = record.get('expense_date')
                    if not raw_date:
                        raise ValueError("Missing expense_date")
                    expense_date = datetime.strptime(raw_date.strip(), "%Y-%m-%d").date()

                    category = record.get('category', 'Other').strip()
                    if not category:
                        category = 'Other'

                    payee = record.get('payee', '').strip() or None
                    payment_mode = record.get('payment_mode', '').strip() or None
                    description = record.get('description', '').strip() or None

                    # Ensure Category exists in user registry
                    if not Category.query.filter_by(user_id=user_id, name=category).first():
                        db.session.add(Category(user_id=user_id, name=category))
                        db.session.commit()

                    if payment_mode:
                        if not PaymentMethod.query.filter_by(user_id=user_id, name=payment_mode).first():
                            db.session.add(PaymentMethod(user_id=user_id, name=payment_mode))
                            db.session.commit()

                    user = User.query.get(user_id)
                    default_currency = user.default_currency if user else 'USD'

                    orig_currency = record.get('original_currency') or record.get('currency')
                    if orig_currency:
                        orig_currency = orig_currency.strip().upper()
                    else:
                        orig_currency = default_currency

                    orig_amount = record.get('original_amount')
                    if orig_amount is not None:
                        orig_amount = Decimal(str(orig_amount))
                    else:
                        orig_amount = amount

                    rate_val = record.get('conversion_rate')
                    if rate_val is not None:
                        rate = Decimal(str(rate_val))
                    else:
                        rate = Decimal('1.0000')

                    if orig_currency != default_currency:
                        canonical_amount = orig_amount * rate
                    else:
                        canonical_amount = amount
                        rate = Decimal('1.0000')

                    if cls.check_duplicate(user_id, canonical_amount, expense_date, category, description):
                        duplicate_count += 1
                        continue

                    expense = Expense(
                        user_id=user_id,
                        amount=canonical_amount,
                        category=category,
                        description=description,
                        payee=payee,
                        payment_mode=payment_mode,
                        expense_date=expense_date,
                        original_amount=orig_amount,
                        original_currency=orig_currency,
                        conversion_rate=rate,
                        converted_amount=canonical_amount
                    )
                    new_expenses.append(expense)
                    success_count += 1

                except Exception as val_err:
                    error_count += 1
                    skipped_records.append({
                        'index': idx,
                        'reason': str(val_err)
                    })

            if new_expenses:
                try:
                    db.session.add_all(new_expenses)
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    return {'success': False, 'error': f"Database save error: {str(e)}", 'success_count': 0, 'error_count': error_count, 'duplicate_count': 0}

            return {
                'success': True,
                'success_count': success_count,
                'duplicate_count': duplicate_count,
                'error_count': error_count,
                'errors': skipped_records
            }

        elif isinstance(data, dict):
            # Validate JSON Structure & Data
            is_valid, checklist, error_msg = cls.validate_backup_json(data)
            if not is_valid:
                return {'success': False, 'error': f"Validation error: {error_msg}", 'success_count': 0, 'error_count': 1, 'duplicate_count': 0}

            try:
                # 1. Update user preferences (default currency)
                user = User.query.get(user_id)
                if user and 'user_preferences' in data:
                    pref = data['user_preferences']
                    if 'default_currency' in pref:
                        user.default_currency = pref['default_currency']
                        db.session.flush()

                # 2. Merge categories by name, update colors, build old_id -> new_id map
                category_map = {}
                for c in data.get('categories', []):
                    name = c['name'].strip()
                    color = c.get('color', '#475569')
                    existing_cat = Category.query.filter_by(user_id=user_id, name=name).first()
                    if existing_cat:
                        existing_cat.color = color
                        category_map[c['id']] = existing_cat.id
                    else:
                        new_cat_uuid = str(uuid.uuid4())
                        new_cat = Category(id=new_cat_uuid, user_id=user_id, name=name, color=color)
                        db.session.add(new_cat)
                        category_map[c['id']] = new_cat_uuid
                
                # 3. Merge payment methods by name, update colors, build old_id -> new_id map
                payment_method_map = {}
                for pm in data.get('payment_methods', []):
                    name = pm['name'].strip()
                    color = pm.get('color', '#475569')
                    existing_pm = PaymentMethod.query.filter_by(user_id=user_id, name=name).first()
                    if existing_pm:
                        existing_pm.color = color
                        payment_method_map[pm['id']] = existing_pm.id
                    else:
                        new_pm_uuid = str(uuid.uuid4())
                        new_pm = PaymentMethod(id=new_pm_uuid, user_id=user_id, name=name, color=color)
                        db.session.add(new_pm)
                        payment_method_map[pm['id']] = new_pm_uuid
                
                db.session.flush()

                # 4. Clear existing expenses
                Expense.query.filter_by(user_id=user_id).delete()
                db.session.flush()

                # 5. Build lookup maps for names
                cat_id_to_name = {c['id']: c['name'] for c in data.get('categories', [])}
                pm_id_to_name = {pm['id']: pm['name'] for pm in data.get('payment_methods', [])}

                # 6. Rebuild and insert expenses with new UUIDs and current user encryption keys
                new_expenses = []
                for e in data.get('expenses', []):
                    cat_name = cat_id_to_name.get(e['category_id'], 'Other')
                    pm_name = pm_id_to_name.get(e['payment_method_id']) if e.get('payment_method_id') else None
                    
                    amount = Decimal(str(e['amount']))
                    expense_date = datetime.strptime(e['expense_date'], "%Y-%m-%d").date()
                    original_amount = Decimal(str(e.get('original_amount') or e['amount']))
                    original_currency = e.get('original_currency') or (user.default_currency if user else 'USD')
                    conversion_rate = Decimal(str(e.get('conversion_rate') or '1.0000'))
                    converted_amount = Decimal(str(e.get('converted_amount') or e['amount']))

                    new_exp = Expense(
                        id=str(uuid.uuid4()),  # Generate new UUID during import (Option B)
                        user_id=user_id,
                        amount=amount,
                        category=cat_name,
                        description=e.get('description') or None,
                        payee=e.get('payee') or None,
                        payment_mode=pm_name,
                        expense_date=expense_date,
                        original_amount=original_amount,
                        original_currency=original_currency,
                        conversion_rate=conversion_rate,
                        converted_amount=converted_amount
                    )
                    new_expenses.append(new_exp)

                if new_expenses:
                    db.session.add_all(new_expenses)
                
                db.session.commit()
                return {
                    'success': True,
                    'success_count': len(new_expenses),
                    'duplicate_count': 0,
                    'error_count': 0
                }

            except Exception as import_err:
                db.session.rollback()
                return {
                    'success': False,
                    'error': f"Import database execution failed: {str(import_err)}",
                    'success_count': 0,
                    'error_count': 1,
                    'duplicate_count': 0
                }
        else:
            return {'success': False, 'error': "Invalid JSON structure. Expected dictionary or list.", 'success_count': 0, 'error_count': 1, 'duplicate_count': 0}

    @classmethod
    def import_csv(cls, user_id, csv_file_stream):
        """Reads, validates, and bulk inserts monthly/bulk expense data from a CSV file stream."""
        try:
            df = pd.read_csv(csv_file_stream)
        except Exception as e:
            return {'success': False, 'error': f"Failed to parse CSV: {str(e)}", 'success_count': 0, 'error_count': 1, 'duplicate_count': 0}

        df.columns = [col.strip().lower().replace(' ', '_') for col in df.columns]

        column_mappings = {
            'amount': ['amount', 'amt', 'value', 'price'],
            'category': ['category', 'cat', 'type', 'genre'],
            'expense_date': ['date', 'expense_date', 'when', 'timestamp'],
            'description': ['description', 'desc', 'message', 'memo', 'info'],
            'payee': ['payee', 'merchant', 'recipient', 'to'],
            'payment_mode': ['payment_mode', 'mode', 'payment_type', 'payment'],
            'original_amount': ['original_amount', 'orig_amount', 'source_amount'],
            'original_currency': ['original_currency', 'orig_currency', 'currency', 'curr'],
            'conversion_rate': ['conversion_rate', 'rate', 'exchange_rate', 'conv_rate']
        }

        resolved_cols = {}
        for target, aliases in column_mappings.items():
            for alias in aliases:
                if alias in df.columns:
                    resolved_cols[target] = alias
                    break

        if 'amount' not in resolved_cols or 'expense_date' not in resolved_cols:
            return {
                'success': False,
                'error': "Invalid CSV schema. Ensure the CSV contains at least 'Amount' and 'Date' columns.",
                'success_count': 0,
                'error_count': 1,
                'duplicate_count': 0
            }

        success_count = 0
        duplicate_count = 0
        error_count = 0
        skipped_records = []
        new_expenses = []

        for idx, row in df.iterrows():
            try:
                raw_amount = row[resolved_cols['amount']]
                amount = Decimal(str(raw_amount))
                if amount <= 0:
                    raise ValueError("Amount must be greater than zero")

                raw_date = str(row[resolved_cols['expense_date']]).strip()
                parsed_dt = pd.to_datetime(raw_date)
                if pd.isna(parsed_dt):
                    raise ValueError("Invalid date value")
                expense_date = parsed_dt.date()

                category = 'Other'
                if 'category' in resolved_cols:
                    category = cls.normalize_category(str(row[resolved_cols['category']]))

                description = None
                if 'description' in resolved_cols:
                    val = str(row[resolved_cols['description']]).strip()
                    if val and val.lower() != 'nan':
                        description = val

                payee = None
                if 'payee' in resolved_cols:
                    val = str(row[resolved_cols['payee']]).strip()
                    if val and val.lower() != 'nan':
                        payee = val

                payment_mode = None
                if 'payment_mode' in resolved_cols:
                    val = str(row[resolved_cols['payment_mode']]).strip()
                    if val and val.lower() != 'nan':
                        payment_mode = val

                if not Category.query.filter_by(user_id=user_id, name=category).first():
                    db.session.add(Category(user_id=user_id, name=category))
                    db.session.commit()

                if payment_mode:
                    if not PaymentMethod.query.filter_by(user_id=user_id, name=payment_mode).first():
                        db.session.add(PaymentMethod(user_id=user_id, name=payment_mode))
                        db.session.commit()

                user = User.query.get(user_id)
                default_currency = user.default_currency if user else 'USD'

                orig_currency = None
                if 'original_currency' in resolved_cols:
                    val = str(row[resolved_cols['original_currency']]).strip().upper()
                    if val and val != 'NAN' and val != 'NONE':
                        orig_currency = val
                if not orig_currency:
                    orig_currency = default_currency

                orig_amount = None
                if 'original_amount' in resolved_cols:
                    val = row[resolved_cols['original_amount']]
                    if pd.notna(val):
                        orig_amount = Decimal(str(val))
                if orig_amount is None:
                    orig_amount = amount

                rate = Decimal('1.0000')
                if 'conversion_rate' in resolved_cols:
                    val = row[resolved_cols['conversion_rate']]
                    if pd.notna(val):
                        try:
                            rate = Decimal(str(val))
                        except Exception:
                            rate = Decimal('1.0000')

                if orig_currency != default_currency:
                    canonical_amount = orig_amount * rate
                else:
                    canonical_amount = amount
                    rate = Decimal('1.0000')

                if cls.check_duplicate(user_id, canonical_amount, expense_date, category, description):
                    duplicate_count += 1
                    continue

                expense = Expense(
                    user_id=user_id,
                    amount=canonical_amount,
                    category=category,
                    description=description,
                    payee=payee,
                    payment_mode=payment_mode,
                    expense_date=expense_date,
                    original_amount=orig_amount,
                    original_currency=orig_currency,
                    conversion_rate=rate,
                    converted_amount=canonical_amount
                )
                new_expenses.append(expense)
                success_count += 1

            except Exception as row_err:
                error_count += 1
                skipped_records.append({
                    'row_number': idx + 2,
                    'reason': str(row_err)
                })

        if new_expenses:
            try:
                db.session.add_all(new_expenses)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                return {'success': False, 'error': f"Database save error: {str(e)}", 'success_count': 0, 'error_count': error_count, 'duplicate_count': 0}

        return {
            'success': True,
            'success_count': success_count,
            'duplicate_count': duplicate_count,
            'error_count': error_count,
            'errors': skipped_records
        }

from flask import request, jsonify, g
from marshmallow import ValidationError
from app.extensions import db
from app.models.expense import Expense, Category, PaymentMethod
from app.api import api
from app.api.decorators import token_required
from app.api.schemas import CategorySchema, PaymentMethodSchema

category_schema = CategorySchema()
categories_schema = CategorySchema(many=True)
pm_schema = PaymentMethodSchema()
pms_schema = PaymentMethodSchema(many=True)


# CATEGORY API ENDPOINTS
@api.route('/v1/categories', methods=['GET'])
@token_required
def api_list_categories():
    """Lists all user custom categories."""
    categories = Category.query.filter_by(user_id=g.current_user.id).order_by(Category.name).all()
    return jsonify(categories_schema.dump(categories)), 200


@api.route('/v1/categories', methods=['POST'])
@token_required
def api_create_category():
    """Creates a new custom category."""
    json_data = request.get_json() or {}
    try:
        data = category_schema.load(json_data)
    except ValidationError as err:
        return jsonify({'error': 'Bad Request', 'message': err.messages}), 400

    name = data.name.strip()
    if Category.query.filter_by(user_id=g.current_user.id, name=name).first():
        return jsonify({'error': 'Bad Request', 'message': 'Category already exists.'}), 400

    color = data.color if getattr(data, 'color', None) else '#475569'
    new_cat = Category(user_id=g.current_user.id, name=name, color=color)
    try:
        db.session.add(new_cat)
        db.session.commit()
        return jsonify(category_schema.dump(new_cat)), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@api.route('/v1/categories/<uuid_str>', methods=['PUT'])
@token_required
def api_update_category(uuid_str):
    """Updates/Renames a custom category. Cascade renames existing expenses."""
    category = Category.query.filter_by(id=uuid_str, user_id=g.current_user.id).first_or_404()
    json_data = request.get_json() or {}
    new_name = json_data.get('name', '').strip()
    new_color = json_data.get('color', '').strip()
    
    if not new_name:
        return jsonify({'error': 'Bad Request', 'message': 'Name field is required.'}), 400

    # Check for name collisions
    collision = Category.query.filter(Category.user_id == g.current_user.id, Category.name == new_name, Category.id != uuid_str).first()
    if collision:
        return jsonify({'error': 'Bad Request', 'message': 'Another category with this name already exists.'}), 400

    try:
        old_name = category.name
        category.name = new_name
        if new_color:
            category.color = new_color
        # Cascade rename in Expenses in Python since values are encrypted in DB
        expenses = Expense.query.filter_by(user_id=g.current_user.id).all()
        for e in expenses:
            try:
                if e.category == old_name:
                    e.category = new_name
            except Exception:
                continue
        db.session.commit()
        return jsonify(category_schema.dump(category)), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@api.route('/v1/categories/<uuid_str>', methods=['DELETE'])
@token_required
def api_delete_category(uuid_str):
    """Deletes a custom category if no expenses are associated with it."""
    category = Category.query.filter_by(id=uuid_str, user_id=g.current_user.id).first_or_404()
    
    # Check for associated expenses in Python since values are encrypted in DB
    has_expenses = False
    expenses = Expense.query.filter_by(user_id=g.current_user.id).all()
    for e in expenses:
        try:
            if e.category == category.name:
                has_expenses = True
                break
        except Exception:
            continue
            
    if has_expenses:
        return jsonify({'error': 'Bad Request', 'message': f"Cannot delete category '{category.name}' because existing expenses are associated with it."}), 400

    try:
        db.session.delete(category)
        db.session.commit()
        return jsonify({'message': 'Category deleted successfully.'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


# PAYMENT METHOD API ENDPOINTS
@api.route('/v1/payment-methods', methods=['GET'])
@token_required
def api_list_payment_methods():
    """Lists all user custom payment methods."""
    pms = PaymentMethod.query.filter_by(user_id=g.current_user.id).order_by(PaymentMethod.name).all()
    return jsonify(pms_schema.dump(pms)), 200


@api.route('/v1/payment-methods', methods=['POST'])
@token_required
def api_create_payment_method():
    """Creates a new custom payment method."""
    json_data = request.get_json() or {}
    try:
        data = pm_schema.load(json_data)
    except ValidationError as err:
        return jsonify({'error': 'Bad Request', 'message': err.messages}), 400

    name = data.name.strip()
    color = data.color if getattr(data, 'color', None) else '#475569'
    if PaymentMethod.query.filter_by(user_id=g.current_user.id, name=name).first():
        return jsonify({'error': 'Bad Request', 'message': 'Payment method already exists.'}), 400

    new_pm = PaymentMethod(user_id=g.current_user.id, name=name, color=color)
    try:
        db.session.add(new_pm)
        db.session.commit()
        return jsonify(pm_schema.dump(new_pm)), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@api.route('/v1/payment-methods/<uuid_str>', methods=['PUT'])
@token_required
def api_update_payment_method(uuid_str):
    """Updates/Renames a custom payment method. Cascade renames existing expenses."""
    pm = PaymentMethod.query.filter_by(id=uuid_str, user_id=g.current_user.id).first_or_404()
    json_data = request.get_json() or {}
    new_name = json_data.get('name', '').strip()
    new_color = json_data.get('color', '').strip()
    
    if not new_name:
        return jsonify({'error': 'Bad Request', 'message': 'Name field is required.'}), 400

    # Check for name collisions
    collision = PaymentMethod.query.filter(PaymentMethod.user_id == g.current_user.id, PaymentMethod.name == new_name, PaymentMethod.id != uuid_str).first()
    if collision:
        return jsonify({'error': 'Bad Request', 'message': 'Another payment method with this name already exists.'}), 400

    try:
        old_name = pm.name
        pm.name = new_name
        if new_color:
            pm.color = new_color
        # Cascade rename in Expenses in Python since values are encrypted in DB
        expenses = Expense.query.filter_by(user_id=g.current_user.id).all()
        for e in expenses:
            try:
                if e.payment_mode == old_name:
                    e.payment_mode = new_name
            except Exception:
                continue
        db.session.commit()
        return jsonify(pm_schema.dump(pm)), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500


@api.route('/v1/payment-methods/<uuid_str>', methods=['DELETE'])
@token_required
def api_delete_payment_method(uuid_str):
    """Deletes a custom payment method if no expenses are associated with it."""
    pm = PaymentMethod.query.filter_by(id=uuid_str, user_id=g.current_user.id).first_or_404()
    
    # Check for associated expenses in Python since values are encrypted in DB
    has_expenses = False
    expenses = Expense.query.filter_by(user_id=g.current_user.id).all()
    for e in expenses:
        try:
            if e.payment_mode == pm.name:
                has_expenses = True
                break
        except Exception:
            continue
            
    if has_expenses:
        return jsonify({'error': 'Bad Request', 'message': f"Cannot delete payment method '{pm.name}' because existing expenses are associated with it."}), 400

    try:
        db.session.delete(pm)
        db.session.commit()
        return jsonify({'message': 'Payment method deleted successfully.'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Server Error', 'message': str(e)}), 500

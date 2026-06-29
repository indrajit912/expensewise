from flask import g
from flask_login import current_user
from marshmallow import Schema, fields, validate, post_load, ValidationError, validates
from app.extensions import ma
from app.models.expense import Expense, Category, PaymentMethod
from app.models.user import User

class UserSchema(ma.SQLAlchemyAutoSchema):
    """Schema to serialize User details."""
    class Meta:
        model = User
        fields = ('id', 'name', 'email', 'date_joined', 'last_login', 'default_currency', 'encryption_enabled')


class CategorySchema(ma.SQLAlchemyAutoSchema):
    """Schema to validate and serialize Category records."""
    class Meta:
        model = Category
        load_instance = True
        include_fk = True
        fields = ('id', 'name', 'color')

    name = fields.String(required=True, validate=validate.Length(min=1, max=50))
    color = fields.String(required=False, load_default='#475569', validate=validate.Regexp(r'^#([0-9a-fA-F]{6})$', error='Color must be a hex code like #RRGGBB'))


class PaymentMethodSchema(ma.SQLAlchemyAutoSchema):
    """Schema to validate and serialize PaymentMethod records."""
    class Meta:
        model = PaymentMethod
        load_instance = True
        include_fk = True
        fields = ('id', 'name', 'color')

    name = fields.String(required=True, validate=validate.Length(min=1, max=50))
    color = fields.String(required=False, load_default='#475569', validate=validate.Regexp(r'^#([0-9a-fA-F]{6})$', error='Color must be a hex code like #RRGGBB'))


class ExpenseSchema(ma.SQLAlchemyAutoSchema):
    """Schema to validate and serialize Expense records."""
    class Meta:
        model = Expense
        load_instance = True
        include_fk = True
        fields = (
            'id', 'amount', 'category', 'description', 'payee', 'payment_mode', 
            'expense_date', 'original_amount', 'original_currency', 'conversion_rate', 
            'converted_amount', 'created_at', 'updated_at'
        )

    # Add custom validation for categories and amounts
    amount = fields.Decimal(required=True, as_string=True, validate=validate.Range(min=0.01, error="Amount must be positive"))
    category = fields.String(required=True)
    expense_date = fields.Date(required=True)
    payee = fields.String(allow_none=True, validate=validate.Length(max=120))
    payment_mode = fields.String(allow_none=True)
    description = fields.String(allow_none=True)
    original_amount = fields.Decimal(allow_none=True, as_string=True)
    original_currency = fields.String(allow_none=True)
    conversion_rate = fields.Decimal(allow_none=True, as_string=True)
    converted_amount = fields.Decimal(allow_none=True, as_string=True)

    @validates('category')
    def validate_category(self, value, **kwargs):
        if not value:
            raise ValidationError("Category is required.")
        
        # Get active authenticated user (API token or Web session)
        user = g.current_user if hasattr(g, 'current_user') and g.current_user else (current_user if current_user and current_user.is_authenticated else None)
        if user:
            exists = Category.query.filter_by(user_id=user.id, name=value).first() is not None
            if not exists:
                raise ValidationError(f"Invalid category '{value}'. You must add it to your custom categories first.")

    @validates('payment_mode')
    def validate_payment_mode(self, value, **kwargs):
        if value:  # payment mode is optional
            user = g.current_user if hasattr(g, 'current_user') and g.current_user else (current_user if current_user and current_user.is_authenticated else None)
            if user:
                exists = PaymentMethod.query.filter_by(user_id=user.id, name=value).first() is not None
                if not exists:
                    raise ValidationError(f"Invalid payment mode '{value}'. You must add it to your custom payment methods first.")


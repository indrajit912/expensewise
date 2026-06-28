import uuid
from decimal import Decimal
from datetime import datetime, date, timezone
from app.extensions import db
from app.services.encryption_service import EncryptionService

class Expense(db.Model):
    """Expense Model representing individual spending records (encrypted at rest)."""
    __tablename__ = 'expenses'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Encrypted fields stored in the database
    amount_enc = db.Column(db.Text, nullable=False)
    category_enc = db.Column(db.Text, nullable=False)
    description_enc = db.Column(db.Text, nullable=True)
    payee_enc = db.Column(db.Text, nullable=True)
    payment_mode_enc = db.Column(db.Text, nullable=True)
    expense_date_enc = db.Column(db.Text, nullable=False)
    
    # Currency enhancement columns (encrypted)
    original_amount_enc = db.Column(db.Text, nullable=True)
    original_currency_enc = db.Column(db.Text, nullable=True)
    conversion_rate_enc = db.Column(db.Text, nullable=True)
    converted_amount_enc = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = db.relationship('User', back_populates='expenses')

    # Getters and setters for transparent encryption/decryption
    @property
    def amount(self):
        val = EncryptionService.decrypt(self.amount_enc)
        return Decimal(val) if val else None

    @amount.setter
    def amount(self, value):
        if value is not None:
            self.amount_enc = EncryptionService.encrypt(str(value))

    @property
    def category(self):
        return EncryptionService.decrypt(self.category_enc)

    @category.setter
    def category(self, value):
        if value is not None:
            self.category_enc = EncryptionService.encrypt(value)

    @property
    def description(self):
        return EncryptionService.decrypt(self.description_enc)

    @description.setter
    def description(self, value):
        self.description_enc = EncryptionService.encrypt(value) if value else None

    @property
    def payee(self):
        return EncryptionService.decrypt(self.payee_enc)

    @payee.setter
    def payee(self, value):
        self.payee_enc = EncryptionService.encrypt(value) if value else None

    @property
    def payment_mode(self):
        return EncryptionService.decrypt(self.payment_mode_enc)

    @payment_mode.setter
    def payment_mode(self, value):
        self.payment_mode_enc = EncryptionService.encrypt(value) if value else None

    @property
    def expense_date(self):
        val = EncryptionService.decrypt(self.expense_date_enc)
        return date.fromisoformat(val) if val else None

    @expense_date.setter
    def expense_date(self, value):
        if value is not None:
            if isinstance(value, (date, datetime)):
                self.expense_date_enc = EncryptionService.encrypt(value.isoformat())
            else:
                self.expense_date_enc = EncryptionService.encrypt(str(value))

    @property
    def original_amount(self):
        val = EncryptionService.decrypt(self.original_amount_enc)
        return Decimal(val) if val else self.amount

    @original_amount.setter
    def original_amount(self, value):
        if value is not None:
            self.original_amount_enc = EncryptionService.encrypt(str(value))
        else:
            self.original_amount_enc = None

    @property
    def original_currency(self):
        val = EncryptionService.decrypt(self.original_currency_enc)
        if not val and self.user:
            return self.user.default_currency
        return val or 'USD'

    @original_currency.setter
    def original_currency(self, value):
        if value is not None:
            self.original_currency_enc = EncryptionService.encrypt(value)
        else:
            self.original_currency_enc = None

    @property
    def conversion_rate(self):
        val = EncryptionService.decrypt(self.conversion_rate_enc)
        return Decimal(val) if val else Decimal('1.0000')

    @conversion_rate.setter
    def conversion_rate(self, value):
        if value is not None:
            self.conversion_rate_enc = EncryptionService.encrypt(str(value))
        else:
            self.conversion_rate_enc = None

    @property
    def converted_amount(self):
        val = EncryptionService.decrypt(self.converted_amount_enc)
        return Decimal(val) if val else self.amount

    @converted_amount.setter
    def converted_amount(self, value):
        if value is not None:
            self.converted_amount_enc = EncryptionService.encrypt(str(value))
        else:
            self.converted_amount_enc = None

    def to_dict(self):
        """Helper to convert database columns to dictionary representations (useful for JSON APIs)."""
        return {
            'id': self.id,
            'amount': float(self.amount) if self.amount else 0.0,
            'category': self.category,
            'description': self.description,
            'payee': self.payee,
            'payment_mode': self.payment_mode,
            'expense_date': self.expense_date.isoformat() if self.expense_date else '',
            'original_amount': float(self.original_amount) if self.original_amount else 0.0,
            'original_currency': self.original_currency,
            'conversion_rate': float(self.conversion_rate) if self.conversion_rate else 1.0,
            'converted_amount': float(self.converted_amount) if self.converted_amount else 0.0,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

    def __repr__(self):
        try:
            return f"<Expense {self.category} - {self.amount} on {self.expense_date}>"
        except Exception:
            return f"<Expense Locked/Encrypted id={self.id}>"


class Category(db.Model):
    """Category Model unique to each user."""
    __tablename__ = 'categories'
    __table_args__ = (db.UniqueConstraint('user_id', 'name', name='_user_category_uc'),)

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(50), nullable=False)
    color = db.Column(db.String(20), nullable=False, default='#475569')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), server_default=db.text('CURRENT_TIMESTAMP'))

    user = db.relationship('User', backref=db.backref('custom_categories', cascade='all, delete-orphan'))


class PaymentMethod(db.Model):
    """Payment Method Model unique to each user."""
    __tablename__ = 'payment_methods'
    __table_args__ = (db.UniqueConstraint('user_id', 'name', name='_user_payment_method_uc'),)

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(50), nullable=False)
    color = db.Column(db.String(20), nullable=False, default='#475569')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), server_default=db.text('CURRENT_TIMESTAMP'))

    user = db.relationship('User', backref=db.backref('custom_payment_methods', cascade='all, delete-orphan'))


class Budget(db.Model):
    """Budget Model to store monthly category-wise budgets."""
    __tablename__ = 'budgets'
    __table_args__ = (db.UniqueConstraint('user_id', 'month', 'category_name', name='_user_month_category_budget_uc'),)

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    month = db.Column(db.String(7), nullable=False)  # format YYYY-MM
    category_name = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), server_default=db.text('CURRENT_TIMESTAMP'))

    user = db.relationship('User', backref=db.backref('budgets', cascade='all, delete-orphan'))

from flask_wtf import FlaskForm
from wtforms import DecimalField, StringField, SelectField, TextAreaField, DateField, SubmitField
from wtforms.validators import DataRequired, Optional, NumberRange, Length
from datetime import date

class ExpenseForm(FlaskForm):
    """Form to add or edit an individual expense."""
    amount = DecimalField('Amount', validators=[
        DataRequired(message="Please enter a valid amount"),
        NumberRange(min=0.01, message="Amount must be greater than zero")
    ])
    
    currency = SelectField('Currency', choices=[
        ('INR', 'INR (₹)'),
        ('USD', 'USD ($)'),
        ('EUR', 'EUR (€)'),
        ('GBP', 'GBP (£)'),
        ('JPY', 'JPY (¥)'),
        ('AUD', 'AUD (A$)'),
        ('CAD', 'CAD (C$)')
    ], validators=[DataRequired()])
    
    category = SelectField('Category', choices=[], validators=[DataRequired()])
    
    conversion_rate = DecimalField('Conversion Rate', validators=[Optional()])
    
    expense_date = DateField('Date', default=date.today, validators=[DataRequired()])
    
    payee = StringField('Payee / Merchant', validators=[Optional(), Length(max=120)])
    
    payment_mode = SelectField('Payment Mode', choices=[], validators=[Optional()])
    
    description = TextAreaField('Description / Notes', validators=[Optional()])
    
    submit = SubmitField('Save Expense')

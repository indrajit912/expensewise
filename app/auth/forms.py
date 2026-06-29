from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError
import re
from app.models.user import User
from app.services.timezone_service import TimezoneService

def validate_password_complexity(form, field):
    """Utility validator to enforce strong passwords."""
    password = field.data
    if not any(c.isupper() for c in password):
        raise ValidationError('Password must contain at least one uppercase letter.')
    if not any(c.islower() for c in password):
        raise ValidationError('Password must contain at least one lowercase letter.')
    if not any(c.isdigit() for c in password):
        raise ValidationError('Password must contain at least one number.')
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        raise ValidationError('Password must contain at least one special character.')


class LoginForm(FlaskForm):
    """Form to handle user logins."""
    email = StringField('Email or Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')


class RegisterForm(FlaskForm):
    """Form to handle new user registration."""
    name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=50)])
    email = StringField('Email Address', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[
        DataRequired(), 
        Length(min=8, message='Password must be at least 8 characters long.'),
        validate_password_complexity
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(), 
        EqualTo('password', message='Passwords must match.')
    ])
    default_currency = SelectField('Default Currency', choices=[
        ('INR', 'INR (₹)'),
        ('USD', 'USD ($)'),
        ('EUR', 'EUR (€)'),
        ('GBP', 'GBP (£)'),
        ('JPY', 'JPY (¥)'),
        ('AUD', 'AUD (A$)'),
        ('CAD', 'CAD (C$)')
    ], validators=[DataRequired()], default='INR')
    timezone = SelectField('Timezone', choices=[('UTC', 'UTC')], validators=[DataRequired()], default='UTC')
    submit = SubmitField('Create Account')

    def validate_email(self, field):
        """Custom validator to check if email address is already taken."""
        user = User.query.filter_by(email=field.data.lower().strip()).first()
        if user:
            raise ValidationError('An account with this email address already exists.')

    def validate_username(self, field):
        """Custom validator to check if username is already taken."""
        user = User.query.filter_by(username=field.data.lower().strip()).first()
        if user:
            raise ValidationError('This username is already taken.')


class ResetPasswordRequestForm(FlaskForm):
    """Form to request a password reset email."""
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    submit = SubmitField('Request Password Reset')


class ResetPasswordForm(FlaskForm):
    """Form to set a new password after confirmation."""
    password = PasswordField('New Password', validators=[
        DataRequired(), 
        Length(min=8, message='Password must be at least 8 characters long.'),
        validate_password_complexity
    ])
    confirm_password = PasswordField('Confirm New Password', validators=[
        DataRequired(), 
        EqualTo('password', message='Passwords must match.')
    ])
    submit = SubmitField('Reset Password')


def populate_timezone_choices(form):
    """Populate timezone field with IANA timezone choices."""
    timezone_list = TimezoneService.get_timezone_list()
    form.timezone.choices = [(tz, tz) for tz in timezone_list]

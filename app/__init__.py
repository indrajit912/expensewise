import os
from flask import Flask, jsonify, render_template, request
from config import config_by_name
from app.extensions import db, migrate, login_manager, csrf, limiter, talisman, cache, mail, ma

def create_app(config_name=None):
    """Flask Application Factory."""
    app = Flask(__name__, instance_relative_config=True)
    
    # Load configuration
    if not config_name:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    app.config.from_object(config_by_name[config_name])
    
    # Ensure the instance directory exists
    os.makedirs(app.instance_path, exist_ok=True)
    
    # Initialize Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    cache.init_app(app)
    mail.init_app(app)
    ma.init_app(app)
    
    # Configure Talisman based on environment
    if app.debug or app.testing:
        # Disable HTTPS force and CSP header blocks for easier local development
        talisman.init_app(
            app, 
            force_https=False, 
            content_security_policy=None,
            session_cookie_secure=False
        )
    else:
        # Standard strict production security headers
        talisman.init_app(
            app,
            force_https=True,
            content_security_policy={
                'default-src': '\'self\'',
                'script-src': ['\'self\'', 'https://cdn.jsdelivr.net', '\'unsafe-inline\''],
                'style-src': ['\'self\'', 'https://cdn.jsdelivr.net', 'https://fonts.googleapis.com', '\'unsafe-inline\''],
                'font-src': ['\'self\'', 'https://fonts.gstatic.com', 'https://cdn.jsdelivr.net'],
                'img-src': ['\'self\'', 'data:'],
                'connect-src': '\'self\''
            }
        )
    
    # Flask-Login Configuration
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'warning'
    
    # Register Blueprints
    from app.auth.routes import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')
    
    from app.dashboard.routes import dashboard as dashboard_blueprint
    app.register_blueprint(dashboard_blueprint)
    
    from app.expenses.routes import expenses as expenses_blueprint
    app.register_blueprint(expenses_blueprint, url_prefix='/expenses')
    
    from app.analytics.routes import analytics as analytics_blueprint
    app.register_blueprint(analytics_blueprint, url_prefix='/analytics')
    
    from app.api import api as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix='/api')
    
    # Global Error Handlers
    register_error_handlers(app)
    
    # Context Processor for standard expense categories
    @app.context_processor
    def inject_categories():
        from flask_login import current_user
        from app.models.expense import Category
        if current_user and current_user.is_authenticated:
            cats = [c.name for c in Category.query.filter_by(user_id=current_user.id).order_by(Category.name).all()]
            if cats:
                return {'EXPENSE_CATEGORIES': cats}
        return {
            'EXPENSE_CATEGORIES': [
                'Food', 'Groceries', 'Rent', 'Utilities', 'Travel', 
                'Entertainment', 'Medical', 'Education', 'Shopping', 'Other'
            ]
        }

    # Context Processor and filter for currency symbols/formatting
    @app.context_processor
    def inject_currency_symbols():
        CURRENCY_SYMBOLS = {
            'INR': '₹',
            'USD': '$',
            'EUR': '€',
            'GBP': '£',
            'JPY': '¥',
            'AUD': 'A$',
            'CAD': 'C$'
        }
        return {'CURRENCY_SYMBOLS': CURRENCY_SYMBOLS}

    @app.context_processor
    def inject_badge_colors():
        from flask_login import current_user
        if current_user and current_user.is_authenticated:
            from app.models.expense import Category, PaymentMethod
            categories = Category.query.filter_by(user_id=current_user.id).all()
            payment_methods = PaymentMethod.query.filter_by(user_id=current_user.id).all()
            return {
                'CATEGORY_COLORS': {c.name: c.color for c in categories},
                'PAYMENT_METHOD_COLORS': {pm.name: pm.color for pm in payment_methods}
            }
        return {
            'CATEGORY_COLORS': {},
            'PAYMENT_METHOD_COLORS': {}
        }

    @app.template_filter('hex_to_rgba')
    def hex_to_rgba(hex_color, alpha=0.15):
        if not hex_color:
            return f'rgba(71, 84, 105, {alpha})'
        cleaned = hex_color.strip().lstrip('#')
        if len(cleaned) != 6:
            return f'rgba(71, 84, 105, {alpha})'
        try:
            r = int(cleaned[0:2], 16)
            g = int(cleaned[2:4], 16)
            b = int(cleaned[4:6], 16)
        except ValueError:
            return f'rgba(71, 84, 105, {alpha})'
        return f'rgba({r}, {g}, {b}, {alpha})'

    @app.template_filter('currency_format')
    def currency_format(amount, currency_code):
        if amount is None:
            return ""
        CURRENCY_SYMBOLS = {
            'INR': '₹',
            'USD': '$',
            'EUR': '€',
            'GBP': '£',
            'JPY': '¥',
            'AUD': 'A$',
            'CAD': 'C$'
        }
        symbol = CURRENCY_SYMBOLS.get(currency_code or 'USD', currency_code or 'USD')
        try:
            return f"{symbol}{float(amount):,.2f}"
        except Exception:
            return f"{symbol}{amount}"
        
    # Register CLI Commands
    from app.cli import bootstrap_system_command, create_admin_command, create_guest_command
    app.cli.add_command(bootstrap_system_command)
    app.cli.add_command(create_admin_command)
    app.cli.add_command(create_guest_command)
        
    return app

def register_error_handlers(app):
    """Registers handlers for 400, 404, and 500 errors."""
    
    def wants_json_response():
        return request.path.startswith('/api/') or request.accept_mimetypes.best == 'application/json'

    @app.errorhandler(400)
    def bad_request(error):
        if wants_json_response():
            return jsonify({'error': 'Bad Request', 'message': str(error.description)}), 400
        return render_template('errors/400.html'), 400

    @app.errorhandler(404)
    def not_found(error):
        if wants_json_response():
            return jsonify({'error': 'Not Found', 'message': 'The requested resource was not found'}), 404
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        if wants_json_response():
            return jsonify({'error': 'Internal Server Error', 'message': 'An unexpected server error occurred'}), 500
        return render_template('errors/500.html'), 500

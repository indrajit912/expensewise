import os
from app import create_app, db
from app.models import User, Expense, APIToken

# Obtain configuration target environment
flask_env = os.environ.get('FLASK_ENV', 'development')
app = create_app(flask_env)

@app.shell_context_processor
def make_shell_context():
    """Provides automatic imports when executing 'flask shell' in the CLI."""
    return dict(db=db, User=User, Expense=Expense, APIToken=APIToken)

if __name__ == '__main__':
    # Use standard development execution configuration if run directly
    app.run(host='0.0.0.0', port=5000)

from flask import Blueprint

# Declare versioned API blueprint (url_prefix registered at /api in application factory)
api = Blueprint('api', __name__)

# Import individual endpoints to trigger route definitions
from app.api import auth, expenses, analytics, categories

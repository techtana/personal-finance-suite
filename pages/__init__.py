from flask import Blueprint

pages_bp = Blueprint("pages", __name__)

# Import routes to register them
from pages.routes import *

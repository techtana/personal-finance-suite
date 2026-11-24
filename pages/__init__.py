from flask import Blueprint

pages_bp = Blueprint("pages", __name__)

# Import routes to register them
from pages.routes import *  # noqa: E402,F401,F403
from pages import pwa  # noqa: E402,F401

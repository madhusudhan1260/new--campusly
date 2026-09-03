"""Single shared SQLAlchemy instance, so models.py and app.py don't import
each other in a circle."""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

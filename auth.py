"""Password hashing, session helpers and route-guarding decorators."""

from __future__ import annotations

from functools import wraps

from flask import abort, flash, redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import User

SESSION_KEY = "user_id"


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return check_password_hash(password_hash, password)


def login_user(user: User) -> None:
    session.clear()
    session[SESSION_KEY] = user.id
    session.permanent = True


def logout_user() -> None:
    session.clear()


def current_user() -> User | None:
    user_id = session.get(SESSION_KEY)
    if user_id is None:
        return None
    return db.session.get(User, user_id)


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapper


def role_required(*roles: str):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                flash("Please log in to continue.", "error")
                return redirect(url_for("login"))
            if user.role not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapper

    return decorator

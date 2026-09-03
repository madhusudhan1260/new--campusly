"""No sign-in wall: every visitor shares one account.

There used to be per-person login/signup here. Removed on request -- the
whole site is now open, including admin actions. current_user() always
resolves to the single seeded account (role=super_admin, created by
_seed_super_admin() in app.py on first run), so bookmarks, claims,
appointments and everything else tied to "the current user" now belong to
that one shared identity instead of to individual people.
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from models import User


def hash_password(password: str) -> str:
    """Still needed to populate the shared account's (never-checked) password_hash column."""
    return generate_password_hash(password)


def current_user() -> User | None:
    return User.query.filter_by(role="super_admin").first()


def login_required(view):
    return view


def role_required(*roles: str):
    def decorator(view):
        return view

    return decorator

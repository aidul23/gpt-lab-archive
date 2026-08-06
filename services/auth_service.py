"""Simple session-based authentication for admin routes."""
import hmac
from functools import wraps

from flask import flash, redirect, request, session, url_for
from werkzeug.security import check_password_hash

import config


def is_admin_logged_in():
    """Return True when the current session has admin access."""
    return session.get("admin_logged_in") is True


def login_admin():
    """Mark the current session as authenticated."""
    session["admin_logged_in"] = True
    session.permanent = True


def logout_admin():
    """Clear admin authentication from the session."""
    session.pop("admin_logged_in", None)


def verify_password(password):
    """Check a submitted password against configured admin credentials."""
    if not password:
        return False

    if config.ADMIN_PASSWORD_HASH:
        return check_password_hash(config.ADMIN_PASSWORD_HASH, password)

    expected = config.ADMIN_PASSWORD
    if not expected:
        return False

    return hmac.compare_digest(password, expected)


def admin_required(view):
    """Decorator that restricts a route to authenticated admins."""

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not is_admin_logged_in():
            flash("Please log in to access the admin area.", "danger")
            next_url = request.path
            return redirect(url_for("admin_login", next=next_url))
        return view(*args, **kwargs)

    return wrapped_view

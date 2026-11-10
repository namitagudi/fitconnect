import functools
import secrets
from flask import session, request, g
from .db import fetch1
from .util import ApiError

EXEMPT = {"/api/auth/login", "/api/auth/register"}


def current_user():
    if "user" not in g:
        uid = session.get("uid")
        g.user = fetch1("SELECT * FROM users WHERE id=?", (uid,)) if uid else None
    return g.user


def login_user(uid):
    session.clear()
    session["uid"] = uid
    session["csrf"] = secrets.token_hex(16)
    g.pop("user", None)


def login_required(f):
    @functools.wraps(f)
    def w(*a, **k):
        if not current_user():
            raise ApiError(401, "auth_required", "Please sign in.")
        return f(*a, **k)
    return w


def admin_required(f):
    @functools.wraps(f)
    @login_required
    def w(*a, **k):
        if current_user()["role"] != "admin":
            raise ApiError(403, "forbidden", "Only the trainer/admin can do this.")
        return f(*a, **k)
    return w


def subscription_required(f):
    @functools.wraps(f)
    @login_required
    def w(*a, **k):
        from .subs import has_access
        if not has_access(current_user()):
            raise ApiError(403, "subscription_required", "An active subscription is needed for this feature. Enter your subscription code in the Membership tab.")
        return f(*a, **k)
    return w


def init_app(app):
    @app.before_request
    def csrf():
        if request.path.startswith("/api/") and request.method in ("POST", "PUT", "PATCH", "DELETE") and request.path not in EXEMPT:
            tok = session.get("csrf")
            if not tok or not secrets.compare_digest(tok, request.headers.get("X-CSRF-Token", "")):
                raise ApiError(403, "csrf", "Your session expired. Please refresh the page and sign in again.")

import calendar
import datetime as dt
import time
from flask import request, current_app


class ApiError(Exception):
    def __init__(self, status, code, message, field=None):
        super().__init__(message)
        self.status, self.code, self.message, self.field = status, code, message, field


def today():
    return current_app.config.get("FAKE_TODAY") or dt.date.today()


def parse_date(v):
    try:
        return dt.date.fromisoformat(str(v))
    except ValueError:
        raise ApiError(422, "invalid", "Dates must look like YYYY-MM-DD")


def add_months(d, m):
    y, mo = d.year + (d.month - 1 + m) // 12, (d.month - 1 + m) % 12 + 1
    return dt.date(y, mo, min(d.day, calendar.monthrange(y, mo)[1]))


def body():
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        raise ApiError(400, "bad_json", "Send a JSON object")
    return d


def vstr(d, k, mn=1, mx=200, req=True, default=None):
    v = d.get(k)
    if v is None or (isinstance(v, str) and not v.strip()):
        if req:
            raise ApiError(422, "invalid", f"{k.replace('_', ' ').capitalize()} is required", k)
        return default
    if not isinstance(v, str):
        raise ApiError(422, "invalid", f"{k} must be text", k)
    v = v.strip()
    if not mn <= len(v) <= mx:
        raise ApiError(422, "invalid", f"{k.replace('_', ' ').capitalize()} must be {mn}-{mx} characters", k)
    return v


def vnum(d, k, lo, hi, req=True, default=None, integer=False):
    v = d.get(k)
    if v is None or v == "":
        if req:
            raise ApiError(422, "invalid", f"{k.replace('_', ' ').capitalize()} is required", k)
        return default
    if isinstance(v, bool):
        raise ApiError(422, "invalid", f"{k} must be a number", k)
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ApiError(422, "invalid", f"{k.replace('_', ' ').capitalize()} must be a number", k)
    if f != f or not lo <= f <= hi:
        raise ApiError(422, "invalid", f"{k.replace('_', ' ').capitalize()} must be between {lo} and {hi}", k)
    return int(round(f)) if integer else f


def vdate(d, k, req=True, default=None):
    v = d.get(k)
    if v is None or v == "":
        if req:
            raise ApiError(422, "invalid", f"{k.capitalize()} is required", k)
        return default
    return parse_date(v).isoformat()


class RateLimit:
    """Small in-memory limiter (per process). Use Redis for multi-server deployments."""
    def __init__(self):
        self.h = {}

    def blocked(self, key, limit, window):
        now = time.time()
        self.h[key] = [t for t in self.h.get(key, []) if now - t < window]
        return len(self.h[key]) >= limit

    def add(self, key):
        self.h.setdefault(key, []).append(time.time())

    def reset(self, key):
        self.h.pop(key, None)

    def check(self, key, limit, window):
        if self.blocked(key, limit, window):
            raise ApiError(429, "rate_limited", "Too many attempts. Please wait a few minutes and try again.")
        self.add(key)


RL = RateLimit()

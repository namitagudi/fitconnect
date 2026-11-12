import datetime as dt
import hmac
import hashlib
import logging
import re
import secrets
from flask import Blueprint, jsonify, request, session, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from .db import fetch, fetch1, run, get_db
from .mailer import send_mail
from .security import login_user, login_required, current_user
from .subs import sub_for_user, sub_info, find_linkable, link
from .util import ApiError, body, vstr, vnum, RL

bp = Blueprint("auth", __name__, url_prefix="/api")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
USERNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.]{2,29}$")
GOALS = {"lose_weight", "maintain", "gain_muscle", "general_fitness"}
RESET_MINUTES = 15


@bp.record_once
def _setup(state):
    """Adds the username column, backfills it for existing accounts, and creates the reset-code table."""
    with state.app.app_context():
        conn = get_db()
        if "username" not in {r["name"] for r in conn.execute("PRAGMA table_info(users)")}:
            conn.execute("ALTER TABLE users ADD COLUMN username TEXT")
        conn.executescript("""CREATE UNIQUE INDEX IF NOT EXISTS users_username_ci ON users(lower(username));
CREATE TABLE IF NOT EXISTS password_resets(id INTEGER PRIMARY KEY, user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 code_hash TEXT NOT NULL, expires_at TEXT NOT NULL, used INT DEFAULT 0, attempts INT DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);""")
        taken = {r["username"].lower() for r in conn.execute("SELECT username FROM users WHERE username IS NOT NULL")}
        for r in conn.execute("SELECT id,email FROM users WHERE username IS NULL").fetchall():
            base = re.sub(r"[^a-z0-9_.]", "", r["email"].split("@")[0].lower())[:24] or "user"
            base = base if len(base) >= 3 else base + "user"
            name, n = base, 1
            while name in taken:
                n += 1
                name = f"{base}{n}"
            taken.add(name)
            conn.execute("UPDATE users SET username=? WHERE id=?", (name, r["id"]))
        conn.commit()


def me_payload(u):
    s = sub_for_user(u["id"])
    pu = {k: v for k, v in u.items() if k != "pw_hash"}
    return {"user": pu, "csrf": session.get("csrf"), "subscription": sub_info(s) if s else None}


def _find(ident):
    """Look an account up by username, falling back to email so older accounts still work."""
    return (fetch1("SELECT * FROM users WHERE lower(username)=lower(?)", (ident,))
            or fetch1("SELECT * FROM users WHERE lower(email)=lower(?)", (ident,)))


def _strong(pw):
    return bool(re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw))


@bp.post("/auth/register")
def register():
    d = body()
    name, username = vstr(d, "name", 2, 60), vstr(d, "username", 3, 30)
    email, pw = vstr(d, "email", 5, 120).lower(), vstr(d, "password", 8, 128)
    if not USERNAME.match(username):
        raise ApiError(422, "invalid", "Username must be 3-30 characters: letters, numbers, dots or underscores.", "username")
    if not EMAIL.match(email):
        raise ApiError(422, "invalid", "Enter a valid email address.", "email")
    if not _strong(pw):
        raise ApiError(422, "weak_password", "Password needs at least 8 characters with letters and numbers.", "password")
    if fetch1("SELECT id FROM users WHERE lower(username)=lower(?)", (username,)):
        raise ApiError(409, "username_taken", "That username is taken. Try another.", "username")
    if fetch1("SELECT id FROM users WHERE email=?", (email,)):
        raise ApiError(409, "email_taken", "An account with this email already exists.", "email")
    code = (d.get("code") or "").strip()
    sub = None
    if code:
        if d.get("consent") is not True:
            raise ApiError(422, "consent_required", "Please tick the box to let your trainer see your progress.", "consent")
        sub = find_linkable(code, request.remote_addr)
    uid = run("INSERT INTO users(email,username,name,pw_hash) VALUES(?,?,?,?)", (email, username, name, generate_password_hash(pw)))
    if sub:
        link(sub, uid)
    login_user(uid)
    return jsonify(me_payload(fetch1("SELECT * FROM users WHERE id=?", (uid,)))), 201


@bp.post("/auth/login")
def login():
    d = body()
    ident = vstr(d, "username" if d.get("username") else "email", 1, 120).lower()
    pw = vstr(d, "password", 1, 128)
    key = f"login:{request.remote_addr}:{ident}"
    if RL.blocked(key, 5, 900):
        raise ApiError(429, "rate_limited", "Too many failed sign-ins. Please wait 15 minutes.")
    u = _find(ident)
    if not u or not check_password_hash(u["pw_hash"], pw):
        RL.add(key)
        raise ApiError(401, "bad_credentials", "Invalid username or password.")
    RL.reset(key)
    login_user(u["id"])
    return jsonify(me_payload(u))


# ---- forgot password: we email a one-time code (passwords are stored hashed, so they can never be sent)
def _code_hash(uid, code):
    return hmac.new(current_app.config["SECRET_KEY"].encode(), f"{uid}:{code}".encode(), hashlib.sha256).hexdigest()


def _utcnow():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@bp.post("/auth/forgot")
def forgot():
    ident = vstr(body(), "username", 1, 120).lower()
    RL.check(f"forgot:{request.remote_addr}:{ident}", 5, 3600)
    u = _find(ident)
    if u:
        code = f"{secrets.randbelow(10 ** 6):06d}"
        exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=RESET_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
        run("UPDATE password_resets SET used=1 WHERE user_id=?", (u["id"],))
        run("INSERT INTO password_resets(user_id,code_hash,expires_at) VALUES(?,?,?)", (u["id"], _code_hash(u["id"], code), exp))
        sent = send_mail(u["email"], "Your Fit Connect password reset code",
                         f"Hi {u['name']},\n\nYour password reset code is: {code}\n\nIt works for {RESET_MINUTES} minutes and can be used once. "
                         "If you didn't ask for this, you can ignore this email and your password will stay the same.\n\nFit Connect")
        if not sent:
            logging.warning("[SETUP] Email isn't configured or failed. Reset code for %s is %s", u["username"], code)
    return jsonify(ok=True, message=f"If that account exists, we've emailed a 6-digit code. It works for {RESET_MINUTES} minutes.")


@bp.post("/auth/reset")
def reset():
    d = body()
    ident, code, pw = vstr(d, "username", 1, 120).lower(), vstr(d, "code", 4, 10), vstr(d, "password", 8, 128)
    RL.check(f"reset:{request.remote_addr}:{ident}", 10, 3600)
    if not _strong(pw):
        raise ApiError(422, "weak_password", "Password needs at least 8 characters with letters and numbers.", "password")
    bad = ApiError(422, "invalid_code", "That code is invalid or has expired. Request a new one.", "code")
    u = _find(ident)
    if not u:
        raise bad
    r = fetch1("SELECT * FROM password_resets WHERE user_id=? AND used=0 ORDER BY id DESC LIMIT 1", (u["id"],))
    if not r or r["expires_at"] < _utcnow() or r["attempts"] >= 5:
        raise bad
    if not hmac.compare_digest(r["code_hash"], _code_hash(u["id"], code.strip())):
        run("UPDATE password_resets SET attempts=attempts+1 WHERE id=?", (r["id"],))
        raise bad
    run("UPDATE users SET pw_hash=? WHERE id=?", (generate_password_hash(pw), u["id"]))
    run("UPDATE password_resets SET used=1 WHERE user_id=?", (u["id"],))
    return jsonify(ok=True)


@bp.post("/auth/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.get("/me")
@login_required
def me():
    return jsonify(me_payload(current_user()))


@bp.patch("/me")
@login_required
def update_me():
    d, u = body(), current_user()
    vals = {"name": vstr(d, "name", 2, 60, req=False, default=u["name"]),
            "age": vnum(d, "age", 5, 110, req=False, default=u["age"], integer=True),
            "height_cm": vnum(d, "height_cm", 100, 230, req=False, default=u["height_cm"]),
            "weight_kg": vnum(d, "weight_kg", 25, 250, req=False, default=u["weight_kg"]),
            "area": vstr(d, "area", 1, 80, req=False, default=u["area"]), "city": vstr(d, "city", 1, 80, req=False, default=u["city"])}
    run("UPDATE users SET name=?,age=?,height_cm=?,weight_kg=?,area=?,city=? WHERE id=?",
        (*vals.values(), u["id"]))
    return jsonify(me_payload(fetch1("SELECT * FROM users WHERE id=?", (u["id"],))))


@bp.patch("/me/goals")
@login_required
def goals():
    d, u = body(), current_user()
    gt = vstr(d, "goal_type", 3, 30)
    if gt not in GOALS:
        raise ApiError(422, "invalid", "Choose a valid goal.", "goal_type")
    run("UPDATE users SET goal_type=?,step_goal=?,calorie_goal=?,water_goal_ml=?,workouts_per_week=?,target_weight_kg=?,onboarded=1 WHERE id=?",
        (gt, vnum(d, "step_goal", 1000, 50000, integer=True), vnum(d, "calorie_goal", 800, 6000, integer=True),
         vnum(d, "water_goal_ml", 500, 7000, integer=True), vnum(d, "workouts_per_week", 1, 14, integer=True),
         vnum(d, "target_weight_kg", 25, 250, req=False), u["id"]))
    return jsonify(me_payload(fetch1("SELECT * FROM users WHERE id=?", (u["id"],))))


TABLES = ["activity", "measurements", "workouts", "food_log", "water_log", "posture_sessions", "checkins", "bookings", "routines", "chat_threads"]


@bp.get("/me/export")
@login_required
def export():
    u = current_user()
    out = {"profile": me_payload(u)["user"], "subscription": (sub_info(sub_for_user(u["id"])) if sub_for_user(u["id"]) else None)}
    for t in TABLES:
        out[t] = fetch(f"SELECT * FROM {t} WHERE user_id=?", (u["id"],))
    out["sets"] = fetch("SELECT s.* FROM sets s JOIN workouts w ON w.id=s.workout_id WHERE w.user_id=?", (u["id"],))
    return jsonify(out)


@bp.delete("/me")
@login_required
def delete_me():
    d, u = body(), current_user()
    if not check_password_hash(u["pw_hash"], vstr(d, "password", 1, 128)):
        raise ApiError(403, "bad_credentials", "Password is incorrect.", "password")
    if u["role"] == "admin" and fetch1("SELECT COUNT(*) c FROM users WHERE role='admin'")["c"] < 2:
        raise ApiError(409, "last_admin", "You are the only admin. Create another admin first.")
    run("DELETE FROM users WHERE id=?", (u["id"],))
    session.clear()
    return jsonify(ok=True)
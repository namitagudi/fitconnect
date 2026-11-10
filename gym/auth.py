import re
from flask import Blueprint, jsonify, request, session
from werkzeug.security import generate_password_hash, check_password_hash
from .db import fetch, fetch1, run
from .security import login_user, login_required, current_user
from .subs import sub_for_user, sub_info, find_linkable, link
from .util import ApiError, body, vstr, vnum, RL

bp = Blueprint("auth", __name__, url_prefix="/api")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
GOALS = {"lose_weight", "maintain", "gain_muscle", "general_fitness"}


def me_payload(u):
    s = sub_for_user(u["id"])
    pu = {k: v for k, v in u.items() if k != "pw_hash"}
    return {"user": pu, "csrf": session.get("csrf"), "subscription": sub_info(s) if s else None}


@bp.post("/auth/register")
def register():
    d = body()
    name, email, pw = vstr(d, "name", 2, 60), vstr(d, "email", 5, 120).lower(), vstr(d, "password", 8, 128)
    if not EMAIL.match(email):
        raise ApiError(422, "invalid", "Enter a valid email address.", "email")
    if not (re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw)):
        raise ApiError(422, "weak_password", "Password needs at least 8 characters with letters and numbers.", "password")
    if fetch1("SELECT id FROM users WHERE email=?", (email,)):
        raise ApiError(409, "email_taken", "An account with this email already exists.", "email")
    code = (d.get("code") or "").strip()
    sub = None
    if code:
        if d.get("consent") is not True:
            raise ApiError(422, "consent_required", "Please tick the box to let your trainer see your progress.", "consent")
        sub = find_linkable(code, request.remote_addr)
    uid = run("INSERT INTO users(email,name,pw_hash) VALUES(?,?,?)", (email, name, generate_password_hash(pw)))
    if sub:
        link(sub, uid)
    login_user(uid)
    return jsonify(me_payload(fetch1("SELECT * FROM users WHERE id=?", (uid,)))), 201


@bp.post("/auth/login")
def login():
    d = body()
    email, pw = vstr(d, "email", 3, 120).lower(), vstr(d, "password", 1, 128)
    key = f"login:{request.remote_addr}:{email}"
    if RL.blocked(key, 5, 900):
        raise ApiError(429, "rate_limited", "Too many failed sign-ins. Please wait 15 minutes.")
    u = fetch1("SELECT * FROM users WHERE email=?", (email,))
    if not u or not check_password_hash(u["pw_hash"], pw):
        RL.add(key)
        raise ApiError(401, "bad_credentials", "Invalid email or password.")
    RL.reset(key)
    login_user(u["id"])
    return jsonify(me_payload(u))


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
         vnum(d, "water_goal_ml", 500, 6000, integer=True), vnum(d, "workouts_per_week", 1, 14, integer=True),
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

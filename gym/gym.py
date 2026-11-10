"""Check-in/attendance, food database admin, analytics, announcements, settings, CSV reports.
Creates its own tables on startup, so db.py does not need to change."""
import csv
import datetime as dt
import io
import sqlite3
from flask import Blueprint, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash
import re
from .db import fetch, fetch1, run, runc, get_db
from .security import login_required, subscription_required, admin_required, current_user
from .subs import sub_info
from .util import ApiError, body, vstr, vnum, today, parse_date

bp = Blueprint("gym", __name__, url_prefix="/api")
SCHEMA = """
CREATE TABLE IF NOT EXISTS attendance(id INTEGER PRIMARY KEY, user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 date TEXT NOT NULL, check_in TEXT NOT NULL, check_out TEXT, by_admin INT DEFAULT 0);
CREATE INDEX IF NOT EXISTS att_user_date ON attendance(user_id,date);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS announcements(id INTEGER PRIMARY KEY, audience TEXT NOT NULL, message TEXT NOT NULL, sent_to INT,
 by_user_id INT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
"""


@bp.record_once
def _setup(state):
    with state.app.app_context():
        get_db().executescript(SCHEMA)


def now_hm():
    return dt.datetime.now().strftime("%H:%M")


def mins(a, b):
    h1, m1 = map(int, a.split(":"))
    h2, m2 = map(int, b.split(":"))
    return max(h2 * 60 + m2 - h1 * 60 - m1, 0)


def _in(uid, by=0):
    if fetch1("SELECT 1 FROM attendance WHERE user_id=? AND date=? AND check_out IS NULL", (uid, today().isoformat())):
        raise ApiError(409, "already_in", "Already checked in.")
    run("INSERT INTO attendance(user_id,date,check_in,by_admin) VALUES(?,?,?,?)", (uid, today().isoformat(), now_hm(), by))


def _out(uid):
    n = runc("UPDATE attendance SET check_out=? WHERE id=(SELECT id FROM attendance WHERE user_id=? AND date=? AND check_out IS NULL ORDER BY id DESC LIMIT 1)",
             (now_hm(), uid, today().isoformat()))
    if not n:
        raise ApiError(409, "not_in", "You are not checked in.")


# ---- member check-in
@bp.get("/attendance/me")
@subscription_required
def my_att():
    u, t = current_user(), today().isoformat()
    rows = fetch("SELECT * FROM attendance WHERE user_id=? ORDER BY date DESC,id DESC LIMIT 60", (u["id"],))
    for r in rows:
        r["minutes"] = mins(r["check_in"], r["check_out"]) if r["check_out"] else None
    todays = [r for r in rows if r["date"] == t]
    days = {r["date"] for r in rows}
    d, streak = parse_date(t), 0
    if t not in days:
        d -= dt.timedelta(days=1)
    while d.isoformat() in days:
        streak += 1
        d -= dt.timedelta(days=1)
    ms = [r["minutes"] for r in rows if r["minutes"]]
    return jsonify(open=next((r for r in todays if not r["check_out"]), None), today=todays, history=rows[:15],
                   visits_month=len({r["date"] for r in rows if r["date"][:7] == t[:7]}),
                   avg_minutes=round(sum(ms) / len(ms)) if ms else 0, streak=streak)


@bp.post("/attendance/checkin")
@subscription_required
def checkin():
    _in(current_user()["id"])
    return jsonify(ok=True), 201


@bp.post("/attendance/checkout")
@subscription_required
def checkout():
    _out(current_user()["id"])
    return jsonify(ok=True)


# ---- admin attendance
CONSENTED = "u.trainer_consent=1 AND u.role='member'"


@bp.get("/admin/attendance")
@admin_required
def admin_att():
    t = today()
    rows = {r["user_id"]: r for r in fetch("SELECT * FROM attendance WHERE date=? ORDER BY id", (t.isoformat(),))}
    members = []
    for u in fetch(f"SELECT u.id,u.name FROM users u WHERE {CONSENTED} ORDER BY u.name"):
        r = rows.get(u["id"])
        members.append({**u, "status": "in" if r and not r["check_out"] else "out" if r else "none",
                        "check_in": r["check_in"] if r else None, "check_out": r["check_out"] if r else None})
    last14 = []
    for i in range(13, -1, -1):
        d = (t - dt.timedelta(days=i)).isoformat()
        last14.append({"date": d, "count": fetch1("SELECT COUNT(DISTINCT user_id) c FROM attendance WHERE date=?", (d,))["c"]})
    return jsonify(date=t.isoformat(), members=members, last14=last14)


@bp.post("/admin/attendance/toggle")
@admin_required
def toggle():
    uid = vnum(body(), "user_id", 1, 10 ** 9, integer=True)
    if not fetch1(f"SELECT 1 FROM users u WHERE u.id=? AND {CONSENTED}", (uid,)):
        raise ApiError(404, "not_found", "Member not found.")
    if fetch1("SELECT 1 FROM attendance WHERE user_id=? AND date=? AND check_out IS NULL", (uid, today().isoformat())):
        _out(uid)
        return jsonify(ok=True, status="out")
    _in(uid, 1)
    return jsonify(ok=True, status="in")


# ---- food database admin + member intake
def _food(d):
    return (vstr(d, "name", 2, 80), vnum(d, "kcal", 0, 900), vnum(d, "protein", 0, 100), vnum(d, "carbs", 0, 100), vnum(d, "fat", 0, 100),
            vstr(d, "serving_label", 1, 40, req=False), vnum(d, "serving_g", 1, 2000, req=False))


@bp.post("/admin/foods")
@admin_required
def add_food():
    try:
        fid = run("INSERT INTO foods(name,kcal,protein,carbs,fat,serving_label,serving_g) VALUES(?,?,?,?,?,?,?)", _food(body()))
    except sqlite3.IntegrityError:
        raise ApiError(409, "exists", "A food with this name already exists.", "name")
    return jsonify(id=fid), 201


@bp.put("/admin/foods/<int:fid>")
@admin_required
def edit_food(fid):
    if not runc("UPDATE foods SET name=?,kcal=?,protein=?,carbs=?,fat=?,serving_label=?,serving_g=? WHERE id=?", (*_food(body()), fid)):
        raise ApiError(404, "not_found", "Food not found.")
    return jsonify(ok=True)


@bp.delete("/admin/foods/<int:fid>")
@admin_required
def del_food(fid):
    run("DELETE FROM foods WHERE id=?", (fid,))
    return jsonify(ok=True)


@bp.get("/admin/nutrition/today")
@admin_required
def nutrition_today():
    t = today().isoformat()
    rows = fetch(f"SELECT u.id,u.name,(SELECT COALESCE(SUM(kcal),0) FROM food_log f WHERE f.user_id=u.id AND f.date=?) kcal,"
                 f"(SELECT COALESCE(SUM(ml),0) FROM water_log w WHERE w.user_id=u.id AND w.date=?) water_ml FROM users u WHERE {CONSENTED} ORDER BY u.name", (t, t))
    return jsonify(members=rows, note="Estimates. Only members who consented are shown.")


# ---- analytics + exports
@bp.get("/admin/analytics")
@admin_required
def analytics():
    t = today()
    d30, d56, d90 = ((t - dt.timedelta(days=n)).isoformat() for n in (30, 56, 90))
    new = fetch1("SELECT COUNT(*) c FROM users WHERE role='member' AND date(created_at)>=?", (d30,))["c"]
    checks = fetch1("SELECT COUNT(*) c FROM attendance WHERE date>=?", (d30,))["c"]
    wk = fetch1("SELECT COUNT(*) c FROM workouts WHERE date>=?", (d30,))["c"]
    ren = fetch1("SELECT COUNT(*) c FROM renewals r JOIN subscriptions s ON s.id=r.subscription_id WHERE s.is_demo=0 AND r.kind='renew' AND date(r.created_at)>=?", (d90,))["c"]
    exp = sum(1 for s in fetch("SELECT * FROM subscriptions WHERE is_demo=0") if sub_info(s)["status"] == "expired")
    weekday = [0] * 7
    for r in fetch("SELECT date FROM attendance WHERE date>=?", (d56,)):
        weekday[parse_date(r["date"]).weekday()] += 1
    top = fetch("SELECT s.exercise, COUNT(*) n FROM sets s JOIN workouts w ON w.id=s.workout_id WHERE w.date>=? GROUP BY s.exercise ORDER BY n DESC LIMIT 8", (d30,))
    return jsonify(new_members_30d=new, avg_daily_checkins=round(checks / 30, 1), workouts_30d=wk,
                   renewal_rate=round(100 * ren / (ren + exp)) if ren + exp else None, weekday=weekday, top_exercises=top,
                   note="Renewal rate = renewals in the last 90 days / (those renewals + currently expired memberships). Demo data excluded.")


def _csv(name, header, rows):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    for r in rows:   # guard against spreadsheet formula injection
        w.writerow(["'" + c if isinstance(c, str) and c and c[0] in "=+-@" else c for c in r])
    return Response(out.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={name}"})


@bp.get("/admin/export.csv")
@admin_required
def export_members():
    d30 = (today() - dt.timedelta(days=30)).isoformat()
    rows = []
    for s in fetch("SELECT * FROM subscriptions WHERE is_demo=0 ORDER BY member_name"):
        i, uid = sub_info(s), s["user_id"]
        v = fetch1("SELECT COUNT(DISTINCT date) c FROM attendance WHERE user_id=? AND date>=?", (uid, d30))["c"] if uid else ""
        w = fetch1("SELECT COUNT(*) c FROM workouts WHERE user_id=? AND date>=?", (uid, d30))["c"] if uid else ""
        rows.append([s["member_name"], s["plan"], i["status"], s["expiry_date"], s["price_inr"], v, w])
    return _csv("members.csv", ["Member", "Plan", "Status", "Expiry", "Price INR", "Visits (30d)", "Workouts (30d)"], rows)


@bp.get("/me/report.csv")
@login_required
def my_report():
    uid, d90 = current_user()["id"], (today() - dt.timedelta(days=90)).isoformat()
    days = {}
    for r in fetch("SELECT date,steps FROM activity WHERE user_id=? AND date>=?", (uid, d90)):
        days.setdefault(r["date"], {})["steps"] = r["steps"]
    for r in fetch("SELECT date,weight_kg FROM measurements WHERE user_id=? AND date>=? AND weight_kg IS NOT NULL", (uid, d90)):
        days.setdefault(r["date"], {})["weight"] = r["weight_kg"]
    for r in fetch("SELECT date,SUM(kcal) k FROM food_log WHERE user_id=? AND date>=? GROUP BY date", (uid, d90)):
        days.setdefault(r["date"], {})["kcal"] = round(r["k"])
    for r in fetch("SELECT date,SUM(ml) m FROM water_log WHERE user_id=? AND date>=? GROUP BY date", (uid, d90)):
        days.setdefault(r["date"], {})["water"] = r["m"]
    return _csv("my-report.csv", ["Date", "Steps", "Weight kg", "Food kcal (est.)", "Water ml"],
                [[d, v.get("steps", ""), v.get("weight", ""), v.get("kcal", ""), v.get("water", "")] for d, v in sorted(days.items(), reverse=True)])


# ---- announcements
@bp.post("/admin/announcements")
@admin_required
def announce():
    d = body()
    msg, aud, city = vstr(d, "message", 3, 300), vstr(d, "audience", 3, 20), vstr(d, "city", 1, 80, req=False)
    if aud == "all":
        ids = [r["id"] for r in fetch("SELECT id FROM users WHERE role='member'")]
    elif aud == "expiring":
        ids = [s["user_id"] for s in fetch("SELECT * FROM subscriptions WHERE user_id IS NOT NULL") if sub_info(s)["status"] == "expiring"]
    elif aud == "city":
        if not city:
            raise ApiError(422, "invalid", "Enter a city.", "city")
        ids = [r["id"] for r in fetch("SELECT id FROM users WHERE role='member' AND lower(city)=lower(?)", (city,))]
    else:
        raise ApiError(422, "invalid", "Choose all, expiring or city.", "audience")
    label = aud if aud != "city" else f"city: {city}"
    aid = run("INSERT INTO announcements(audience,message,sent_to,by_user_id) VALUES(?,?,?,?)", (label, msg, len(ids), current_user()["id"]))
    for uid in ids:
        run("INSERT OR IGNORE INTO notifications(user_id,kind,message,dedupe) VALUES(?,?,?,?)", (uid, "announcement", msg, f"ann{aid}:{uid}"))
    return jsonify(id=aid, sent_to=len(ids)), 201


@bp.get("/admin/announcements")
@admin_required
def list_announcements():
    return jsonify(announcements=fetch("SELECT id,audience,message,sent_to,created_at FROM announcements ORDER BY id DESC LIMIT 30"))


# ---- settings + password
def _setting(k, default):
    r = fetch1("SELECT value FROM settings WHERE key=?", (k,))
    return r["value"] if r else default


@bp.get("/settings")
@login_required
def get_settings():
    return jsonify(gym_name=_setting("gym_name", "Fit Connect"))


@bp.put("/admin/settings")
@admin_required
def put_settings():
    run("INSERT INTO settings(key,value) VALUES('gym_name',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (vstr(body(), "gym_name", 2, 60),))
    return jsonify(ok=True)


@bp.post("/me/password")
@login_required
def change_password():
    d, u = body(), current_user()
    if not check_password_hash(u["pw_hash"], vstr(d, "current", 1, 128)):
        raise ApiError(403, "bad_credentials", "Current password is incorrect.", "current")
    new = vstr(d, "new", 8, 128)
    if not (re.search(r"[A-Za-z]", new) and re.search(r"\d", new)):
        raise ApiError(422, "weak_password", "Password needs at least 8 characters with letters and numbers.", "new")
    run("UPDATE users SET pw_hash=? WHERE id=?", (generate_password_hash(new), u["id"]))
    return jsonify(ok=True)
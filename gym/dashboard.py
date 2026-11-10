from flask import Blueprint, jsonify
from .calc import est_activity, bmi
from .db import fetch, fetch1, run
from .security import login_required, current_user
from .subs import sub_for_user, sub_info, member_reminders, admin_reminders
from .util import today

bp = Blueprint("dashboard", __name__, url_prefix="/api")


def day_summary(u, date=None):
    date = date or today().isoformat()
    a = fetch1("SELECT * FROM activity WHERE user_id=? AND date=?", (u["id"], date))
    act = est_activity(a["steps"], u["height_cm"], u["weight_kg"], a["active_minutes"]) if a else None
    f = fetch1("SELECT COALESCE(SUM(kcal),0) k,COALESCE(SUM(protein),0) p,COALESCE(SUM(carbs),0) c,COALESCE(SUM(fat),0) f FROM food_log WHERE user_id=? AND date=?", (u["id"], date))
    w = fetch1("SELECT COALESCE(SUM(ml),0) ml FROM water_log WHERE user_id=? AND date=?", (u["id"], date))
    m = fetch1("SELECT * FROM measurements WHERE user_id=? ORDER BY date DESC LIMIT 1", (u["id"],))
    last_w = fetch1("SELECT date FROM workouts WHERE user_id=? ORDER BY date DESC,id DESC LIMIT 1", (u["id"],))
    wk = fetch1("SELECT COUNT(*) c FROM workouts WHERE user_id=? AND date>=date(?,'-6 day')", (u["id"], date))
    ps = fetch1("SELECT COUNT(*) c FROM posture_sessions WHERE user_id=?", (u["id"],))
    return {"date": date, "activity": act, "food": {k: round(v, 1) for k, v in f.items()}, "water_ml": w["ml"], "latest_measurement": m,
            "bmi": bmi(u["weight_kg"], u["height_cm"], u["age"]), "last_workout_date": last_w["date"] if last_w else None,
            "workouts_last_7_days": wk["c"], "posture_sessions": ps["c"],
            "goals": {"step_goal": u["step_goal"], "calorie_goal": u["calorie_goal"], "water_goal_ml": u["water_goal_ml"],
                      "workouts_per_week": u["workouts_per_week"], "goal_type": u["goal_type"], "target_weight_kg": u["target_weight_kg"]}}


@bp.get("/dashboard")
@login_required
def dashboard():
    u = current_user()
    member_reminders(u["id"])
    s = sub_for_user(u["id"])
    nxt = fetch1("SELECT b.*,t.name trainer_name FROM bookings b JOIN trainers t ON t.id=b.trainer_id WHERE b.user_id=? AND b.date>=? AND b.status IN('requested','confirmed') ORDER BY b.date,b.time LIMIT 1", (u["id"], today().isoformat()))
    unread = fetch1("SELECT COUNT(*) c FROM notifications WHERE user_id=? AND is_read=0", (u["id"],))["c"]
    return jsonify(summary=day_summary(u), subscription=sub_info(s) if s else None, next_booking=nxt, unread_notifications=unread)


@bp.get("/notifications")
@login_required
def notifications():
    u = current_user()
    (admin_reminders if u["role"] == "admin" else member_reminders)(u["id"])
    rows = fetch("SELECT id,kind,message,is_read,created_at FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50", (u["id"],))
    return jsonify(notifications=rows, unread=sum(1 for r in rows if not r["is_read"]))


@bp.post("/notifications/read")
@login_required
def mark_read():
    run("UPDATE notifications SET is_read=1 WHERE user_id=?", (current_user()["id"],))
    return jsonify(ok=True)

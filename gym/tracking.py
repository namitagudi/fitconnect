from flask import Blueprint, jsonify, request
from .calc import est_activity, bmi
from .db import fetch, fetch1, run, get_db
from .security import login_required, current_user
from .util import ApiError, body, vstr, vnum, vdate, parse_date, today

bp = Blueprint("tracking", __name__, url_prefix="/api")


def check_date(ds):
    if parse_date(ds) > today():
        raise ApiError(422, "invalid", "Dates can't be in the future.", "date")
    return ds


# ---- activity (manual entry only)
@bp.put("/activity/<date>")
@login_required
def put_activity(date):
    d, u = body(), current_user()
    date = check_date(parse_date(date).isoformat())
    steps = vnum(d, "steps", 0, 200000, integer=True)
    mins = vnum(d, "active_minutes", 0, 1440, req=False, integer=True)
    run("INSERT INTO activity(user_id,date,steps,active_minutes) VALUES(?,?,?,?) ON CONFLICT(user_id,date) DO UPDATE SET steps=excluded.steps,active_minutes=excluded.active_minutes",
        (u["id"], date, steps, mins))
    return jsonify(date=date, **est_activity(steps, u["height_cm"], u["weight_kg"], mins))


@bp.get("/activity")
@login_required
def get_activity():
    u = current_user()
    days = int(request.args.get("days", 14)) if request.args.get("days", "14").isdigit() else 14
    rows = fetch("SELECT date,steps,active_minutes FROM activity WHERE user_id=? AND date>=date(?,?) ORDER BY date DESC", (u["id"], today().isoformat(), f"-{min(days, 365)} day"))
    out = [{"date": r["date"], **est_activity(r["steps"], u["height_cm"], u["weight_kg"], r["active_minutes"])} for r in rows]
    return jsonify(days=out, step_goal=u["step_goal"],
                   note="Distance, active minutes (when not entered) and calories are estimates from your steps, height and weight. Steps are entered by you.")


@bp.delete("/activity/<date>")
@login_required
def del_activity(date):
    run("DELETE FROM activity WHERE user_id=? AND date=?", (current_user()["id"], date))
    return jsonify(ok=True)


# ---- body measurements
FIELDS = [("weight_kg", 25, 250), ("waist_cm", 30, 250), ("chest_cm", 40, 250), ("hips_cm", 40, 250), ("arm_cm", 10, 80), ("thigh_cm", 20, 120)]


@bp.put("/measurements/<date>")
@login_required
def put_measure(date):
    d, u = body(), current_user()
    date = check_date(parse_date(date).isoformat())
    vals = [vnum(d, k, lo, hi, req=False) for k, lo, hi in FIELDS]
    if all(v is None for v in vals):
        raise ApiError(422, "invalid", "Enter at least one measurement.")
    run("INSERT INTO measurements(user_id,date,weight_kg,waist_cm,chest_cm,hips_cm,arm_cm,thigh_cm) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(user_id,date) DO UPDATE SET "
        + ",".join(f"{k}=excluded.{k}" for k, _, _ in FIELDS), (u["id"], date, *vals))
    if vals[0] and date == today().isoformat():
        run("UPDATE users SET weight_kg=? WHERE id=?", (vals[0], u["id"]))   # shared data: profile weight stays current
    w = vals[0] or u["weight_kg"]
    return jsonify(date=date, bmi=bmi(w, u["height_cm"], u["age"]))


@bp.get("/measurements")
@login_required
def get_measure():
    u = current_user()
    rows = fetch("SELECT * FROM measurements WHERE user_id=? ORDER BY date DESC LIMIT 120", (u["id"],))
    return jsonify(measurements=rows, bmi=bmi(u["weight_kg"], u["height_cm"], u["age"]), target_weight_kg=u["target_weight_kg"])


@bp.delete("/measurements/<date>")
@login_required
def del_measure(date):
    run("DELETE FROM measurements WHERE user_id=? AND date=?", (current_user()["id"], date))
    return jsonify(ok=True)


# ---- routines & workout logbook
def _items(d):
    items = d.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 30:
        raise ApiError(422, "invalid", "Add 1-30 exercises.", "items")
    return [(vstr(i, "exercise", 2, 60), vnum(i, "sets", 1, 20, req=False, integer=True), vnum(i, "reps", 1, 200, req=False, integer=True),
             vnum(i, "weight_kg", 0, 500, req=False)) for i in items if isinstance(i, dict)]


@bp.post("/routines")
@login_required
def add_routine():
    d, u = body(), current_user()
    items = _items(d)
    rid = run("INSERT INTO routines(user_id,name) VALUES(?,?)", (u["id"], vstr(d, "name", 2, 60)))
    for it in items:
        run("INSERT INTO routine_items(routine_id,exercise,sets,reps,weight_kg) VALUES(?,?,?,?,?)", (rid, *it))
    return jsonify(id=rid), 201


@bp.get("/routines")
@login_required
def list_routines():
    u = current_user()
    rs = fetch("SELECT * FROM routines WHERE user_id=? ORDER BY id DESC", (u["id"],))
    for r in rs:
        r["items"] = fetch("SELECT exercise,sets,reps,weight_kg FROM routine_items WHERE routine_id=? ORDER BY id", (r["id"],))
    return jsonify(routines=rs)


@bp.delete("/routines/<int:rid>")
@login_required
def del_routine(rid):
    run("DELETE FROM routines WHERE id=? AND user_id=?", (rid, current_user()["id"]))
    return jsonify(ok=True)


@bp.post("/workouts")
@login_required
def add_workout():
    d, u = body(), current_user()
    date = check_date(vdate(d, "date", req=False, default=today().isoformat()))
    sets = d.get("sets")
    if not isinstance(sets, list) or not 1 <= len(sets) <= 200:
        raise ApiError(422, "invalid", "Add at least one set.", "sets")
    clean = [(vstr(s, "exercise", 2, 60), vnum(s, "reps", 1, 500, integer=True), vnum(s, "weight_kg", 0, 700, req=False, default=0)) for s in sets if isinstance(s, dict)]
    rid = d.get("routine_id")
    if rid is not None and not fetch1("SELECT id FROM routines WHERE id=? AND user_id=?", (rid, u["id"])):
        raise ApiError(404, "not_found", "Routine not found.", "routine_id")
    wid = run("INSERT INTO workouts(user_id,date,routine_id,notes,duration_min) VALUES(?,?,?,?,?)",
              (u["id"], date, rid, vstr(d, "notes", 1, 500, req=False), vnum(d, "duration_min", 1, 600, req=False, integer=True)))
    counts = {}
    for ex, reps, wt in clean:
        counts[ex] = counts.get(ex, 0) + 1
        run("INSERT INTO sets(workout_id,exercise,set_no,reps,weight_kg) VALUES(?,?,?,?,?)", (wid, ex, counts[ex], reps, wt))
    return jsonify(id=wid), 201


@bp.get("/workouts")
@login_required
def list_workouts():
    u = current_user()
    ws = fetch("SELECT * FROM workouts WHERE user_id=? ORDER BY date DESC,id DESC LIMIT 60", (u["id"],))
    for w in ws:
        w["sets"] = fetch("SELECT exercise,set_no,reps,weight_kg FROM sets WHERE workout_id=? ORDER BY id", (w["id"],))
    return jsonify(workouts=ws)


@bp.delete("/workouts/<int:wid>")
@login_required
def del_workout(wid):
    run("DELETE FROM workouts WHERE id=? AND user_id=?", (wid, current_user()["id"]))
    return jsonify(ok=True)


@bp.get("/workouts/prs")
@login_required
def prs():
    rows = fetch("SELECT s.exercise, MAX(s.weight_kg) best_weight_kg, MAX(s.reps) best_reps FROM sets s JOIN workouts w ON w.id=s.workout_id WHERE w.user_id=? GROUP BY s.exercise ORDER BY s.exercise", (current_user()["id"],))
    return jsonify(records=rows)

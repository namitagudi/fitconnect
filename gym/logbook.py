"""Workout logbook: body-part exercise catalogue, saved workouts, history and personal records.
Reuses the existing `workouts` and `sets` tables (adds two optional columns), so older logs keep working
and the dashboard, analytics and AI coach keep reading the same data."""
from flask import Blueprint, jsonify, request
from .db import fetch, fetch1, run, get_db
from .security import login_required, current_user
from .util import ApiError, body, vstr, vnum, vdate, today, parse_date

bp = Blueprint("logbook", __name__, url_prefix="/api/logbook")
PARTS = ["Chest", "Back", "Shoulders", "Biceps", "Triceps", "Legs", "Abs"]
CATALOG = {
    "Chest": ["Bench press", "Incline dumbbell press", "Chest fly", "Push-up", "Cable crossover", "Pec deck"],
    "Back": ["Deadlift", "Lat pulldown", "Seated cable row", "Pull-up", "Bent-over row", "T-bar row"],
    "Shoulders": ["Overhead press", "Lateral raise", "Front raise", "Arnold press", "Rear delt fly", "Shrug"],
    "Biceps": ["Barbell curl", "Dumbbell curl", "Hammer curl", "Preacher curl", "Concentration curl", "Wrist curl"],
    "Triceps": ["Triceps pushdown", "Skull crusher", "Overhead triceps extension", "Close-grip bench press", "Triceps dips", "Triceps kickback"],
    "Legs": ["Squat", "Leg press", "Lunge", "Romanian deadlift", "Leg extension", "Leg curl", "Calf raise"],
    "Abs": ["Plank", "Crunch", "Hanging leg raise", "Russian twist", "Cable crunch", "Ab wheel rollout"],
}
SCHEMA = "CREATE TABLE IF NOT EXISTS exercises(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, body_part TEXT NOT NULL);"
BP_OF = "COALESCE(s.body_part,(SELECT e.body_part FROM exercises e WHERE lower(e.name)=lower(s.exercise)))"


@bp.record_once
def _setup(state):
    with state.app.app_context():
        conn = get_db()
        conn.executescript(SCHEMA)
        have = {r["name"] for r in conn.execute("PRAGMA table_info(sets)")}
        for col, typ in (("exercise_id", "INT"), ("body_part", "TEXT")):
            if col not in have:
                conn.execute(f"ALTER TABLE sets ADD COLUMN {col} {typ}")
        for part, names in CATALOG.items():
            for n in names:
                conn.execute("INSERT OR IGNORE INTO exercises(name,body_part) VALUES(?,?)", (n, part))
        conn.commit()


@bp.get("/exercises")
@login_required
def exercises():
    rows = fetch("SELECT id,name,body_part FROM exercises ORDER BY id")
    return jsonify(body_parts=[{"name": p, "exercises": [{"id": r["id"], "name": r["name"]} for r in rows if r["body_part"] == p]} for p in PARTS])


@bp.post("/workouts")
@login_required
def save_workout():
    d, u = body(), current_user()
    date = vdate(d, "date", req=False, default=today().isoformat())
    if parse_date(date) > today():
        raise ApiError(422, "invalid", "Dates can't be in the future.", "date")
    entries = d.get("entries")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 15:
        raise ApiError(422, "invalid", "Add 1-15 exercises.", "entries")
    clean = []
    for e in entries:
        if not isinstance(e, dict):
            raise ApiError(422, "invalid", "Invalid exercise entry.", "entries")
        ex = fetch1("SELECT * FROM exercises WHERE id=?", (e.get("exercise_id"),))
        if not ex:
            raise ApiError(404, "not_found", "Exercise not found.", "exercise_id")
        sets = e.get("sets")
        if not isinstance(sets, list) or not 1 <= len(sets) <= 30:
            raise ApiError(422, "invalid", f"Add 1-30 sets for {ex['name']}.", "sets")
        rows = []
        for s in sets:
            if not isinstance(s, dict):
                raise ApiError(422, "invalid", "Invalid set.", "sets")
            rows.append((vnum(s, "weight_kg", 0, 700, req=False, default=0), vnum(s, "reps", 1, 500, integer=True)))
        clean.append((ex, rows))
    records = []
    for ex, rows in clean:     # compare with what the member had before this workout
        prior = fetch1("SELECT MAX(s.weight_kg) w, MAX(s.reps) r FROM sets s JOIN workouts w ON w.id=s.workout_id WHERE w.user_id=? AND lower(s.exercise)=lower(?)", (u["id"], ex["name"]))
        mw, mr = max(w for w, _ in rows), max(r for _, r in rows)
        if prior["w"] is not None:
            if mw > prior["w"]:
                records.append({"exercise": ex["name"], "kind": "weight", "value": mw, "previous": prior["w"]})
            elif mw == 0 and prior["w"] == 0 and mr > (prior["r"] or 0):
                records.append({"exercise": ex["name"], "kind": "reps", "value": mr, "previous": prior["r"]})
    wid = run("INSERT INTO workouts(user_id,date,notes,duration_min) VALUES(?,?,?,?)",
              (u["id"], date, vstr(d, "notes", 1, 500, req=False), vnum(d, "duration_min", 1, 600, req=False, integer=True)))
    counts, total = {}, 0
    for ex, rows in clean:
        for w, r in rows:
            counts[ex["id"]] = counts.get(ex["id"], 0) + 1
            run("INSERT INTO sets(workout_id,exercise,set_no,reps,weight_kg,exercise_id,body_part) VALUES(?,?,?,?,?,?,?)",
                (wid, ex["name"], counts[ex["id"]], r, w, ex["id"], ex["body_part"]))
            total += 1
    return jsonify(id=wid, sets=total, new_records=records), 201


@bp.get("/history")
@login_required
def history():
    u, part = current_user(), (request.args.get("body_part") or "").strip()
    ws = fetch("SELECT id,date,notes,duration_min FROM workouts WHERE user_id=? ORDER BY date DESC,id DESC LIMIT 200", (u["id"],))
    if not ws:
        return jsonify(workouts=[])
    ids = [w["id"] for w in ws]
    ss = fetch(f"SELECT s.workout_id,s.exercise,s.set_no,s.reps,s.weight_kg,{BP_OF} bp FROM sets s "
               f"WHERE s.workout_id IN ({','.join('?' * len(ids))}) ORDER BY s.workout_id,s.id", ids)
    by = {}
    for s in ss:
        w = by.setdefault(s["workout_id"], {})
        e = w.setdefault(s["exercise"], {"exercise": s["exercise"], "body_part": s["bp"], "sets": []})
        e["sets"].append({"set_no": s["set_no"], "weight_kg": s["weight_kg"], "reps": s["reps"]})
    out = []
    for w in ws:
        entries = list(by.get(w["id"], {}).values())
        if part and not any(e["body_part"] == part for e in entries):
            continue
        sets = [s for e in entries for s in e["sets"]]
        out.append({**w, "entries": entries, "total_sets": len(sets), "volume_kg": round(sum((s["weight_kg"] or 0) * s["reps"] for s in sets)),
                    "parts": sorted({e["body_part"] for e in entries if e["body_part"]})})
    return jsonify(workouts=out[:60])


@bp.get("/records")
@login_required
def records():
    part = (request.args.get("body_part") or "").strip()
    rows = fetch(f"SELECT s.exercise,s.reps,s.weight_kg,w.date,{BP_OF} bp FROM sets s JOIN workouts w ON w.id=s.workout_id WHERE w.user_id=?", (current_user()["id"],))
    agg = {}
    for r in rows:
        a = agg.setdefault(r["exercise"].lower(), {"exercise": r["exercise"], "body_part": r["bp"], "best_weight_kg": 0, "reps_at_best": 0,
                                                   "best_reps": 0, "est_1rm_kg": None, "date": None})
        w, rp = r["weight_kg"] or 0, r["reps"]
        a["best_reps"] = max(a["best_reps"], rp)
        if a["date"] is None or w > a["best_weight_kg"] or (w == a["best_weight_kg"] and rp > a["reps_at_best"]):
            a["best_weight_kg"], a["reps_at_best"], a["date"] = w, rp, r["date"]
        elif w == a["best_weight_kg"] and rp == a["reps_at_best"] and r["date"] < a["date"]:
            a["date"] = r["date"]
        if w > 0:
            a["est_1rm_kg"] = max(a["est_1rm_kg"] or 0, w * (1 + rp / 30))
    out = sorted((a for a in agg.values() if not part or a["body_part"] == part), key=lambda a: a["exercise"])
    for a in out:
        if a["est_1rm_kg"] is not None:
            a["est_1rm_kg"] = round(a["est_1rm_kg"], 1)
    return jsonify(records=out, note="Estimated one-rep max uses the Epley formula and is most reliable for sets of up to about 10 reps.")


@bp.delete("/workouts/<int:wid>")
@login_required
def delete_workout(wid):
    run("DELETE FROM workouts WHERE id=? AND user_id=?", (wid, current_user()["id"]))
    return jsonify(ok=True)
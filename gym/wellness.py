from flask import Blueprint, jsonify
from .db import fetch, run
from .security import login_required, current_user
from .util import body, vnum, vdate, vstr, today

bp = Blueprint("wellness", __name__, url_prefix="/api/wellness")
SUPPORT = {"tele_manas": "14416", "tele_manas_alt": "1800-891-4416", "emergency": "112",
           "message": "Tele-MANAS is the Government of India's free, confidential mental-health helpline, open 24x7 in many languages. If you or someone else is in immediate danger, call 112."}
RESOURCES = [
    {"id": "box", "title": "Box breathing (4-4-4-4)", "minutes": 3, "steps": ["Breathe in through your nose for 4 seconds.", "Hold for 4 seconds.", "Breathe out slowly for 4 seconds.", "Hold for 4 seconds. Repeat for 3 minutes."]},
    {"id": "478", "title": "4-7-8 relaxing breath", "minutes": 3, "steps": ["Breathe in quietly through the nose for 4 seconds.", "Hold for 7 seconds.", "Breathe out through the mouth for 8 seconds.", "Repeat up to 4 rounds. Stop if you feel dizzy."]},
    {"id": "scan", "title": "Body scan", "minutes": 5, "steps": ["Lie down or sit comfortably and close your eyes.", "Move attention slowly from your toes up to your head.", "Notice each area and let it soften.", "Finish with three slow breaths."]},
    {"id": "stretch", "title": "Desk-friendly neck and shoulder release", "minutes": 4, "steps": ["Roll your shoulders back 5 times.", "Tilt your ear towards one shoulder and hold 15 seconds; switch sides.", "Clasp hands behind you and gently open the chest for 15 seconds.", "Stop if anything hurts."]},
]


@bp.post("/checkins")
@login_required
def checkin():
    d, u = body(), current_user()
    date = vdate(d, "date", req=False, default=today().isoformat())
    mood, stress = vnum(d, "mood", 1, 5, integer=True), vnum(d, "stress", 1, 5, integer=True)
    run("DELETE FROM checkins WHERE user_id=? AND date=?", (u["id"], date))
    run("INSERT INTO checkins(user_id,date,mood,stress,energy,sleep_hours,note) VALUES(?,?,?,?,?,?,?)",
        (u["id"], date, mood, stress, vnum(d, "energy", 1, 5, req=False, integer=True), vnum(d, "sleep_hours", 0, 24, req=False), vstr(d, "note", 1, 500, req=False)))
    return jsonify(ok=True, support=SUPPORT if (mood <= 2 or stress >= 4) else None), 201


@bp.get("/checkins")
@login_required
def checkins():
    return jsonify(checkins=fetch("SELECT date,mood,stress,energy,sleep_hours,note FROM checkins WHERE user_id=? ORDER BY date DESC LIMIT 60", (current_user()["id"],)), support_info=SUPPORT)


@bp.get("/resources")
@login_required
def resources():
    return jsonify(resources=RESOURCES, support=SUPPORT)

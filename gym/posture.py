
import json
from flask import Blueprint, jsonify, request, current_app
from . import pose
from .db import fetch, fetch1, run
from .posture_rules import analyze, NEED
from .security import subscription_required, current_user
from .util import ApiError, RL

bp = Blueprint("posture", __name__, url_prefix="/api/posture")
MAX = 8 * 1024 * 1024


@bp.post("/analyze")
@subscription_required
def analyze_photo():
    u = current_user()
    RL.check(f"posture:{u['id']}", 30, 3600)

    # Accept uppercase, lowercase and mixed-case exercise names
    ex = (request.form.get("exercise") or "").strip().lower()

    if ex not in NEED:
        raise ApiError(422, "invalid", "Choose squat, lunge, pushup or plank.", "exercise")

    f = request.files.get("image")
    if not f:
        raise ApiError(422, "invalid", "Upload a JPG or PNG photo.", "image")

    data = f.read(MAX + 1)
    if len(data) > MAX:
        raise ApiError(413, "too_large", "Photo must be under 8 MB.", "image")

    if not (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n"):
        raise ApiError(422, "invalid", "Please upload a JPG or PNG photo (PDFs aren't supported - save the photo as JPG).", "image")

    lms, w, h = pose.detect(data, current_app.config["POSE_MODEL_PATH"])
    # The photo itself is never stored

    res = analyze(ex, lms, w, h)

    sid = run(
        "INSERT INTO posture_sessions(user_id,exercise,confidence,status,result) VALUES(?,?,?,?,?)",
        (u["id"], ex, res["confidence"], res["status"], json.dumps(res))
    )

    return jsonify(id=sid, **res)


@bp.get("/sessions")
@subscription_required
def sessions():
    rows = fetch(
        "SELECT id,exercise,confidence,status,result,created_at FROM posture_sessions WHERE user_id=? ORDER BY id DESC LIMIT 50",
        (current_user()["id"],)
    )

    for r in rows:
        r["result"] = json.loads(r["result"])
        r["result"].pop("overlay", None)

    return jsonify(sessions=rows)


@bp.delete("/sessions/<int:sid>")
@subscription_required
def del_session(sid):
    run(
        "DELETE FROM posture_sessions WHERE id=? AND user_id=?",
        (sid, current_user()["id"])
    )
    return jsonify(ok=True)


@bp.delete("/sessions")
@subscription_required
def del_all():
    run(
        "DELETE FROM posture_sessions WHERE user_id=?",
        (current_user()["id"],)
    )
    return jsonify(ok=True)

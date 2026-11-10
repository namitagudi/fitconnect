from flask import Blueprint, jsonify
from .dashboard import day_summary
from .db import fetch, fetch1, run
from .security import admin_required, current_user
from .subs import new_code, sub_info, renew, extend, unlink
from .util import ApiError, body, vstr, vnum, vdate, today, add_months, parse_date

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _sub(sid):
    s = fetch1("SELECT * FROM subscriptions WHERE id=?", (sid,))
    if not s:
        raise ApiError(404, "not_found", "Subscription not found.")
    return s


@bp.post("/subscriptions")
@admin_required
def create_sub():
    d, a = body(), current_user()
    start = vdate(d, "start_date", req=False, default=today().isoformat())
    months = vnum(d, "months", 1, 24, integer=True)
    exp = add_months(parse_date(start), months).isoformat()
    code = new_code()
    sid = run("INSERT INTO subscriptions(code,member_name,plan,price_inr,start_date,expiry_date,trainer_id) VALUES(?,?,?,?,?,?,?)",
              (code, vstr(d, "member_name", 2, 60), vstr(d, "plan", 2, 60), vnum(d, "price_inr", 0, 1000000, integer=True), start, exp, a["id"]))
    return jsonify(id=sid, code=code, expiry_date=exp), 201


@bp.get("/subscriptions")
@admin_required
def list_subs():
    out = []
    for s in fetch("SELECT s.*,u.name linked_name,u.email linked_email FROM subscriptions s LEFT JOIN users u ON u.id=s.user_id ORDER BY s.id DESC"):
        i = sub_info(s, admin=True)
        i["linked_name"], i["linked_email"] = s["linked_name"], s["linked_email"]
        out.append(i)
    return jsonify(subscriptions=out)


@bp.post("/subscriptions/<int:sid>/renew")
@admin_required
def do_renew(sid):
    d = body()
    _sub(sid)
    new = renew(sid, vnum(d, "months", 1, 24, integer=True), current_user()["id"], vstr(d, "note", 1, 200, req=False, default=""))
    return jsonify(expiry_date=new, subscription=sub_info(_sub(sid), admin=True))


@bp.post("/subscriptions/<int:sid>/extend")
@admin_required
def do_extend(sid):
    d = body()
    _sub(sid)
    new = extend(sid, vnum(d, "days", 1, 365, integer=True), current_user()["id"], vstr(d, "note", 1, 200, req=False, default=""))
    return jsonify(expiry_date=new, subscription=sub_info(_sub(sid), admin=True))


@bp.post("/subscriptions/<int:sid>/unlink")
@admin_required
def do_unlink(sid):
    _sub(sid)
    unlink(sid)
    return jsonify(ok=True, code=_sub(sid)["code"])


@bp.get("/subscriptions/<int:sid>/history")
@admin_required
def history(sid):
    _sub(sid)
    return jsonify(history=fetch("SELECT * FROM renewals WHERE subscription_id=? ORDER BY id DESC", (sid,)))


@bp.get("/stats")
@admin_required
def stats():
    c = {"total": 0, "active": 0, "expiring": 0, "expired": 0, "upcoming": 0, "linked": 0}
    for s in fetch("SELECT * FROM subscriptions WHERE is_demo=0"):      # demonstration data is excluded from real stats
        c["total"] += 1
        c[sub_info(s)["status"]] += 1
        c["linked"] += 1 if s["user_id"] else 0
    return jsonify(stats=c, note="Demo membership is excluded from these numbers.")


@bp.get("/members")
@admin_required
def members():
    out = []
    rows = fetch("SELECT u.*,s.id sid FROM users u JOIN subscriptions s ON s.user_id=u.id WHERE u.trainer_consent=1 AND u.role='member' ORDER BY u.name")
    for u in rows:
        s = fetch1("SELECT * FROM subscriptions WHERE id=?", (u["sid"],))
        n = fetch1("SELECT note FROM trainer_notes WHERE member_id=?", (u["id"],))
        out.append({"id": u["id"], "name": u["name"], "email": u["email"], "area": u["area"], "subscription": sub_info(s, admin=True),
                    "today": day_summary(u), "note": n["note"] if n else ""})
    return jsonify(members=out, note="Shown only for members who consented when linking their code. Wellness check-ins and AI chats are private.")


@bp.put("/members/<int:uid>/note")
@admin_required
def note(uid):
    if not fetch1("SELECT 1 FROM users WHERE id=? AND trainer_consent=1", (uid,)):
        raise ApiError(404, "not_found", "Member not found.")
    run("INSERT INTO trainer_notes(member_id,note) VALUES(?,?) ON CONFLICT(member_id) DO UPDATE SET note=excluded.note,updated_at=CURRENT_TIMESTAMP", (uid, vstr(body(), "note", 0, 2000, req=False, default="")))
    return jsonify(ok=True)

from flask import Blueprint, jsonify, request
from .db import fetch, fetch1, run
from .security import login_required, current_user
from .subs import sub_for_user, sub_info, find_linkable, link, has_access
from .util import ApiError, body, vstr

bp = Blueprint("membership", __name__, url_prefix="/api")


@bp.get("/membership")
@login_required
def get_membership():
    u = current_user()
    s = sub_for_user(u["id"])
    hist = fetch("SELECT kind,months,days,old_expiry,new_expiry,created_at FROM renewals WHERE subscription_id=? ORDER BY id DESC", (s["id"],)) if s else []
    return jsonify(subscription=sub_info(s) if s else None, history=hist, access=has_access(u),
                   payment_note="Payments are a demonstration only - no money is charged. Your trainer records renewals.")


@bp.post("/membership/link")
@login_required
def link_code():
    d, u = body(), current_user()
    if sub_for_user(u["id"]):
        raise ApiError(409, "already_linked", "Your account is already linked to a subscription.")
    if d.get("consent") is not True:
        raise ApiError(422, "consent_required", "Please tick the box to let your trainer see your progress.", "consent")
    s = find_linkable(vstr(d, "code", 4, 30), f"u{u['id']}")
    link(s, u["id"])
    return get_membership()


@bp.post("/membership/leave")
@login_required
def leave():
    u = current_user()
    s = sub_for_user(u["id"])
    if not s:
        raise ApiError(404, "not_linked", "You are not linked to a subscription.")
    from .subs import unlink
    unlink(s["id"])
    return jsonify(ok=True)


@bp.post("/membership/renewal-request")
@login_required
def renewal_request():
    u = current_user()
    s = sub_for_user(u["id"])
    if not s:
        raise ApiError(404, "not_linked", "Link a subscription code first.")
    from .util import today
    for a in fetch("SELECT id FROM users WHERE role='admin'"):
        run("INSERT OR IGNORE INTO notifications(user_id,kind,message,dedupe) VALUES(?,?,?,?)",
            (a["id"], "renewal_request", f"{u['name']} asked to renew their membership (demo request - no payment taken).",
             f"rr{a['id']}:{s['id']}:{today().isoformat()}"))
    return jsonify(ok=True, message="Request sent. Demo payment - no money was charged. Your trainer will renew your membership.")

import datetime as dt
import secrets
from .db import fetch, fetch1, run, runc
from .util import ApiError, today, parse_date, add_months, RL

ALPHA = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def new_code():
    while True:
        c = "FIT-" + "".join(secrets.choice(ALPHA) for _ in range(4)) + "-" + "".join(secrets.choice(ALPHA) for _ in range(4))
        if not fetch1("SELECT 1 FROM subscriptions WHERE code=?", (c,)):
            return c


def sub_info(s, admin=False):
    t = today()
    exp, st = parse_date(s["expiry_date"]), parse_date(s["start_date"])
    left = (exp - t).days
    status = "expired" if left < 0 else "upcoming" if st > t else "expiring" if left <= 7 else "active"
    out = {"id": s["id"], "member_name": s["member_name"], "plan": s["plan"], "start_date": s["start_date"], "expiry_date": s["expiry_date"],
           "status": status, "days_left": left, "is_demo": bool(s["is_demo"]), "monthly_amount_inr": s["price_inr"],
           "next_renewal_date": s["expiry_date"],
           "label": "DEMONSTRATION DATA - not a real member record" if s["is_demo"] else None}
    if admin:
        out["code"] = s["code"]
        out["user_id"] = s["user_id"]
    return out


def sub_for_user(uid):
    return fetch1("SELECT * FROM subscriptions WHERE user_id=?", (uid,))


def has_access(user):
    if user["role"] == "admin":
        return True
    s = sub_for_user(user["id"])
    return bool(s) and sub_info(s)["status"] in ("active", "expiring")


def find_linkable(code, who):
    key = f"code:{who}"
    if RL.blocked(key, 5, 900):
        raise ApiError(429, "rate_limited", "Too many wrong codes. Please wait a few minutes.")
    s = fetch1("SELECT * FROM subscriptions WHERE code=?", (code.strip().upper(),))
    if not s or s["user_id"]:
        RL.add(key)
        raise ApiError(404, "invalid_code", "This code isn't valid or has already been used.", "code")
    return s


def link(sub, uid):
    if runc("UPDATE subscriptions SET user_id=? WHERE id=? AND user_id IS NULL", (uid, sub["id"])) != 1:
        raise ApiError(409, "code_used", "This code has already been used.", "code")
    run("UPDATE users SET trainer_consent=1 WHERE id=?", (uid,))


def unlink(sub_id, regenerate=True):
    s = fetch1("SELECT * FROM subscriptions WHERE id=?", (sub_id,))
    if s and s["user_id"]:
        run("UPDATE users SET trainer_consent=0 WHERE id=?", (s["user_id"],))
    run("UPDATE subscriptions SET user_id=NULL, code=? WHERE id=?", (new_code() if regenerate else s["code"], sub_id))


def renew(sub_id, months, by, note=""):
    s = fetch1("SELECT * FROM subscriptions WHERE id=?", (sub_id,))
    new = add_months(max(today(), parse_date(s["expiry_date"])), months).isoformat()
    run("UPDATE subscriptions SET expiry_date=? WHERE id=?", (new, sub_id))
    run("INSERT INTO renewals(subscription_id,kind,months,old_expiry,new_expiry,by_user_id,note) VALUES(?,?,?,?,?,?,?)",
        (sub_id, "renew", months, s["expiry_date"], new, by, note))
    return new


def extend(sub_id, days, by, note=""):
    s = fetch1("SELECT * FROM subscriptions WHERE id=?", (sub_id,))
    new = (parse_date(s["expiry_date"]) + dt.timedelta(days=days)).isoformat()
    run("UPDATE subscriptions SET expiry_date=? WHERE id=?", (new, sub_id))
    run("INSERT INTO renewals(subscription_id,kind,days,old_expiry,new_expiry,by_user_id,note) VALUES(?,?,?,?,?,?,?)",
        (sub_id, "extend", days, s["expiry_date"], new, by, note))
    return new


def member_reminders(uid):
    s = sub_for_user(uid)
    if not s:
        return
    left = sub_info(s)["days_left"]
    if left < 0:
        key, msg = "expired", f"Your membership expired on {s['expiry_date']}. Ask your trainer to renew it to keep full access."
    else:
        t = next((t for t in (0, 1, 3, 7) if left <= t), None)
        if t is None:
            return
        key = str(t)
        msg = ("Your membership expires today." if left == 0 else f"Your membership expires in {left} day{'s' if left != 1 else ''} ({s['expiry_date']}).") + " Renew to keep your access."
    run("INSERT OR IGNORE INTO notifications(user_id,kind,message,dedupe) VALUES(?,?,?,?)",
        (uid, "membership", msg, f"sub{s['id']}:{s['expiry_date']}:{key}"))


def admin_reminders(admin_id):
    for s in fetch("SELECT * FROM subscriptions WHERE user_id IS NOT NULL AND is_demo=0"):
        left = sub_info(s)["days_left"]
        if left <= 7:
            word = "expired" if left < 0 else f"expires in {left} day(s)"
            run("INSERT OR IGNORE INTO notifications(user_id,kind,message,dedupe) VALUES(?,?,?,?)",
                (admin_id, "member_expiry", f"{s['member_name']}'s membership {word} ({s['expiry_date']}).",
                 f"adm{admin_id}:sub{s['id']}:{s['expiry_date']}:{'x' if left < 0 else 'w'}"))

"""Trainer profiles: members see name + certificate, admin manages them.
Uses the existing `trainers` table (adds the new columns automatically)."""
import os
import uuid
from flask import Blueprint, jsonify, request, current_app, send_from_directory
from .db import fetch, fetch1, run, get_db
from .security import login_required, admin_required
from .util import ApiError, vstr, vnum

bp = Blueprint("team", __name__, url_prefix="/api")
MAX_CERT = 5 * 1024 * 1024
NEW_COLS = {"specialty": "TEXT", "experience_years": "INT", "cert_title": "TEXT", "cert_file": "TEXT", "cert_mime": "TEXT"}


@bp.record_once
def _setup(state):
    with state.app.app_context():
        db = get_db()
        have = {r["name"] for r in db.execute("PRAGMA table_info(trainers)")}
        for col, typ in NEW_COLS.items():
            if col not in have:
                db.execute(f"ALTER TABLE trainers ADD COLUMN {col} {typ}")
        db.commit()


def cdir():
    d = os.path.join(current_app.config["UPLOAD_DIR"], "certs")
    os.makedirs(d, exist_ok=True)
    return d


def sniff(b):
    if b[:5] == b"%PDF-":
        return "application/pdf", ".pdf"
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg", ".jpg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", ".png"
    return None, None


def save_cert(f):
    data = f.read(MAX_CERT + 1)
    if len(data) > MAX_CERT:
        raise ApiError(413, "too_large", "Certificate must be under 5 MB.", "certificate")
    mime, ext = sniff(data)
    if not mime:
        raise ApiError(422, "invalid_file", "Upload the certificate as a JPG, PNG or PDF.", "certificate")
    name = uuid.uuid4().hex + ext
    with open(os.path.join(cdir(), name), "wb") as o:
        o.write(data)
    return name, mime


def rm(name):
    if name:
        try:
            os.remove(os.path.join(cdir(), name))
        except OSError:
            pass


def public(t):
    return {"id": t["id"], "name": t["name"], "specialty": t.get("specialty"), "experience_years": t.get("experience_years"),
            "bio": t.get("bio"), "contact": t.get("contact"), "cert_title": t.get("cert_title"),
            "has_cert": bool(t.get("cert_file")), "cert_mime": t.get("cert_mime")}


def fields():
    f = request.form
    return (vstr(f, "name", 2, 60), vstr(f, "specialty", 1, 80, req=False), vnum(f, "experience_years", 0, 60, req=False, integer=True),
            vstr(f, "bio", 1, 400, req=False), vstr(f, "contact", 1, 80, req=False), vstr(f, "cert_title", 1, 100, req=False))


def _get(tid):
    t = fetch1("SELECT * FROM trainers WHERE id=?", (tid,))
    if not t:
        raise ApiError(404, "not_found", "Trainer not found.")
    return t


@bp.get("/team")
@login_required
def list_team():
    return jsonify(trainers=[public(t) for t in fetch("SELECT * FROM trainers ORDER BY name")])


@bp.get("/team/<int:tid>/certificate")
@login_required
def certificate(tid):
    t = _get(tid)
    if not t.get("cert_file"):
        raise ApiError(404, "not_found", "No certificate uploaded.")
    r = send_from_directory(cdir(), t["cert_file"], mimetype=t["cert_mime"])
    r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["Content-Disposition"] = "inline"
    return r


@bp.post("/admin/team")
@admin_required
def add_trainer():
    vals = fields()
    f = request.files.get("certificate")
    cf, cm = save_cert(f) if f and f.filename else (None, None)
    tid = run("INSERT INTO trainers(name,specialty,experience_years,bio,contact,cert_title,cert_file,cert_mime) VALUES(?,?,?,?,?,?,?,?)", (*vals, cf, cm))
    return jsonify(id=tid), 201


@bp.put("/admin/team/<int:tid>")
@admin_required
def edit_trainer(tid):
    t = _get(tid)
    vals = fields()
    cf, cm, old = t.get("cert_file"), t.get("cert_mime"), None
    f = request.files.get("certificate")
    if f and f.filename:
        new = save_cert(f)
        old, cf, cm = cf, new[0], new[1]
    elif request.form.get("remove_certificate") == "1":
        old, cf, cm = cf, None, None
    run("UPDATE trainers SET name=?,specialty=?,experience_years=?,bio=?,contact=?,cert_title=?,cert_file=?,cert_mime=? WHERE id=?", (*vals, cf, cm, tid))
    rm(old)
    return jsonify(ok=True)


@bp.delete("/admin/team/<int:tid>")
@admin_required
def delete_trainer(tid):
    t = _get(tid)
    run("DELETE FROM trainers WHERE id=?", (tid,))
    rm(t.get("cert_file"))
    return jsonify(ok=True)
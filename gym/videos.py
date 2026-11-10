import os
import uuid
from flask import Blueprint, jsonify, request, current_app, send_from_directory
from .db import fetch, fetch1, run
from .security import admin_required, subscription_required
from .util import ApiError, vstr

bp = Blueprint("videos", __name__, url_prefix="/api")
THUMB_MAX = 400 * 1024


def vdir():
    d = os.path.join(current_app.config["UPLOAD_DIR"], "videos")
    os.makedirs(d, exist_ok=True)
    return d


def sniff_video(b):
    if b[4:8] == b"ftyp":
        return "video/mp4", ".mp4"
    if b[:4] == b"\x1a\x45\xdf\xa3":
        return "video/webm", ".webm"
    return None, None


def save_video(f):
    head = f.read(16)
    f.seek(0)
    mime, ext = sniff_video(head)
    if not mime or not (f.filename or "").lower().endswith((".mp4", ".webm")):
        raise ApiError(422, "invalid_file", "Please upload an MP4 or WebM video.", "file")
    name = uuid.uuid4().hex + ext
    f.save(os.path.join(vdir(), name))
    return name, mime, os.path.getsize(os.path.join(vdir(), name))


def save_thumb(f):
    if not f:
        return None
    b = f.read(THUMB_MAX + 1)
    if len(b) > THUMB_MAX or b[:3] != b"\xff\xd8\xff":
        raise ApiError(422, "invalid_file", "Thumbnail must be a small JPEG.", "thumb")
    name = uuid.uuid4().hex + ".jpg"
    with open(os.path.join(vdir(), name), "wb") as o:
        o.write(b)
    return name


def rm(name):
    if name:
        try:
            os.remove(os.path.join(vdir(), name))
        except OSError:
            pass


def public(v):
    return {"id": v["id"], "title": v["title"], "category": v["category"], "trainer_name": v["trainer_name"], "instructions": v["instructions"],
            "size": v["size"], "mime": v["mime"], "has_thumb": bool(v["thumb"]), "created_at": v["created_at"]}


def fields():
    f = request.form
    return {"title": vstr(f, "title", 2, 80), "category": vstr(f, "category", 2, 40), "trainer_name": vstr(f, "trainer_name", 2, 60),
            "instructions": vstr(f, "instructions", 1, 3000, req=False, default="")}


@bp.get("/videos")
@subscription_required
def list_videos():
    return jsonify(videos=[public(v) for v in fetch("SELECT * FROM videos ORDER BY id DESC")])


@bp.post("/videos")
@admin_required
def create_video():
    d = fields()
    f = request.files.get("file")
    if not f:
        raise ApiError(422, "invalid", "Choose an MP4 or WebM video.", "file")
    name, mime, size = save_video(f)
    try:
        th = save_thumb(request.files.get("thumb"))
    except ApiError:
        rm(name)
        raise
    vid = run("INSERT INTO videos(title,category,trainer_name,instructions,file,mime,size,thumb) VALUES(?,?,?,?,?,?,?,?)",
              (d["title"], d["category"], d["trainer_name"], d["instructions"], name, mime, size, th))
    return jsonify(id=vid), 201


@bp.put("/videos/<int:vid>")
@admin_required
def update_video(vid):
    v = fetch1("SELECT * FROM videos WHERE id=?", (vid,))
    if not v:
        raise ApiError(404, "not_found", "Video not found.")
    d = fields()
    name, mime, size, old = v["file"], v["mime"], v["size"], []
    f = request.files.get("file")
    if f:
        name, mime, size = save_video(f)
        old.append(v["file"])
    th = v["thumb"]
    nt = save_thumb(request.files.get("thumb"))
    if nt:
        old.append(th)
        th = nt
    run("UPDATE videos SET title=?,category=?,trainer_name=?,instructions=?,file=?,mime=?,size=?,thumb=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (d["title"], d["category"], d["trainer_name"], d["instructions"], name, mime, size, th, vid))
    for o in old:
        rm(o)
    return jsonify(ok=True)


@bp.delete("/videos/<int:vid>")
@admin_required
def delete_video(vid):
    v = fetch1("SELECT * FROM videos WHERE id=?", (vid,))
    if not v:
        raise ApiError(404, "not_found", "Video not found.")
    run("DELETE FROM videos WHERE id=?", (vid,))
    rm(v["file"])
    rm(v["thumb"])
    return jsonify(ok=True)


@bp.get("/videos/<int:vid>/file")
@subscription_required
def video_file(vid):
    v = fetch1("SELECT * FROM videos WHERE id=?", (vid,))
    if not v:
        raise ApiError(404, "not_found", "Video not found.")
    return send_from_directory(vdir(), v["file"], mimetype=v["mime"], conditional=True)   # supports Range requests for seeking


@bp.get("/videos/<int:vid>/thumb")
@subscription_required
def video_thumb(vid):
    v = fetch1("SELECT * FROM videos WHERE id=?", (vid,))
    if not v or not v["thumb"]:
        raise ApiError(404, "not_found", "No thumbnail.")
    return send_from_directory(vdir(), v["thumb"], mimetype="image/jpeg")

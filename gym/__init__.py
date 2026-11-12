import logging
import os
from flask import Flask, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException
from .util import ApiError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def create_app(config=None):
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
    except ImportError:
        pass
    app = Flask(__name__, instance_relative_config=True, static_folder=os.path.join(ROOT, "static"), static_url_path="/static")
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.path.join(app.instance_path, "gym.sqlite"), UPLOAD_DIR=os.path.join(app.instance_path, "uploads"),
        MAX_CONTENT_LENGTH=int(os.environ.get("MAX_UPLOAD_MB", "200")) * 1024 * 1024,
        GEMINI_API_KEY=os.environ.get("GEMINI_API_KEY", ""), GEMINI_MODEL=os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
        POSE_MODEL_PATH=os.environ.get("POSE_MODEL_PATH", os.path.join(ROOT, "models", "pose_landmarker_full.task")),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1", FAKE_TODAY=None)
    if config:
        app.config.update(config)
    if app.config["SECRET_KEY"] == "dev-only-change-me" and not app.config.get("TESTING"):
        logging.warning("SECRET_KEY is the insecure development default. Set a long random SECRET_KEY in .env before deploying.")
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)
    from . import db, security, auth, membership, dashboard, tracking, diet, videos, posture, coach, wellness, admin, gym, trainers, logbook
    db.init_app(app)
    security.init_app(app)
    for m in (auth, membership, dashboard, tracking, diet, videos, posture, coach, wellness, admin, gym, trainers, logbook):
        app.register_blueprint(m.bp)

    @app.errorhandler(ApiError)
    def api_error(e):
        return jsonify(error={"code": e.code, "message": e.message, "field": e.field}), e.status

    @app.errorhandler(HTTPException)
    def http_error(e):
        return jsonify(error={"code": e.name.lower().replace(" ", "_"), "message": {413: "That file is too large."}.get(e.code, e.description)}), e.code

    @app.errorhandler(Exception)
    def crash(e):
        logging.exception("Unhandled error")
        return jsonify(error={"code": "server_error", "message": "Something went wrong on our side. Please try again."}), 500

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/health")
    def health():
        return jsonify(ok=True, ai_configured=bool(app.config["GEMINI_API_KEY"]), pose_model=os.path.exists(app.config["POSE_MODEL_PATH"]))

    return app
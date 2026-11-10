import sqlite3
from flask import g, current_app

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, pw_hash TEXT NOT NULL,
 role TEXT NOT NULL DEFAULT 'member' CHECK(role IN('member','admin')), age INT, height_cm REAL, weight_kg REAL, area TEXT, city TEXT,
 goal_type TEXT, step_goal INT DEFAULT 7000, calorie_goal INT DEFAULT 2000, water_goal_ml INT DEFAULT 2000, workouts_per_week INT DEFAULT 3,
 target_weight_kg REAL, onboarded INT DEFAULT 0, trainer_consent INT DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS subscriptions(id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, member_name TEXT NOT NULL, plan TEXT NOT NULL,
 price_inr INT NOT NULL, start_date TEXT NOT NULL, expiry_date TEXT NOT NULL, user_id INT UNIQUE REFERENCES users(id) ON DELETE SET NULL,
 trainer_id INT REFERENCES users(id) ON DELETE SET NULL, is_demo INT DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS renewals(id INTEGER PRIMARY KEY, subscription_id INT NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
 kind TEXT, months INT, days INT, old_expiry TEXT, new_expiry TEXT, by_user_id INT, note TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY, user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE, kind TEXT,
 message TEXT NOT NULL, dedupe TEXT UNIQUE, is_read INT DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY, user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE, date TEXT NOT NULL,
 steps INT NOT NULL, active_minutes INT, UNIQUE(user_id,date));
CREATE TABLE IF NOT EXISTS measurements(id INTEGER PRIMARY KEY, user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE, date TEXT NOT NULL,
 weight_kg REAL, waist_cm REAL, chest_cm REAL, hips_cm REAL, arm_cm REAL, thigh_cm REAL, UNIQUE(user_id,date));
CREATE TABLE IF NOT EXISTS routines(id INTEGER PRIMARY KEY, user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS routine_items(id INTEGER PRIMARY KEY, routine_id INT NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
 exercise TEXT NOT NULL, sets INT, reps INT, weight_kg REAL);
CREATE TABLE IF NOT EXISTS workouts(id INTEGER PRIMARY KEY, user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE, date TEXT NOT NULL,
 routine_id INT, notes TEXT, duration_min INT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS sets(id INTEGER PRIMARY KEY, workout_id INT NOT NULL REFERENCES workouts(id) ON DELETE CASCADE, exercise TEXT NOT NULL,
 set_no INT, reps INT NOT NULL, weight_kg REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS foods(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, kcal REAL, protein REAL, carbs REAL, fat REAL,
 serving_label TEXT, serving_g REAL);
CREATE TABLE IF NOT EXISTS food_log(id INTEGER PRIMARY KEY, user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE, date TEXT NOT NULL,
 meal TEXT NOT NULL, name TEXT NOT NULL, food_id INT, grams REAL, kcal REAL, protein REAL, carbs REAL, fat REAL, source TEXT,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS water_log(id INTEGER PRIMARY KEY, user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE, date TEXT NOT NULL, ml INT NOT NULL);
CREATE TABLE IF NOT EXISTS videos(id INTEGER PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL, trainer_name TEXT NOT NULL, instructions TEXT,
 file TEXT NOT NULL, mime TEXT, size INT, thumb TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS posture_sessions(id INTEGER PRIMARY KEY, user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE, exercise TEXT,
 confidence REAL, status TEXT, result TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS chat_threads(id INTEGER PRIMARY KEY, user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE, title TEXT,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS chat_messages(id INTEGER PRIMARY KEY, thread_id INT NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
 role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS trainers(id INTEGER PRIMARY KEY, name TEXT NOT NULL, area TEXT, city TEXT, fee_inr INT, bio TEXT, contact TEXT);
CREATE TABLE IF NOT EXISTS bookings(id INTEGER PRIMARY KEY, user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 trainer_id INT NOT NULL REFERENCES trainers(id) ON DELETE CASCADE, date TEXT NOT NULL, time TEXT NOT NULL, note TEXT,
 status TEXT DEFAULT 'requested', payment_status TEXT DEFAULT 'demo_not_charged', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS checkins(id INTEGER PRIMARY KEY, user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE, date TEXT NOT NULL,
 mood INT, stress INT, energy INT, sleep_hours REAL, note TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS trainer_notes(member_id INT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, note TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def fetch(sql, a=()):
    return [dict(r) for r in get_db().execute(sql, a).fetchall()]


def fetch1(sql, a=()):
    r = get_db().execute(sql, a).fetchone()
    return dict(r) if r else None


def run(sql, a=()):
    c = get_db().execute(sql, a)
    get_db().commit()
    return c.lastrowid


def runc(sql, a=()):
    c = get_db().execute(sql, a)
    get_db().commit()
    return c.rowcount


def close_db(e=None):
    d = g.pop("db", None)
    if d:
        d.close()


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        get_db().executescript(SCHEMA)
        from .foods import seed_foods
        seed_foods()

"""Creates the admin (trainer) account and ONE clearly-labelled demo membership. Safe to run more than once."""
import datetime as dt
import os
from werkzeug.security import generate_password_hash
from gym import create_app
from gym.db import fetch1, run


def seed(app):
    with app.app_context():
        email, pw = os.environ.get("ADMIN_EMAIL"), os.environ.get("ADMIN_PASSWORD")
        if email and pw and not fetch1("SELECT id FROM users WHERE email=?", (email.lower(),)):
            run("INSERT INTO users(email,name,pw_hash,role,onboarded) VALUES(?,?,?,?,1)", (email.lower(), os.environ.get("ADMIN_NAME", "Trainer"), generate_password_hash(pw), "admin"))
            print("Created admin:", email)
        elif not (email and pw):
            print("Set ADMIN_EMAIL and ADMIN_PASSWORD in .env to create the admin account.")
        if not fetch1("SELECT id FROM subscriptions WHERE is_demo=1"):
            from gym.util import today
            t = today()
            adm = fetch1("SELECT id FROM users WHERE role='admin' LIMIT 1")
            run("INSERT INTO subscriptions(code,member_name,plan,price_inr,start_date,expiry_date,trainer_id,is_demo) VALUES(?,?,?,?,?,?,?,1)",
                ("FIT-DEMO-2026", "Demo Member", "Monthly Basic (DEMO)", 999, (t - dt.timedelta(days=23)).isoformat(), (t + dt.timedelta(days=7)).isoformat(), adm["id"] if adm else None))
            print("Created demo membership. Code: FIT-DEMO-2026 (DEMONSTRATION DATA)")


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    seed(create_app())

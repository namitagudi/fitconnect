import datetime as dt
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gym import create_app
from gym.util import RL
from gym.posture_rules import analyze
import seed as seedmod

TODAY = dt.date(2026, 6, 15)
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 200
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 100


class C:
    """Test client that remembers the CSRF token."""
    def __init__(self, app):
        self.c, self.csrf = app.test_client(), None

    def req(self, m, path, **kw):
        h = kw.pop("headers", {})
        if self.csrf:
            h["X-CSRF-Token"] = self.csrf
        r = getattr(self.c, m)(path, headers=h, **kw)
        j = r.get_json(silent=True)
        if j and isinstance(j, dict) and j.get("csrf"):
            self.csrf = j["csrf"]
        return r

    def get(self, p, **k): return self.req("get", p, **k)
    def post(self, p, j=None, **k): return self.req("post", p, json=j, **k) if j is not None else self.req("post", p, **k)
    def put(self, p, j=None, **k): return self.req("put", p, json=j, **k) if j is not None else self.req("put", p, **k)
    def patch(self, p, j=None, **k): return self.req("patch", p, json=j, **k)
    def delete(self, p, j=None, **k): return self.req("delete", p, json=j, **k) if j is not None else self.req("delete", p, **k)


def lms(**over):
    L = [[0.5, 0.5, 0.95] for _ in range(33)]
    for k, v in over.items():
        L[int(k[1:])] = list(v)
    return L


def squat_lms(knee_x=0.7, vis=0.95, ankle_vis=None):
    # Left side: shoulder 11, hip 23, knee 25, ankle 27; right side hidden (low visibility)
    d = {"i11": (0.5, 0.3, vis), "i23": (0.5, 0.55, vis), "i25": (knee_x, 0.55, vis), "i27": (knee_x, 0.8, ankle_vis if ankle_vis is not None else vis)}
    for i in (12, 24, 26, 28):
        d[f"i{i}"] = (0.5, 0.5, 0.1)
    return lms(**d)


class Base(unittest.TestCase):
    def setUp(self):
        RL.h.clear()
        self.dir = tempfile.mkdtemp()
        os.environ.update(ADMIN_EMAIL="trainer@test.com", ADMIN_PASSWORD="TrainerPass1", ADMIN_NAME="Coach")
        self.app = create_app({"DATABASE": os.path.join(self.dir, "t.sqlite"), "UPLOAD_DIR": os.path.join(self.dir, "up"), "TESTING": True,
                               "FAKE_TODAY": TODAY, "GEMINI_API_KEY": "test-key", "POSE_MODEL_PATH": "/nonexistent"})
        os.makedirs(self.app.config["UPLOAD_DIR"], exist_ok=True)
        seedmod.seed(self.app)
        self.admin = C(self.app)
        r = self.admin.post("/api/auth/login", {"email": "trainer@test.com", "password": "TrainerPass1"})
        assert r.status_code == 200, r.get_json()

    def member(self, email="m@test.com", code=None, consent=True, name="Mem Ber"):
        c = C(self.app)
        body = {"name": name, "email": email, "password": "Passw0rdX"}
        if code:
            body.update(code=code, consent=consent)
        r = c.post("/api/auth/register", body)
        self.assertEqual(r.status_code, 201, r.get_json())
        return c

    def new_sub(self, months=1, name="Real Person", start=None):
        b = {"member_name": name, "plan": "Monthly", "price_inr": 1500, "months": months}
        if start:
            b["start_date"] = start
        r = self.admin.post("/api/admin/subscriptions", b)
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

    def active_member(self, email="m@test.com", months=2):
        s = self.new_sub(months)
        c = self.member(email, s["code"])
        return c, s

    def profile(self, c, h=170, w=70, age=30):
        r = c.patch("/api/me", {"height_cm": h, "weight_kg": w, "age": age})
        self.assertEqual(r.status_code, 200, r.get_json())


class TestAuth(Base):
    def test_register_validation_and_session(self):
        c = C(self.app)
        for body, field in [({"name": "A", "email": "a@b.co", "password": "Passw0rdX"}, "name"),
                            ({"name": "Alice", "email": "bad", "password": "Passw0rdX"}, "email"),
                            ({"name": "Alice", "email": "a@b.co", "password": "short1"}, "password"),
                            ({"name": "Alice", "email": "a@b.co", "password": "onlyletters"}, "password")]:
            r = c.post("/api/auth/register", body)
            self.assertEqual(r.status_code, 422, body)
            self.assertEqual(r.get_json()["error"]["field"], field)
        m = self.member("alice@test.com")
        self.assertEqual(m.get("/api/me").get_json()["user"]["email"], "alice@test.com")
        self.assertNotIn("pw_hash", m.get("/api/me").get_json()["user"])
        r = C(self.app).post("/api/auth/register", {"name": "Alice", "email": "alice@test.com", "password": "Passw0rdX"})
        self.assertEqual(r.status_code, 409)
        m.post("/api/auth/logout")
        self.assertEqual(m.get("/api/me").status_code, 401)

    def test_csrf_login_and_rate_limit(self):
        m = self.member("c@test.com")
        r = m.c.post("/api/activity/2026-06-14", json={"steps": 5})          # no CSRF header
        self.assertEqual(r.status_code, 403)
        c = C(self.app)
        for _ in range(5):
            self.assertEqual(c.post("/api/auth/login", {"email": "c@test.com", "password": "wrongpass1"}).status_code, 401)
        self.assertEqual(c.post("/api/auth/login", {"email": "c@test.com", "password": "Passw0rdX"}).status_code, 429)

    def test_permissions(self):
        m = self.member("p@test.com")
        self.assertEqual(C(self.app).get("/api/me").status_code, 401)
        for p in ("/api/admin/subscriptions", "/api/admin/members", "/api/admin/stats"):
            self.assertEqual(m.get(p).status_code, 403)
        self.assertEqual(m.post("/api/admin/subscriptions", {"member_name": "X Y", "plan": "P", "price_inr": 1, "months": 1}).status_code, 403)
        for p in ("/api/videos", "/api/chat/threads", "/api/posture/sessions", "/api/trainers"):
            r = m.get(p)
            self.assertEqual((r.status_code, r.get_json()["error"]["code"]), (403, "subscription_required"), p)
        self.assertEqual(m.get("/api/activity").status_code, 200)               # own tracking needs no subscription

    def test_profile_goals_export_delete(self):
        m = self.member("g@test.com")
        self.assertEqual(m.patch("/api/me", {"height_cm": 20}).status_code, 422)
        self.profile(m)
        self.assertEqual(m.patch("/api/me/goals", {"goal_type": "bogus", "step_goal": 8000, "calorie_goal": 2000, "water_goal_ml": 2000, "workouts_per_week": 3}).status_code, 422)
        r = m.patch("/api/me/goals", {"goal_type": "maintain", "step_goal": 8000, "calorie_goal": 2100, "water_goal_ml": 2500, "workouts_per_week": 4})
        self.assertEqual(r.get_json()["user"]["onboarded"], 1)
        self.assertEqual(r.get_json()["user"]["step_goal"], 8000)
        ex = m.get("/api/me/export").get_json()
        self.assertEqual(ex["profile"]["email"], "g@test.com")
        self.assertEqual(m.delete("/api/me", {"password": "wrongpass1"}).status_code, 403)
        self.assertEqual(m.delete("/api/me", {"password": "Passw0rdX"}).status_code, 200)
        self.assertEqual(C(self.app).post("/api/auth/login", {"email": "g@test.com", "password": "Passw0rdX"}).status_code, 401)


class TestMembership(Base):
    def test_code_linking_flow(self):
        s = self.new_sub()
        self.assertRegex(s["code"], r"^FIT-[A-Z0-9]{4}-[A-Z0-9]{4}$")
        c = C(self.app)
        r = c.post("/api/auth/register", {"name": "No Consent", "email": "nc@test.com", "password": "Passw0rdX", "code": s["code"]})
        self.assertEqual(r.get_json()["error"]["code"], "consent_required")
        m = self.member("link@test.com")                                       # register first, link later in Membership tab
        self.assertIsNone(m.get("/api/membership").get_json()["subscription"])
        self.assertEqual(m.post("/api/membership/link", {"code": s["code"]}).get_json()["error"]["code"], "consent_required")
        self.assertEqual(m.post("/api/membership/link", {"code": "FIT-NOPE-NOPE", "consent": True}).status_code, 404)
        r = m.post("/api/membership/link", {"code": s["code"].lower(), "consent": True})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["subscription"]["status"], "active")
        other = self.member("other@test.com")
        self.assertEqual(other.post("/api/membership/link", {"code": s["code"], "consent": True}).status_code, 404)   # single use
        self.assertEqual(m.post("/api/membership/link", {"code": s["code"], "consent": True}).status_code, 409)
        self.assertEqual(m.get("/api/videos").status_code, 200)
        m.post("/api/membership/leave")
        self.assertEqual(m.get("/api/videos").status_code, 403)
        new = [x for x in self.admin.get("/api/admin/subscriptions").get_json()["subscriptions"] if x["id"] == s["id"]][0]
        self.assertNotEqual(new["code"], s["code"])                            # code regenerated after unlink

    def test_wrong_code_rate_limit(self):
        m = self.member("rl@test.com")
        for _ in range(5):
            self.assertEqual(m.post("/api/membership/link", {"code": "FIT-AAAA-BBBB", "consent": True}).status_code, 404)
        self.assertEqual(m.post("/api/membership/link", {"code": "FIT-AAAA-BBBB", "consent": True}).status_code, 429)

    def test_status_reminders_renew_extend(self):
        s = self.new_sub(1, start="2026-05-20")                                # expires 2026-06-20 -> 5 days left
        m = self.member("exp@test.com", s["code"])
        sub = m.get("/api/membership").get_json()["subscription"]
        self.assertEqual((sub["status"], sub["days_left"]), ("expiring", 5))
        n1 = m.get("/api/notifications").get_json()
        n2 = m.get("/api/notifications").get_json()
        self.assertEqual(len(n1["notifications"]), 1)
        self.assertEqual(len(n2["notifications"]), 1)                          # no duplicate reminders
        self.assertIn("5 days", n1["notifications"][0]["message"])
        self.app.config["FAKE_TODAY"] = dt.date(2026, 6, 25)                   # now expired
        self.assertEqual(m.get("/api/membership").get_json()["subscription"]["status"], "expired")
        self.assertEqual(m.get("/api/videos").status_code, 403)
        self.assertTrue(any("expired" in x["message"] for x in m.get("/api/notifications").get_json()["notifications"]))
        adm_n = self.admin.get("/api/notifications").get_json()["notifications"]
        self.assertTrue(any("Real Person" in x["message"] for x in adm_n))     # trainer is told too
        r = self.admin.post(f"/api/admin/subscriptions/{s['id']}/renew", {"months": 1, "note": "paid cash"})
        self.assertEqual(r.get_json()["expiry_date"], "2026-07-25")            # renews from today because it had expired
        self.assertEqual(m.get("/api/videos").status_code, 200)
        r = self.admin.post(f"/api/admin/subscriptions/{s['id']}/extend", {"days": 10})
        self.assertEqual(r.get_json()["expiry_date"], "2026-08-04")
        h = self.admin.get(f"/api/admin/subscriptions/{s['id']}/history").get_json()["history"]
        self.assertEqual([x["kind"] for x in h], ["extend", "renew"])
        self.assertEqual(self.admin.post(f"/api/admin/subscriptions/{s['id']}/renew", {"months": 0}).status_code, 422)
        self.assertEqual(m.post(f"/api/admin/subscriptions/{s['id']}/renew", {"months": 1}).status_code, 403)

    def test_demo_membership_is_labelled_and_excluded(self):
        subs = self.admin.get("/api/admin/subscriptions").get_json()["subscriptions"]
        demo = [x for x in subs if x["is_demo"]]
        self.assertEqual(len(demo), 1)
        self.assertIn("DEMONSTRATION", demo[0]["label"])
        self.assertEqual(demo[0]["status"], "expiring")
        self.assertEqual(self.admin.get("/api/admin/stats").get_json()["stats"]["total"], 0)   # demo excluded
        self.new_sub()
        self.assertEqual(self.admin.get("/api/admin/stats").get_json()["stats"]["total"], 1)
        m = self.member("demo@test.com", demo[0]["code"])
        self.assertTrue(m.get("/api/membership").get_json()["subscription"]["is_demo"])
        seedmod.seed(self.app)                                                  # seeding twice keeps ONE demo
        self.assertEqual(len([x for x in self.admin.get("/api/admin/subscriptions").get_json()["subscriptions"] if x["is_demo"]]), 1)

    def test_renewal_request_notifies_admin(self):
        c, s = self.active_member()
        self.assertEqual(c.post("/api/membership/renewal-request").status_code, 200)
        self.assertTrue(any("renew" in x["message"] for x in self.admin.get("/api/notifications").get_json()["notifications"]))


class TestTracking(Base):
    def test_activity_estimates_and_validation(self):
        m = self.member("a@test.com")
        r = m.put("/api/activity/2026-06-14", {"steps": 10000})
        self.assertIsNone(r.get_json()["calories_kcal"])                       # no height/weight yet -> nothing invented
        self.profile(m)
        r = m.put("/api/activity/2026-06-14", {"steps": 10000}).get_json()
        self.assertEqual((r["distance_km"], r["active_minutes"], r["calories_kcal"]), (7.05, 88, 257))
        self.assertTrue(r["estimated"])
        self.assertEqual(r["active_minutes_source"], "estimated")
        r = m.put("/api/activity/2026-06-14", {"steps": 8000, "active_minutes": 60}).get_json()
        self.assertEqual((r["active_minutes"], r["active_minutes_source"]), (60, "entered"))
        self.assertEqual(m.put("/api/activity/2026-06-16", {"steps": 100}).status_code, 422)     # future
        self.assertEqual(m.put("/api/activity/2026-06-14", {"steps": -5}).status_code, 422)
        self.assertEqual(m.put("/api/activity/2026-06-14", {"steps": "abc"}).status_code, 422)
        self.assertEqual(m.put("/api/activity/not-a-date", {"steps": 5}).status_code, 422)
        days = m.get("/api/activity").get_json()["days"]
        self.assertEqual(len(days), 1)

    def test_measurements_bmi(self):
        m = self.member("b@test.com")
        self.profile(m, 170, 70, 30)
        r = m.put("/api/measurements/2026-06-15", {"weight_kg": 80, "waist_cm": 90}).get_json()
        self.assertEqual(r["bmi"]["category"], "Overweight range")             # 80/1.7^2 = 27.7
        self.assertIn("worth", r["bmi"]["guidance"])
        self.assertEqual(m.get("/api/me").get_json()["user"]["weight_kg"], 80)   # shared: profile weight updated
        self.assertEqual(m.put("/api/measurements/2026-06-15", {}).status_code, 422)
        self.assertEqual(m.put("/api/measurements/2026-06-15", {"waist_cm": 5}).status_code, 422)
        self.profile(m, 170, 80, 16)
        self.assertFalse(m.get("/api/measurements").get_json()["bmi"]["applicable"])   # under 18: no adult category
        self.profile(m, 170, 55, 30)
        self.assertEqual(m.put("/api/measurements/2026-06-14", {"weight_kg": 55}).get_json()["bmi"]["category"], "Healthy range")
        self.assertEqual(len(m.get("/api/measurements").get_json()["measurements"]), 2)
        m.delete("/api/measurements/2026-06-14")
        self.assertEqual(len(m.get("/api/measurements").get_json()["measurements"]), 1)

    def test_workouts_routines_prs_and_isolation(self):
        a, b = self.member("w1@test.com"), self.member("w2@test.com")
        r = a.post("/api/routines", {"name": "Push day", "items": [{"exercise": "Bench press", "sets": 3, "reps": 8, "weight_kg": 40}]})
        rid = r.get_json()["id"]
        self.assertEqual(a.post("/api/routines", {"name": "Empty", "items": []}).status_code, 422)
        w = a.post("/api/workouts", {"date": "2026-06-14", "routine_id": rid, "duration_min": 45,
                                     "sets": [{"exercise": "Bench press", "reps": 8, "weight_kg": 40}, {"exercise": "Bench press", "reps": 6, "weight_kg": 45}]})
        wid = w.get_json()["id"]
        h = a.get("/api/workouts").get_json()["workouts"]
        self.assertEqual([s["set_no"] for s in h[0]["sets"]], [1, 2])
        self.assertEqual(a.get("/api/workouts/prs").get_json()["records"][0]["best_weight_kg"], 45)
        self.assertEqual(a.post("/api/workouts", {"sets": []}).status_code, 422)
        self.assertEqual(a.post("/api/workouts", {"sets": [{"exercise": "Squat", "reps": 0}]}).status_code, 422)
        self.assertEqual(a.post("/api/workouts", {"routine_id": 9999, "sets": [{"exercise": "Squat", "reps": 5}]}).status_code, 404)
        b.delete(f"/api/workouts/{wid}")                                       # someone else's -> silently no effect
        self.assertEqual(len(a.get("/api/workouts").get_json()["workouts"]), 1)
        self.assertEqual(b.get("/api/workouts").get_json()["workouts"], [])
        a.delete(f"/api/workouts/{wid}")
        self.assertEqual(a.get("/api/workouts").get_json()["workouts"], [])


class TestDiet(Base):
    def test_food_log_water_totals(self):
        m = self.member("d@test.com")
        idli = m.get("/api/foods?q=idli").get_json()["foods"][0]
        self.assertEqual(m.post("/api/food-log", {"meal": "Breakfast", "items": [{"food_id": idli["id"], "grams": 100}]}).status_code, 201)
        self.assertEqual(m.post("/api/food-log", {"meal": "Lunch", "items": [{"name": "Home dal", "grams": 150, "kcal": 180, "protein": 10, "carbs": 25, "fat": 4}]}).status_code, 201)
        self.assertEqual(m.post("/api/food-log", {"meal": "Brunch", "items": [{"food_id": idli["id"], "grams": 100}]}).status_code, 422)
        self.assertEqual(m.post("/api/food-log", {"meal": "Lunch", "items": [{"name": "X", "grams": 0, "kcal": 1, "protein": 0, "carbs": 0, "fat": 0}]}).status_code, 422)
        m.post("/api/water", {"ml": 250})
        m.post("/api/water", {"ml": 500})
        self.assertEqual(m.post("/api/water", {"ml": 99999}).status_code, 422)
        d = m.get("/api/food-log").get_json()
        self.assertEqual(d["totals"]["kcal"], 325.0)
        self.assertEqual(d["water_ml"], 750)
        m.delete(f"/api/food-log/{d['entries'][0]['id']}")
        self.assertEqual(m.get("/api/food-log").get_json()["totals"]["kcal"], 180.0)

    def test_photo_analysis(self):
        c, _ = self.active_member("ph@test.com")
        ai_json = json.dumps([{"name": "Idli", "confidence": "high", "grams": 120}, {"name": "Mystery stew", "confidence": "low", "grams": 200, "kcal_per_100g": 100, "protein_per_100g": 5, "carbs_per_100g": 10, "fat_per_100g": 3}])
        with mock.patch("gym.ai.call_gemini", return_value="Here you go: " + ai_json) as m:
            r = c.post("/api/diet/analyze-photo", data={"image": (io.BytesIO(JPG), "meal.jpg")}, content_type="multipart/form-data")
            self.assertEqual(r.status_code, 200, r.get_json())
            j = r.get_json()
            self.assertEqual(j["items"][0]["kcal"], 174)                        # 145 kcal/100g x 120 g from the food table
            self.assertEqual(j["items"][0]["source"], "database")
            self.assertEqual((j["items"][1]["source"], j["items"][1]["kcal"]), ("ai_estimate", 200))
            self.assertLess(j["items"][0]["kcal_low"], 174 < j["items"][0]["kcal_high"] and 175)
            self.assertIn("estimate", j["disclaimer"].lower())
            self.assertEqual(m.call_count, 1)
        r = c.post("/api/diet/analyze-photo", data={"image": (io.BytesIO(b"not an image"), "x.jpg")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 422)
        self.assertEqual(c.post("/api/diet/analyze-photo").status_code, 422)
        with mock.patch("gym.ai.call_gemini", return_value="no json here"):
            r = c.post("/api/diet/analyze-photo", data={"image": (io.BytesIO(JPG), "m.jpg")}, content_type="multipart/form-data")
            self.assertEqual(r.status_code, 502)
        self.app.config["GEMINI_API_KEY"] = ""
        r = c.post("/api/diet/analyze-photo", data={"image": (io.BytesIO(JPG), "m.jpg")}, content_type="multipart/form-data")
        self.assertEqual((r.status_code, r.get_json()["error"]["code"]), (503, "ai_unavailable"))
        nosub = self.member("nosub@test.com")
        self.assertEqual(nosub.post("/api/diet/analyze-photo", data={"image": (io.BytesIO(JPG), "m.jpg")}, content_type="multipart/form-data").status_code, 403)


class TestVideos(Base):
    def upload(self, c, data=MP4, name="squat.mp4", **extra):
        form = {"title": "Squat", "category": "Legs", "trainer_name": "Coach", "instructions": "1. Stand\n2. Squat", "file": (io.BytesIO(data), name)}
        form.update(extra)
        return c.post("/api/videos", data=form, content_type="multipart/form-data")

    def test_admin_upload_member_watch_only(self):
        mem, _ = self.active_member("v@test.com")
        self.assertEqual(self.upload(mem).status_code, 403)                     # member cannot upload
        self.assertEqual(self.upload(self.admin, b"hello world not video").status_code, 422)
        self.assertEqual(self.upload(self.admin, MP4, "clip.mov").status_code, 422)
        self.assertEqual(self.upload(self.admin, title="x").status_code, 422)  # title too short
        r = self.upload(self.admin, thumb=(io.BytesIO(JPG), "t.jpg"))
        self.assertEqual(r.status_code, 201, r.get_json())
        vid = r.get_json()["id"]
        lst = mem.get("/api/videos").get_json()["videos"]
        self.assertEqual((lst[0]["title"], lst[0]["trainer_name"], lst[0]["has_thumb"]), ("Squat", "Coach", True))
        self.assertNotIn("file", lst[0])
        full = mem.get(f"/api/videos/{vid}/file")
        self.assertEqual((full.status_code, full.mimetype, len(full.data)), (200, "video/mp4", len(MP4)))
        part = mem.get(f"/api/videos/{vid}/file", headers={"Range": "bytes=0-9"})
        self.assertEqual((part.status_code, len(part.data)), (206, 10))        # seeking works
        self.assertEqual(mem.get(f"/api/videos/{vid}/thumb").status_code, 200)
        self.assertEqual(mem.put(f"/api/videos/{vid}", data={"title": "Hack", "category": "x1", "trainer_name": "me"}, content_type="multipart/form-data").status_code, 403)
        self.assertEqual(mem.delete(f"/api/videos/{vid}").status_code, 403)
        nosub = self.member("n@test.com")
        self.assertEqual(nosub.get(f"/api/videos/{vid}/file").status_code, 403)
        webm = b"\x1a\x45\xdf\xa3" + b"\x00" * 50
        r = self.admin.put(f"/api/videos/{vid}", data={"title": "Squat v2", "category": "Legs", "trainer_name": "Coach", "file": (io.BytesIO(webm), "n.webm")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(mem.get("/api/videos").get_json()["videos"][0]["mime"], "video/webm")
        vdir = os.path.join(self.app.config["UPLOAD_DIR"], "videos")
        before = len(os.listdir(vdir))
        self.assertEqual(self.admin.delete(f"/api/videos/{vid}").status_code, 200)
        self.assertLess(len(os.listdir(vdir)), before)                          # files removed from disk
        self.assertEqual(mem.get("/api/videos").get_json()["videos"], [])


class TestPosture(Base):
    def post(self, c, ex="squat", data=JPG):
        return c.post("/api/posture/analyze", data={"exercise": ex, "image": (io.BytesIO(data), "p.jpg")}, content_type="multipart/form-data")

    def test_rules_unit(self):
        r = analyze("squat", squat_lms(0.7), 1000, 1000)
        self.assertEqual((r["status"], r["metrics"]["knee_angle"]), ("ok", 90))
        self.assertEqual(r["issues"][0]["severity"], "ok")
        self.assertEqual(r["corrections"], [])
        stand = squat_lms(0.5); stand[25] = [0.5, 0.68, 0.95]; stand[27] = [0.5, 0.8, 0.95]
        r = analyze("squat", stand, 1000, 1000)                                 # straight leg -> standing, no depth judgement
        self.assertTrue(any("top of a rep" in o for o in r["observations"]))
        lean = squat_lms(0.7); lean[11] = [0.9, 0.3, 0.95]                      # shoulder far forward of hip
        r = analyze("squat", lean, 1000, 1000)
        self.assertTrue(any(i["title"] == "Torso leaning forward" for i in r["issues"]))
        self.assertTrue(r["corrections"])
        # shallow squat: knee ~ 140deg
        sh = squat_lms(0.7); sh[25] = [0.62, 0.62, 0.95]; sh[27] = [0.6, 0.85, 0.95]
        r = analyze("squat", sh, 1000, 1000)
        self.assertTrue(any("hallow" in i["title"] or "Moderate" in i["title"] for i in r["issues"]), r["issues"])
        # plank with sagging hips (side view, body left->right): shoulder, hip, ankle
        pl = lms(i11=(0.2, 0.5, .95), i13=(0.2, 0.7, .95), i23=(0.5, 0.72, .95), i27=(0.8, 0.65, .95), i12=(0.2, 0.5, .1), i14=(0.2, 0.7, .1), i24=(0.5, 0.5, .1), i28=(0.8, 0.5, .1))
        r = analyze("plank", pl, 1000, 1000)
        self.assertEqual(r["status"], "ok")
        self.assertTrue(any("sagging" in i["title"] for i in r["issues"]), r["issues"])
        pu = lms(i11=(0.2, 0.5, .95), i13=(0.25, 0.7, .95), i15=(0.3, 0.9, .95), i23=(0.5, 0.52, .95), i27=(0.8, 0.54, .95), i12=(0.2, 0.5, .1), i14=(.2, .5, .1), i16=(.2, .5, .1), i24=(.5, .5, .1), i28=(.8, .5, .1))
        r = analyze("pushup", pu, 1000, 1000)
        self.assertEqual(r["status"], "ok")
        self.assertIn("elbow_angle", r["metrics"])
        self.assertTrue(any("straight" in i["title"] for i in r["issues"]))

    def test_visibility_and_confidence_gates(self):
        r = analyze("squat", squat_lms(ankle_vis=0.2), 1000, 1000)
        self.assertEqual((r["status"], r["missing_joints"], r["corrections"], r["issues"]), ("insufficient_visibility", ["ankle"], [], []))
        r = analyze("squat", squat_lms(vis=0.65), 1000, 1000)                   # visible but below 0.7 confidence
        self.assertEqual((r["status"], r["corrections"]), ("low_confidence", []))
        r = analyze("squat", None, 1000, 1000)
        self.assertEqual(r["status"], "insufficient_visibility")
        self.assertIn("not a professional", analyze("squat", squat_lms(), 1000, 1000)["disclaimer"].lower().replace("this is ", ""))

    def test_endpoint(self):
        c, _ = self.active_member("po@test.com")
        with mock.patch("gym.pose.detect", return_value=(squat_lms(0.7), 1000, 1000)):
            r = self.post(c)
            self.assertEqual(r.status_code, 200, r.get_json())
            self.assertEqual(r.get_json()["status"], "ok")
            self.assertTrue(r.get_json()["overlay"]["points"])
        with mock.patch("gym.pose.detect", return_value=(squat_lms(ankle_vis=0.1), 1000, 1000)):
            self.assertEqual(self.post(c).get_json()["status"], "insufficient_visibility")
        with mock.patch("gym.pose.detect", return_value=(None, 640, 480)):
            self.assertEqual(self.post(c).get_json()["status"], "insufficient_visibility")
        self.assertEqual(self.post(c, "yoga").status_code, 422)
        self.assertEqual(self.post(c, data=b"%PDF-1.4 fake").status_code, 422)
        s = c.get("/api/posture/sessions").get_json()["sessions"]
        self.assertEqual(len(s), 3)
        self.assertNotIn("overlay", s[0]["result"])
        c.delete(f"/api/posture/sessions/{s[0]['id']}")
        self.assertEqual(len(c.get("/api/posture/sessions").get_json()["sessions"]), 2)
        c.delete("/api/posture/sessions")
        self.assertEqual(c.get("/api/posture/sessions").get_json()["sessions"], [])
        nosub = self.member("np@test.com")
        self.assertEqual(self.post(nosub).status_code, 403)
        r = self.post(c)                                                        # real engine, model file missing -> clear error
        self.assertEqual((r.status_code, r.get_json()["error"]["code"]), (503, "pose_model_missing"))


class TestCoach(Base):
    def test_chat_context_history_privacy(self):
        c, _ = self.active_member("ch@test.com")
        self.profile(c)
        c.put("/api/activity/2026-06-14", {"steps": 4321})
        t = c.post("/api/chat/threads").get_json()["id"]
        seen = {}

        def fake(system, messages, max_tokens=900):
            seen["system"], seen["messages"] = system, messages
            return "Try adding a short walk after dinner."
        with mock.patch("gym.ai.call_gemini", side_effect=fake):
            r = c.post(f"/api/chat/threads/{t}/messages", {"content": "How can I walk more?"})
            self.assertEqual(r.status_code, 200, r.get_json())
            self.assertIn("4321", seen["system"])                              # personal data reaches the AI as context
            self.assertIn("not a doctor", seen["system"])
            self.assertIn("14416", seen["system"])
            r = c.post(f"/api/chat/threads/{t}/messages", {"content": "And what about protein?"})
            self.assertEqual(len(seen["messages"]), 3)                          # history is replayed: user, assistant, user
        msgs = c.get(f"/api/chat/threads/{t}").get_json()
        self.assertEqual([m["role"] for m in msgs["messages"]], ["user", "assistant", "user", "assistant"])
        self.assertEqual(c.get("/api/chat/threads").get_json()["threads"][0]["title"], "How can I walk more?")
        self.assertEqual(c.post(f"/api/chat/threads/{t}/messages", {"content": "x" * 2001}).status_code, 422)
        self.assertEqual(c.post(f"/api/chat/threads/{t}/messages", {"content": "  "}).status_code, 422)
        other, _ = self.active_member("ch2@test.com")
        self.assertEqual(other.get(f"/api/chat/threads/{t}").status_code, 404)  # private to the owner
        self.assertEqual(other.post(f"/api/chat/threads/{t}/messages", {"content": "hi"}).status_code, 404)
        from gym.util import ApiError
        with mock.patch("gym.ai.call_gemini", side_effect=ApiError(502, "ai_error", "down")):
            t2 = c.post("/api/chat/threads").get_json()["id"]
            self.assertEqual(c.post(f"/api/chat/threads/{t2}/messages", {"content": "hello"}).status_code, 502)
            self.assertEqual(c.get(f"/api/chat/threads/{t2}").get_json()["messages"], [])   # nothing half-saved
        c.delete(f"/api/chat/threads/{t}")
        self.assertEqual(c.get(f"/api/chat/threads/{t}").status_code, 404)

    def test_trainers_and_bookings(self):
        c, _ = self.active_member("tb@test.com")
        self.assertEqual(c.post("/api/admin/trainers", {"name": "Hacker"}).status_code, 403)
        tid = self.admin.post("/api/admin/trainers", {"name": "Ravi Kumar", "area": "Indiranagar", "city": "Bengaluru", "fee_inr": 800}).get_json()["id"]
        self.assertEqual(self.admin.post("/api/admin/trainers", {"name": "R"}).status_code, 422)
        self.assertEqual(c.get("/api/trainers?q=indira").get_json()["trainers"][0]["name"], "Ravi Kumar")
        self.assertEqual(c.get("/api/trainers?q=zzz").get_json()["trainers"], [])
        self.assertEqual(c.post("/api/bookings", {"trainer_id": tid, "date": "2026-06-10", "time": "18:00"}).status_code, 422)   # past
        self.assertEqual(c.post("/api/bookings", {"trainer_id": tid, "date": "2026-06-20", "time": "25:99"}).status_code, 422)
        self.assertEqual(c.post("/api/bookings", {"trainer_id": 999, "date": "2026-06-20", "time": "18:00"}).status_code, 404)
        r = c.post("/api/bookings", {"trainer_id": tid, "date": "2026-06-20", "time": "18:30", "note": "Knee-friendly"})
        self.assertEqual((r.status_code, r.get_json()["payment_status"]), (201, "demo_not_charged"))
        self.assertIn("no money", r.get_json()["message"])
        bid = r.get_json()["id"]
        self.assertEqual(self.admin.get("/api/bookings").get_json()["bookings"][0]["member_name"], "Mem Ber")
        self.assertEqual(c.patch(f"/api/admin/bookings/{bid}", {"status": "confirmed"}).status_code, 403)
        self.assertEqual(self.admin.patch(f"/api/admin/bookings/{bid}", {"status": "confirmed"}).status_code, 200)
        self.assertEqual(self.admin.patch(f"/api/admin/bookings/{bid}", {"status": "weird"}).status_code, 422)
        self.assertEqual(c.get("/api/dashboard").get_json()["next_booking"]["trainer_name"], "Ravi Kumar")
        other, _ = self.active_member("tb2@test.com")
        self.assertEqual(other.post(f"/api/bookings/{bid}/cancel").status_code, 404)
        self.assertEqual(c.post(f"/api/bookings/{bid}/cancel").status_code, 200)


class TestWellnessAdmin(Base):
    def test_wellness_support_block(self):
        m = self.member("wl@test.com")
        r = m.post("/api/wellness/checkins", {"mood": 1, "stress": 5, "note": "rough day"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["support"]["tele_manas"], "14416")
        self.assertIsNone(m.post("/api/wellness/checkins", {"mood": 4, "stress": 2}).get_json()["support"])
        self.assertEqual(len(m.get("/api/wellness/checkins").get_json()["checkins"]), 1)      # one per day (updated)
        self.assertEqual(m.post("/api/wellness/checkins", {"mood": 7, "stress": 2}).status_code, 422)
        self.assertTrue(m.get("/api/wellness/resources").get_json()["resources"])
        self.assertEqual(C(self.app).get("/api/wellness/resources").status_code, 401)

    def test_trainer_sees_only_consenting_linked_members(self):
        c, s = self.active_member("tm@test.com")
        self.profile(c)
        c.put("/api/activity/2026-06-15", {"steps": 6000})
        c.post("/api/wellness/checkins", {"mood": 2, "stress": 4})
        solo = self.member("solo@test.com")                                     # not linked -> invisible to the trainer
        solo.put("/api/activity/2026-06-15", {"steps": 999})
        mem = self.admin.get("/api/admin/members").get_json()["members"]
        self.assertEqual([m["email"] for m in mem], ["tm@test.com"])
        self.assertEqual(mem[0]["today"]["activity"]["steps"], 6000)
        self.assertEqual(mem[0]["subscription"]["status"], "active")
        self.assertNotIn("checkin", json.dumps(mem).lower())                    # wellness stays private
        uid = mem[0]["id"]
        self.assertEqual(self.admin.put(f"/api/admin/members/{uid}/note", {"note": "Working on squats"}).status_code, 200)
        self.assertEqual(self.admin.get("/api/admin/members").get_json()["members"][0]["note"], "Working on squats")
        self.admin.post(f"/api/admin/subscriptions/{s['id']}/unlink")
        self.assertEqual(self.admin.get("/api/admin/members").get_json()["members"], [])      # access stops on unlink


class TestWorkflow(Base):
    def test_full_member_journey(self):
        # Register (with subscription code) -> goals -> dashboard -> plan -> videos -> log -> posture -> diet -> progress -> AI -> expert
        s = self.new_sub(3)
        tid = self.admin.post("/api/admin/trainers", {"name": "Asha", "area": "Koramangala", "city": "Bengaluru", "fee_inr": 700}).get_json()["id"]
        self.admin.post("/api/videos", data={"title": "Squat form", "category": "Legs", "trainer_name": "Coach", "file": (io.BytesIO(MP4), "s.mp4")}, content_type="multipart/form-data")
        m = self.member("journey@test.com", s["code"], name="Journey Member")
        self.assertFalse(m.get("/api/me").get_json()["user"]["onboarded"])
        self.profile(m, 172, 78, 32)
        m.patch("/api/me/goals", {"goal_type": "lose_weight", "step_goal": 8000, "calorie_goal": 1900, "water_goal_ml": 2500, "workouts_per_week": 3, "target_weight_kg": 72})
        d = m.get("/api/dashboard").get_json()
        self.assertEqual(d["summary"]["goals"]["step_goal"], 8000)
        self.assertEqual(d["subscription"]["status"], "active")
        rid = m.post("/api/routines", {"name": "Legs", "items": [{"exercise": "Squat", "sets": 3, "reps": 10}]}).get_json()["id"]
        self.assertEqual(len(m.get("/api/videos").get_json()["videos"]), 1)
        m.post("/api/workouts", {"routine_id": rid, "sets": [{"exercise": "Squat", "reps": 10, "weight_kg": 30}] * 3})
        with mock.patch("gym.pose.detect", return_value=(squat_lms(0.7), 1000, 1000)):
            self.assertEqual(m.post("/api/posture/analyze", data={"exercise": "squat", "image": (io.BytesIO(JPG), "p.jpg")}, content_type="multipart/form-data").get_json()["status"], "ok")
        with mock.patch("gym.ai.call_gemini", return_value='[{"name":"Banana","confidence":"high","grams":118}]'):
            items = m.post("/api/diet/analyze-photo", data={"image": (io.BytesIO(JPG), "f.jpg")}, content_type="multipart/form-data").get_json()["items"]
        m.post("/api/food-log", {"meal": "Snack", "items": [{"food_id": items[0]["food_id"], "grams": items[0]["grams"]}]})
        m.post("/api/water", {"ml": 500})
        m.put("/api/activity/2026-06-15", {"steps": 9000})
        m.put("/api/measurements/2026-06-15", {"weight_kg": 77.5, "waist_cm": 88})
        m.post("/api/wellness/checkins", {"mood": 4, "stress": 2})
        d = m.get("/api/dashboard").get_json()["summary"]
        self.assertEqual(d["activity"]["steps"], 9000)
        self.assertEqual(d["food"]["k"], 105.0)                                  # banana 89 kcal/100g x 118 g
        self.assertEqual((d["water_ml"], d["workouts_last_7_days"], d["posture_sessions"]), (500, 1, 1))
        self.assertEqual(d["latest_measurement"]["weight_kg"], 77.5)
        self.assertEqual(d["bmi"]["category"], "Overweight range")
        with mock.patch("gym.ai.call_gemini", return_value="Great progress!") as ai:
            t = m.post("/api/chat/threads").get_json()["id"]
            m.post(f"/api/chat/threads/{t}/messages", {"content": "Review my week"})
            system = ai.call_args[0][0]
            for needle in ("9000", "Squat", "77.5", "lose_weight", "500 ml"):
                self.assertIn(needle, system)                                    # every feature feeds the AI's context
        m.post("/api/bookings", {"trainer_id": tid, "date": "2026-06-18", "time": "07:00"})
        adm = self.admin.get("/api/admin/members").get_json()["members"][0]
        self.assertEqual((adm["name"], adm["today"]["activity"]["steps"], adm["today"]["posture_sessions"]), ("Journey Member", 9000, 1))
        self.assertEqual(self.admin.get("/api/bookings").get_json()["bookings"][0]["member_name"], "Journey Member")


if __name__ == "__main__":
    unittest.main(verbosity=1)

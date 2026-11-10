# Fit Connect System (Gym Management Platform)

Flask + SQLite backend, vanilla-JS frontend (your pastel UI), Claude-powered AI (food photos and coach chat) and MediaPipe posture analysis.

## Run it in VS Code
1. Install Python 3.10-3.12 and VS Code (Python extension).
2. Open this folder in VS Code, open a terminal:
   ```
   python -m venv .venv
   .venv\Scripts\activate          # Windows      (Mac/Linux: source .venv/bin/activate)
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill it in:
   - `SECRET_KEY` - a long random string
   - `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_NAME` - **your trainer/admin login**
   - `GEMINI_API_KEY` - create at https://console.anthropic.com (billed to you; used for food-photo analysis and the AI coach)
4. Download the pose model once into `models/` (Mac/Linux: curl; Windows PowerShell: Invoke-WebRequest):
   ```
   curl -L -o models/pose_landmarker_full.task https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task
   ```
5. Check MediaPipe works on a full-body photo of yourself: `python scripts/check_pose.py my_photo.jpg`
6. Create your admin account and the ONE demo membership: `python seed.py`
7. Start: `flask --app gym run --debug` then open http://127.0.0.1:5000
8. Run the tests: `python -m unittest discover -s tests`

`GET /api/health` tells you whether the AI key and pose model are found.

## How people use it
- **You (admin/trainer)** sign in with the seeded account. In **Admin** create a subscription (member name, plan, price, months) - you get a one-time code like `FIT-7K2Q-9M4D`. Give it to the member. Add nearby trainers, renew/extend/unlink subscriptions, see linked members' progress and keep private notes. In **Videos** you add, edit, replace and delete videos (MP4/WebM).
- **Members** register with email + password, set goals, then enter the code in **Membership** (or at sign-up) and tick consent. That links them to the subscription and to you. Members can only *watch* videos.
- Without an active subscription a member can still use their own tracking (activity, diet, workouts, measurements), wellness and Tele-MANAS. Videos, posture analysis, the AI coach, AI food photos and trainer booking need an active subscription.
- Wellness check-ins and AI chats are private (the trainer cannot see them).
- The demo membership (`FIT-DEMO-2026`) is labelled DEMO everywhere and excluded from real statistics.

## Deploy
- Any host that runs Docker (Render, Railway, Fly.io): the included `Dockerfile` installs everything, downloads the pose model and starts gunicorn.
- Set environment variables on the host: `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_NAME`, `GEMINI_API_KEY`, `COOKIE_SECURE=1`.
- **Attach a persistent disk mounted at `/app/instance`** - the SQLite database and uploaded videos live there. Without it, data is lost on every deploy.
- SQLite and the in-memory rate limiter assume ONE server process. For several servers, move to PostgreSQL and Redis.
- Serve over HTTPS (all hosts above do this for you).

## Notes and limits
- Steps and active minutes are entered by hand. Distance, calories and BMI are **estimates** (formulas are in `gym/calc.py`).
- Posture analysis is rule-based on MediaPipe landmarks (`gym/posture_rules.py`). It never guesses hidden joints, withholds advice when confidence is low, and is not a professional assessment. Photos are processed in memory and not stored. JPG/PNG only (no PDF).
- Food database (`gym/foods.py`) holds ~60 approximate typical values. Swap in USDA FoodData Central or IFCT for higher accuracy.
- Payments are a demonstration only - nothing is charged. Reminders are in-app (7, 3, 1 days before expiry and after expiry); no email/SMS yet.
- Members can export or delete all their data from Membership.

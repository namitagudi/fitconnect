"""Dev/E2E server with the AI + pose model replaced by fakes, so the UI can be tested offline."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
d = tempfile.mkdtemp()
os.environ.update(ADMIN_EMAIL="trainer@test.com", ADMIN_PASSWORD="TrainerPass1", ADMIN_NAME="Coach Asha")
import gym.ai, gym.pose
from gym import create_app
import seed

def fake_claude(system, messages, max_tokens=900):
    last = messages[-1]["content"]
    if isinstance(last, list):
        return '[{"name":"Idli","confidence":"high","grams":120},{"name":"Coconut chutney","confidence":"low","grams":40,"kcal_per_100g":150,"protein_per_100g":3,"carbs_per_100g":10,"fat_per_100g":10}]'
    return "Mock coach: a 10-minute walk after meals is a gentle way to add steps."

def lms():
    L = [[0.5, 0.5, 0.95] for _ in range(33)]
    L[11], L[23], L[25], L[27] = [0.5, 0.3, .95], [0.5, 0.55, .95], [0.7, 0.55, .95], [0.7, 0.8, .95]
    for i in (12, 24, 26, 28): L[i] = [0.5, 0.5, 0.1]
    return L

gym.ai.call_gemini = fake_claude
gym.pose.detect = lambda b, p: (lms(), 800, 600)
app = create_app({"DATABASE": os.path.join(d, "e2e.sqlite"), "UPLOAD_DIR": os.path.join(d, "up")})
seed.seed(app)
app.run(port=5057)

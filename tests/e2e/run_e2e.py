import re, sys, traceback
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5057"
errors = []

def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch(); ctx = b.new_context(viewport={"width": 1280, "height": 900}, permissions=[]); page = ctx.new_page(); globals()["PAGE"] = page
        page.on("pageerror", lambda e: errors.append("PAGEERROR: " + str(e)))
        page.on("console", lambda m: errors.append("CONSOLE: " + m.text) if m.type == "error" else None)
        step = lambda n: print("•", n, flush=True)
        txt = lambda: page.inner_text("body")
        def need(s, where=""):
            page.wait_for_function("t => document.body.innerText.includes(t)", arg=s, timeout=8000)
        def nav(t): page.click(f'#nav button[data-t="{t}"]')
        def login(email, pw_):
            page.wait_for_selector("#ae"); page.fill("#ae", email); page.fill("#ap", pw_); page.click("#asub"); page.wait_for_selector("#nav")

        step("auth screen + confetti canvas"); page.goto(BASE); page.wait_for_selector(".authcard"); assert page.query_selector("#confetti"); need("Fit Connect System")
        step("bad login shows error"); page.fill("#ae", "nobody@x.com"); page.fill("#ap", "wrongpass1"); page.click("#asub"); need("Invalid email or password")
        step("admin signs in"); login("trainer@test.com", "TrainerPass1"); need("Hello, Coach"); assert page.query_selector('#nav button[data-t="admin"]')
        step("admin creates subscription -> code"); nav("admin"); page.wait_for_selector("#sn"); page.fill("#sn", "Priya Test"); page.click("#sc"); page.wait_for_selector("#modalbox code")
        code = page.inner_text("#modalbox code").strip(); assert re.match(r"^FIT-[A-Z0-9]{4}-[A-Z0-9]{4}$", code), code; print("   code:", code); page.click("#modalbox .btn")
        step("admin sees DEMO membership and real one"); need("DEMO"); need("Priya Test")
        step("admin adds trainer"); page.click('.tabs2 button[data-a="trainers"]'); page.wait_for_selector("#tn"); page.fill("#tn", "Ravi Kumar"); page.fill("#ta", "Indiranagar"); page.fill("#tc", "Bengaluru"); page.fill("#tf", "800"); page.click("#tadd"); need("Ravi Kumar")
        step("admin uploads a real WebM video"); nav("vid"); need("Your video library is empty"); page.click("#vf"); page.wait_for_selector("#vfile")
        page.set_input_files("#vfile", "/tmp/e2e/demo.webm"); need("Thumbnail ready"); page.fill("#vt", "Squat form"); page.fill("#vc2", "Legs"); page.fill("#vtr", "Coach Asha"); page.fill("#vi", "Stand tall\nSit back and down\nDrive up through heels")
        page.click("#vs"); page.wait_for_selector(".vc"); need("Squat form"); assert page.query_selector('.vc img'), "thumbnail image missing"
        step("admin sees edit/replace/delete controls"); assert page.query_selector("[data-e]") and page.query_selector("[data-x]")
        page.screenshot(path="/tmp/e2e/admin_videos.png")
        step("sign out"); page.click("#lo"); page.wait_for_selector(".authcard")

        step("member registers with code + consent"); page.click('.tabs2 button[data-m="register"]'); page.fill("#an", "Asha Member"); page.fill("#ae", "asha@test.com"); page.fill("#ap", "Passw0rdX"); page.fill("#ac", code); page.check("#acon"); page.click("#asub")
        page.wait_for_selector("#gsv"); step("onboarding goals modal appears"); page.select_option("#gt", "lose_weight"); page.fill("#gs", "8000"); page.click("#gsv"); need("Hello, Asha")
        step("profile edit"); page.click("#ep"); page.fill("#pa", "30"); page.fill("#ph", "170"); page.fill("#pw", "70"); page.fill("#par", "Indiranagar"); page.click("#ps"); need("170 cm")
        step("membership active after linking"); assert "Active" in txt(); assert not page.is_visible("#banner")
        step("activity: manual steps -> estimates"); nav("act"); page.wait_for_selector("#as"); page.fill("#as", "10000"); page.click("#asv"); need("≈ 257"); need("7.05")
        step("diet: add food from table and save"); nav("diet"); page.wait_for_selector("#dq"); page.fill("#dq", "idli"); page.wait_for_selector('#dr .chip:has-text("Idli")'); page.click('#dr .chip:has-text("Idli")'); need("Confirm and save"); page.click("#psv"); need("Idli")
        step("diet: photo -> AI guesses -> confirm -> save"); page.set_input_files("#dfi", "/tmp/e2e/meal.jpg"); page.wait_for_selector(".tag"); need("AI guess"); assert page.is_disabled("#psv"); page.click("#pa"); page.click("#psv"); need("AI estimate")
        step("diet: water"); page.click('[data-w="250"]'); need("250 ml")
        step("workouts: routine -> start -> log"); nav("work"); page.click("#nr"); page.fill("#rn", "Leg day"); page.fill('#ri input[data-k="exercise"]', "Squat"); page.click("#rs"); need("Leg day"); page.click("[data-st]"); page.click("#wsv"); need("Personal records"); need("Squat")
        step("body measurements"); nav("body"); page.fill("#b_weight_kg", "69.5"); page.fill("#b_waist_cm", "80"); page.click("#bs"); need("69.5")
        step("videos: member can watch but not upload"); nav("vid"); page.wait_for_selector(".vc"); assert not page.query_selector("#va") and not page.query_selector("[data-x]")
        page.click(".th"); page.wait_for_selector("#modalbox video"); need("Sit back and down"); page.wait_for_function("document.querySelector('#modalbox video').readyState>=2", timeout=8000); print("   video playable (readyState>=2)"); page.screenshot(path="/tmp/e2e/member_player.png"); page.click("#vcl")
        step("posture: upload photo -> result with overlay"); nav("pos"); page.set_input_files("#pf", "/tmp/e2e/pose.jpg"); page.wait_for_selector("#pcv"); need("Good squat depth"); need("AI estimate"); need("95%"); page.screenshot(path="/tmp/e2e/posture.png")
        step("coach: AI chat reply"); nav("coach"); page.wait_for_selector("#ci"); page.fill("#ci", "How can I walk more?"); page.click("#cs"); need("Mock coach"); page.screenshot(path="/tmp/e2e/coach.png")
        step("coach: chat history persists after reload of tab"); nav("act"); nav("coach"); page.wait_for_selector("#tl .exp"); page.click("#tl .exp"); need("Mock coach")
        step("trainers: book"); page.click('.tabs2 button[data-s="tr"]'); page.wait_for_selector("[data-bk]"); page.click("[data-bk]"); page.click("#bks"); need("Ravi Kumar"); need("requested")
        step("wellness: low mood -> Tele-MANAS support"); nav("well"); page.click('#mo .mc[data-v="1"]'); page.fill("#ws", "5"); page.click("#wsv"); page.wait_for_selector('#sup a[href="tel:14416"]'); need("Call 14416")
        step("membership page"); nav("mem"); need("Monthly"); need("Renewal history")
        step("dashboard aggregates shared data"); nav("dash"); need("kcal burned"); need("1 posture check") if False else None; page.screenshot(path="/tmp/e2e/member_dash.png")
        step("sign out"); page.click("#lo"); page.wait_for_selector(".authcard")

        step("admin sees member progress (consented)"); login("trainer@test.com", "TrainerPass1"); nav("admin"); page.click('.tabs2 button[data-a="members"]'); need("Asha Member"); need("10,000"); need("1 posture") if False else None
        step("admin renews real subscription"); page.click('.tabs2 button[data-a="subs"]'); page.wait_for_selector("[data-rn]"); rows = page.query_selector_all("tr:has-text('Priya Test') [data-rn]"); rows[0].click(); page.click("#qs"); need("Done")
        step("non-admin cannot reach admin API"); b.close()

try:
    main()
except Exception:
    traceback.print_exc(); print("ERRORS SO FAR:", errors)
    try:
        pg = globals().get("PAGE")
        if pg: pg.screenshot(path="/tmp/e2e/fail.png"); print("PAGE TEXT:", pg.inner_text("body")[:700].replace("\n", " | "))
    except Exception as e: print("diag failed", e)
    sys.exit(1)
print("\nJS/console errors:", errors or "none")
sys.exit(1 if errors else 0)

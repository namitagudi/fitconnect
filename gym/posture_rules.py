
"""Rule-based posture feedback from pose landmarks.
Thresholds are general coaching references, not validated clinical limits.
Output is an estimate only.
"""
import math

IDX = {
    "L": dict(shoulder=11, elbow=13, wrist=15, hip=23, knee=25, ankle=27),
    "R": dict(shoulder=12, elbow=14, wrist=16, hip=24, knee=26, ankle=28)
}

NEED = {
    "squat": ["shoulder", "hip", "knee", "ankle"],
    "lunge": ["shoulder", "hip", "knee", "ankle"],
    "pushup": ["shoulder", "elbow", "wrist", "hip", "ankle"],
    "plank": ["shoulder", "elbow", "hip", "ankle"]
}

VIS, CONF = 0.6, 0.7

DISCLAIMER = (
    "AI estimate from landmark detection - it can be wrong. "
    "This is not a professional assessment and cannot diagnose injuries or "
    "medical conditions. Stop if anything hurts and ask a qualified coach or doctor."
)

TIPS = {
    "squat": "Stand side-on, 2-3 m from the camera, whole body in frame, good light.",
    "lunge": "Stand side-on with your front leg nearest the camera and your whole body in frame.",
    "pushup": "Place the camera low and to the side so shoulders, elbows, wrists, hips and ankles are visible.",
    "plank": "Place the camera low and to the side with your whole body in frame."
}


def _ang(a, b, c):
    u = (a[0] - b[0], a[1] - b[1])
    v = (c[0] - b[0], c[1] - b[1])

    n = math.hypot(*u) * math.hypot(*v)

    return (
        math.degrees(
            math.acos(max(-1, min(1, (u[0] * v[0] + u[1] * v[1]) / n)))
        )
        if n else None
    )


def _fail(ex, status, conf, missing, msg):
    return {
        "exercise": ex,
        "status": status,
        "confidence": round(conf, 2),
        "missing_joints": missing,
        "message": msg,
        "issues": [],
        "corrections": [],
        "observations": [],
        "metrics": {},
        "overlay": {"points": [], "angles": []},
        "single_image": True,
        "disclaimer": DISCLAIMER
    }


def analyze(ex, lms, w, h):
    if ex not in NEED:
        raise ValueError("unknown exercise")

    if not lms:
        return _fail(
            ex,
            "insufficient_visibility",
            0,
            ["whole body"],
            "No person was detected. " + TIPS[ex]
        )

    need, best = NEED[ex], None

    for s in "LR":
        v = {
            j: float(lms[IDX[s][j]][2])
            for j in need
        }

        if best is None or min(v.values()) > min(best[1].values()):
            best = (s, v)

    s, v = best

    missing = [j for j in need if v[j] < VIS]

    if missing:
        return _fail(
            ex,
            "insufficient_visibility",
            sum(v.values()) / len(v),
            missing,
            "These body parts were not clearly visible: "
            + ", ".join(missing)
            + ". No feedback is given because I don't guess. "
            + TIPS[ex]
        )

    conf = sum(v.values()) / len(v)

    if conf < CONF:
        return _fail(
            ex,
            "low_confidence",
            conf,
            [],
            "Detection confidence is too low for reliable feedback. "
            "Try brighter light and a clearer side-on view. "
            + TIPS[ex]
        )

    P = {
        j: (
            lms[IDX[s][j]][0] * w,
            lms[IDX[s][j]][1] * h
        )
        for j in need
    }

    N = {
        j: (
            lms[IDX[s][j]][0],
            lms[IDX[s][j]][1]
        )
        for j in need
    }

    obs, iss, cor, met, angles = [], [], [], {}, []

    def add(ok, title, detail, fix=None):
        iss.append({
            "severity": "ok" if ok else "warn",
            "title": title,
            "detail": detail
        })

        if not ok and fix:
            cor.append(fix)

    if ex in ("squat", "lunge"):

        kn = _ang(P["hip"], P["knee"], P["ankle"])

        lean = math.degrees(
            math.atan2(
                abs(P["shoulder"][0] - P["hip"][0]),
                abs(P["hip"][1] - P["shoulder"][1]) or 1e-6
            )
        )

        met.update(
            knee_angle=round(kn),
            torso_lean=round(lean)
        )

        angles.append({
            "label": f"{round(kn)}° knee",
            "x": N["knee"][0],
            "y": N["knee"][1]
        })

        obs += [
            f"Knee angle ≈ {round(kn)}° (estimate)",
            f"Torso lean ≈ {round(lean)}° from vertical (estimate)"
        ]

        if ex == "squat":

            # NEW: Check hip height relative to knee height.
            # Image Y coordinates increase downwards.
            thigh_length = math.hypot(
                P["hip"][0] - P["knee"][0],
                P["hip"][1] - P["knee"][1]
            ) or 1

            hip_knee_level = (
                P["hip"][1] - P["knee"][1]
            ) / thigh_length

            met["hip_knee_level"] = round(hip_knee_level, 2)

            obs.append(
                "Hip position relative to knee level: "
                + (
                    "above knee level"
                    if hip_knee_level < -0.05
                    else "approximately at knee level or lower"
                )
            )

            if kn > 150:
                obs.append(
                    "This looks like standing or the top of a rep. "
                    "Squat depth cannot be judged from this position."
                )

            elif hip_knee_level < -0.05:
                add(
                    False,
                    "Squat depth looks insufficient",
                    "The hip is visibly above knee level. "
                    "A bent knee angle alone does not confirm sufficient squat depth.",
                    "If comfortable, sit your hips further down until they reach approximately knee level. "
                    "Keep your heels grounded."
                )

            elif kn > 130:
                add(
                    False,
                    "Shallow squat",
                    "The knee bend is limited.",
                    "Bend your hips and knees together as if sitting on a chair, "
                    "going only as deep as feels comfortable."
                )

            elif kn > 100:
                add(
                    False,
                    "Moderate squat depth",
                    "The knee bend is fairly shallow.",
                    "If comfortable, sit back and down a little further, "
                    "keeping your heels on the floor."
                )

            else:
                add(
                    True,
                    "Squat depth looks acceptable",
                    "The knee angle and hip height meet the basic depth checks. "
                    "Other alignment details still need to be assessed separately."
                )

        else:
            if kn > 120:
                add(
                    False,
                    "Shallow lunge",
                    "The front knee bends only a little.",
                    "Step a little longer and lower your back knee towards the floor, if comfortable."
                )

            elif kn < 65:
                add(
                    False,
                    "Very deep front-knee bend",
                    "The front knee is bending a lot.",
                    "Try a slightly longer step so the front knee feels comfortable."
                )

            else:
                add(
                    True,
                    "Front knee bend in a typical range",
                    ""
                )

        lim = 55 if ex == "squat" else 30

        if lean > lim:
            add(
                False,
                "Torso leaning forward",
                "The upper body tilts noticeably forward.",
                "Lift your chest, look slightly ahead and brace your core."
                + (" A slightly wider stance can help." if ex == "squat" else "")
            )
        else:
            add(
                True,
                "Upper body position looks fine",
                ""
            )

    else:
        body = _ang(P["shoulder"], P["hip"], P["ankle"])

        dx = P["ankle"][0] - P["shoulder"][0]

        dev = (
            0 if abs(dx) < 20 else
            (
                P["hip"][1] - (
                    P["shoulder"][1]
                    + (P["ankle"][1] - P["shoulder"][1])
                    * (P["hip"][0] - P["shoulder"][0]) / dx
                )
            ) / math.hypot(
                dx,
                P["ankle"][1] - P["shoulder"][1]
            )
        )

        met["body_line"] = round(body)

        angles.append({
            "label": f"{round(body)}° body line",
            "x": N["hip"][0],
            "y": N["hip"][1]
        })

        obs.append(
            f"Shoulder-hip-ankle line ≈ {round(body)}° "
            "(180° = straight, estimate)"
        )

        if ex == "pushup":
            el = _ang(P["shoulder"], P["elbow"], P["wrist"])

            met["elbow_angle"] = round(el)

            angles.append({
                "label": f"{round(el)}° elbow",
                "x": N["elbow"][0],
                "y": N["elbow"][1]
            })

            obs.append(f"Elbow angle ≈ {round(el)}° (estimate)")

            if el > 150:
                obs.append(
                    "This looks like the top of a rep, "
                    "so depth can't be judged from one photo."
                )

            elif el <= 100:
                add(True, "Good push-up depth", "")

            elif el <= 130:
                add(
                    False,
                    "Moderate depth",
                    "The chest isn't getting very close to the floor.",
                    "Lower a little further if comfortable, or practise on an incline or knees."
                )

            else:
                add(
                    False,
                    "Limited depth",
                    "Elbows stay fairly straight.",
                    "Lower your chest towards the floor with control; "
                    "an incline version can help you build up."
                )

        else:
            off = abs(
                P["shoulder"][0] - P["elbow"][0]
            ) / (
                math.hypot(
                    P["shoulder"][0] - P["hip"][0],
                    P["shoulder"][1] - P["hip"][1]
                ) or 1
            )

            met["shoulder_elbow_offset_pct"] = round(off * 100)

            obs.append(
                f"Shoulder vs elbow offset ≈ {round(off * 100)}% of torso length (estimate)"
            )

            if off > .2:
                add(
                    False,
                    "Shoulders not stacked over elbows",
                    "Elbows look ahead of or behind the shoulders.",
                    "Position your elbows directly under your shoulders."
                )
            else:
                add(
                    True,
                    "Shoulders stacked over elbows",
                    ""
                )

        if body >= 165:
            add(
                True,
                "Body line looks straight",
                "Shoulders, hips and ankles are roughly in one line."
            )

        elif dev > 0:
            add(
                False,
                "Hips may be sagging",
                "Hips sit below the shoulder-ankle line.",
                "Gently brace your core and squeeze your glutes to lift the hips into line."
            )

        else:
            add(
                False,
                "Hips may be piking up",
                "Hips sit above the shoulder-ankle line.",
                "Lower your hips slightly so shoulders, hips and ankles form one line."
            )

    pts = [
        {
            "id": i,
            "x": lms[i][0],
            "y": lms[i][1]
        }
        for i in range(11, 29)
        if lms[i][2] >= VIS
    ]

    return {
        "exercise": ex,
        "status": "ok",
        "confidence": round(conf, 2),
        "missing_joints": [],
        "message": None,
        "observations": obs,
        "issues": iss,
        "corrections": cor,
        "metrics": met,
        "overlay": {
            "points": pts,
            "angles": angles
        },
        "single_image": True,
        "disclaimer": DISCLAIMER
    }

"""Estimate formulas. All results are ESTIMATES and are labelled as such in the API."""


def est_activity(steps, height_cm, weight_kg, entered_minutes=None):
    out = {"steps": steps, "distance_km": None, "active_minutes": entered_minutes,
           "active_minutes_source": "entered" if entered_minutes is not None else None, "calories_kcal": None, "estimated": True}
    if height_cm:
        dist = steps * (height_cm * 0.415 / 100) / 1000          # stride = height x 0.415
        out["distance_km"] = round(dist, 2)
        if entered_minutes is None:
            out["active_minutes"] = round(dist / 4.8 * 60)        # assumes 4.8 km/h walking pace
            out["active_minutes_source"] = "estimated"
        if weight_kg:
            out["calories_kcal"] = round(2.5 * weight_kg * (dist / 4.8))   # net walking effort 2.5 METs
    return out


GUIDE = {
    "under": "BMI is a screening number with many possible causes. If it is unintentional or you feel unwell, a doctor or dietitian can help.",
    "healthy": "This is within the typical adult range. Consistency matters more than any single number.",
    "over": "BMI is only a screening number - it does not measure muscle, bone or body shape, and says nothing about your worth. Small steady steps tend to work best: a few hundred more steps than usual, balanced meals, good sleep and strength exercise twice a week. A doctor or registered dietitian can give advice that fits you.",
    "obese": "BMI is a screening tool, not a diagnosis, and many people in this range are healthy and active. Gentle, sustainable habits - regular walking, balanced meals, sleep and strength work - can support well-being. Consider a judgement-free chat with a doctor or registered dietitian.",
}


def bmi(weight_kg, height_cm, age):
    if not (weight_kg and height_cm):
        return {"applicable": False, "reason": "Add height and weight."}
    v = round(weight_kg / (height_cm / 100) ** 2, 1)
    if age and age < 18:   # age is optional: only block when we know the user is under 18
        return {"applicable": False, "value": None, "reason": "Adult BMI categories apply from age 18. Ask a doctor about growth charts."}
    k = "under" if v < 18.5 else "healthy" if v < 25 else "over" if v < 30 else "obese"
    cat = {"under": "Underweight range", "healthy": "Healthy range", "over": "Overweight range", "obese": "Obesity range"}[k]
    return {"applicable": True, "value": v, "category": cat, "guidance": GUIDE[k], "estimated": True,
            "note": "A screening estimate, not a diagnosis. May not suit pregnancy or people with high muscle mass."}

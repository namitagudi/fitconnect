import base64
import json
import logging
import urllib.error
import urllib.request
from flask import current_app
from .util import ApiError


def image_block(data: bytes, media_type: str):
    return {"inline_data": {"mime_type": media_type, "data": base64.b64encode(data).decode()}}


def call_gemini(system, messages, max_tokens=900):
    """Calls the Gemini API from the SERVER (the key never reaches the browser)."""
    key = current_app.config["GEMINI_API_KEY"]
    if not key:
        raise ApiError(503, "ai_unavailable", "AI isn't set up on this server yet. The trainer must add a GEMINI_API_KEY.")

    contents = []
    for msg in messages:
        role = "user" if msg.get("role") == "user" else "model"
        items = msg.get("content", [])
        if isinstance(items, str):
            items = [{"type": "text", "text": items}]
        parts = []
        for item in items:
            if "inline_data" in item:                      # produced by image_block()
                parts.append({"inline_data": item["inline_data"]})
            elif item.get("type") == "text":
                parts.append({"text": item.get("text", "")})
            elif item.get("type") == "image":
                src = item.get("source", {})
                parts.append({"inline_data": {"mime_type": src.get("media_type"), "data": src.get("data")}})
        if parts:
            if contents and contents[-1]["role"] == role:      # Gemini wants alternating turns
                contents[-1]["parts"].extend(parts)
            else:
                contents.append({"role": role, "parts": parts})
    while contents and contents[0]["role"] != "user":          # history must start with a user turn
        contents.pop(0)

    # headroom on max tokens: newer models spend part of the budget "thinking"
    payload = {"contents": contents, "generationConfig": {"maxOutputTokens": max(max_tokens, 2048)}}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}

    model = current_app.config.get("GEMINI_MODEL", "gemini-3.8-flash")
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json", "x-goog-api-key": key},   # key in a header, not the URL (keeps it out of logs)
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        logging.warning("Gemini API error %s: %s", e.code, e.read()[:300])
        msg = {404: "The AI model name isn't available. Ask the trainer to set GEMINI_MODEL to a current model (for example gemini-3.8-flash).",
               400: "The AI request was rejected. Ask the trainer to check GEMINI_API_KEY and GEMINI_MODEL.",
               401: "The AI key was rejected. Ask the trainer to check GEMINI_API_KEY.",
               403: "The AI key was rejected. Ask the trainer to check GEMINI_API_KEY.",
               429: "The AI is busy or its quota is used up. Please try again in a few minutes."}.get(e.code, "The AI service returned an error. Please try again in a moment.")
        raise ApiError(502, "ai_error", msg)
    except (urllib.error.URLError, TimeoutError):
        raise ApiError(502, "ai_error", "Couldn't reach the AI service. Please try again.")

    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError):
        logging.warning("Unexpected Gemini response: %s", str(data)[:300])
        raise ApiError(502, "ai_error", "The AI gave no usable answer. Please try again.")
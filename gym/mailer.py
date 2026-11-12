"""Tiny SMTP sender. Configure in .env:
SMTP_HOST, SMTP_PORT (587 default; 465 uses SSL), SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_TLS (set 0 to disable STARTTLS)."""
import logging
import os
import smtplib
from email.message import EmailMessage


def send_mail(to, subject, text):
    """Returns True if the message was handed to the SMTP server, False otherwise (never raises)."""
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        logging.warning("SMTP_HOST is not set, so no email was sent to %s.", to)
        return False
    port = int(os.environ.get("SMTP_PORT", "587") or 587)
    user, pw = os.environ.get("SMTP_USER", ""), os.environ.get("SMTP_PASSWORD", "")
    msg = EmailMessage()
    msg["From"] = os.environ.get("SMTP_FROM") or user or "no-reply@localhost"
    msg["To"], msg["Subject"] = to, subject
    msg.set_content(text)
    try:
        if port == 465:
            s = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            s = smtplib.SMTP(host, port, timeout=15)
            if os.environ.get("SMTP_TLS", "1") != "0":
                s.starttls()
        with s:
            if user:
                s.login(user, pw)
            s.send_message(msg)
        return True
    except Exception:
        logging.exception("Could not send email to %s", to)
        return False
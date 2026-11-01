"""The create and reset link emails, sent through an SMTP server.

TUTORS_DEV=1 prints them to the console instead, for local work.  Without
SMTP_HOST, sending reports that email is not configured.
"""

import os
import smtplib
from email.message import EmailMessage

DEFAULT_FROM = "Tutors <noreply@example.edu>"

CREATE_SUBJECT = "Create your Tutors account"
CREATE_BODY = """Open this link within 30 minutes to choose a username and a 4-digit passcode for the tutors:

    {url}

If you did not ask for this, ignore this email.
"""

RESET_SUBJECT = "Your Tutors username and passcode"
RESET_BODY = """Your Tutors username is {username}.

Open this link within 30 minutes to choose a new username or a new passcode:

    {url}

If you did not ask for this, ignore this email.
"""


def link_email(kind, url, username):
    """(subject, body) for a create or reset link."""
    if kind == "reset":
        return RESET_SUBJECT, RESET_BODY.format(url=url, username=username)
    return CREATE_SUBJECT, CREATE_BODY.format(url=url)


def make_sender():
    """send(to, subject, body), chosen from the environment."""
    if os.environ.get("TUTORS_DEV") == "1":
        def send(to, subject, body):
            print(f"mail (dev) to {to}: {subject}\n{body}", flush=True)
        return send

    if os.environ.get("SMTP_HOST"):
        host = os.environ["SMTP_HOST"]
        port = int(os.environ.get("SMTP_PORT", "587"))
        user, password = os.environ.get("SMTP_USER", ""), os.environ.get("SMTP_PASSWORD", "")
        sender = os.environ.get("MAIL_FROM") or DEFAULT_FROM

        def send(to, subject, body):
            msg = EmailMessage()
            msg["From"], msg["To"], msg["Subject"] = sender, to, subject
            msg.set_content(body)
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.starttls()
                if user:
                    s.login(user, password)
                s.send_message(msg)
        return send

    def send(to, subject, body):
        raise RuntimeError("no email sender configured (set SMTP_HOST)")
    return send

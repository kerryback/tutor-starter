import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import mail  # noqa: E402

URL = "https://tutors.example.edu/link?t=abc"


def test_create_email_has_link():
    subject, body = mail.link_email("create", URL, None)
    assert subject == "Create your Tutors account"
    assert URL in body and "30 minutes" in body


def test_reset_email_has_username_and_link():
    subject, body = mail.link_email("reset", URL, "jdoe")
    assert subject == "Your Tutors username and passcode"
    assert URL in body and "jdoe" in body and "30 minutes" in body


def test_dev_sender_prints(monkeypatch, capsys):
    monkeypatch.setenv("TUTORS_DEV", "1")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    mail.make_sender()("jdoe@example.edu", "Subject", "Open " + URL)
    out = capsys.readouterr().out
    assert URL in out and "jdoe@example.edu" in out


def test_smtp_sender_uses_resend_settings(monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def starttls(self):
            sent.append(("tls",))

        def login(self, user, password):
            sent.append(("login", user, password))

        def send_message(self, msg):
            sent.append(("msg", msg["From"], msg["To"], msg["Subject"]))

    monkeypatch.delenv("TUTORS_DEV", raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.resend.com")
    monkeypatch.setenv("SMTP_USER", "resend")
    monkeypatch.setenv("SMTP_PASSWORD", "key")
    monkeypatch.delenv("MAIL_FROM", raising=False)
    monkeypatch.setattr(mail.smtplib, "SMTP", FakeSMTP)
    mail.make_sender()("jdoe@example.edu", "S", "B")
    assert sent == [("connect", "smtp.resend.com", 587), ("tls",), ("login", "resend", "key"),
                    ("msg", "Tutors <noreply@example.edu>", "jdoe@example.edu", "S")]

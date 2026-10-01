"""Slack (incoming webhook) and email (SMTP), standard library only. Secrets come from the environment."""
import json
import os
import smtplib
import urllib.request
from email.message import EmailMessage

from bot.config import CHANNELS, Config


def slack(cfg: Config, subject: str, text: str) -> None:
    body = json.dumps({"text": f"*{subject}*\n{text}"}).encode()
    req = urllib.request.Request(os.environ["TK_SLACK_WEBHOOK"], body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status != 200:
            raise RuntimeError(f"Slack answered {r.status}")


def email(cfg: Config, subject: str, text: str) -> None:
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, os.environ["TK_SMTP_USER"], cfg.notify.email_to
    msg.set_content(text)
    with smtplib.SMTP(os.environ["TK_SMTP_HOST"], int(os.environ.get("TK_SMTP_PORT", "587")), timeout=30) as s:
        s.starttls()
        s.login(os.environ["TK_SMTP_USER"], os.environ["TK_SMTP_PASSWORD"])
        s.send_message(msg)


SENDERS = {"slack": slack, "email": email}


def send(cfg: Config, kind: str, subject: str, text: str, senders=SENDERS) -> list[str]:
    """Sends to the channels configured for `kind`; a channel that fails hands the message to the other.
    Returns a line per failure, for the next report."""
    failures, tried, delivered = [], set(), set()
    for channel in getattr(cfg.notify, kind):
        for ch in [channel] + [c for c in CHANNELS if c != channel]:
            if ch in delivered:
                break
            if ch in tried:
                continue
            tried.add(ch)
            try:
                senders[ch](cfg, subject, text)
                delivered.add(ch)
                break
            except Exception as e:  # any failure, from a missing secret to a timeout, means try the other channel
                failures.append(f"{ch}: {type(e).__name__}: {e}")
    return failures

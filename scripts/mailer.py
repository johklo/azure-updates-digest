"""SMTP helper shared by the subscription mailbox and the digest sender."""

from __future__ import annotations

import os
import smtplib
import ssl
import sys
import time
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid


class MailError(RuntimeError):
    pass


def smtp_config() -> dict:
    """Read SMTP settings from the environment.

    SMTP_SECURITY selects the transport: ``starttls`` (default), ``ssl`` or ``none``.
    Authentication is skipped when no password is supplied, which suits an internal relay.
    """
    server = os.environ.get("SMTP_SERVER", "").strip()
    if not server:
        raise MailError("SMTP_SERVER is not set.")

    port = int(os.environ.get("SMTP_PORT", "587") or 587)
    security = os.environ.get("SMTP_SECURITY", "").strip().lower()
    if not security:
        security = "ssl" if port == 465 else "starttls"
    if security not in ("starttls", "ssl", "none"):
        raise MailError(f"SMTP_SECURITY must be starttls, ssl or none (got {security!r}).")

    username = os.environ.get("SMTP_USERNAME", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()
    if password and not username:
        raise MailError("SMTP_PASSWORD is set but SMTP_USERNAME is missing.")

    from_addr = os.environ.get("SMTP_FROM", "").strip() or username
    if not from_addr:
        raise MailError("Set SMTP_FROM (or SMTP_USERNAME) so the digest has a sender address.")

    return {
        "server": server,
        "port": port,
        "security": security,
        "username": username,
        "password": password,
        "from_addr": from_addr,
        "from_name": os.environ.get("SMTP_FROM_NAME", "").strip() or "Azure Updates Digest",
    }


def connect(cfg: dict, retries: int = 3):
    """Open an SMTP session, retrying transient failures."""
    last = None
    for attempt in range(retries):
        try:
            if cfg["security"] == "ssl":
                client = smtplib.SMTP_SSL(cfg["server"], cfg["port"], timeout=60,
                                          context=ssl.create_default_context())
            else:
                client = smtplib.SMTP(cfg["server"], cfg["port"], timeout=60)
                client.ehlo()
                if cfg["security"] == "starttls":
                    client.starttls(context=ssl.create_default_context())
                    client.ehlo()
            if cfg["password"]:
                client.login(cfg["username"], cfg["password"])
            return client
        except (smtplib.SMTPException, OSError) as error:
            last = error
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise MailError(f"Could not connect to {cfg['server']}:{cfg['port']}: {last}")


def build_message(cfg: dict, to_addr: str, subject: str, text: str, html: str | None = None,
                  headers: dict | None = None) -> EmailMessage:
    message = EmailMessage()
    message["From"] = formataddr((cfg["from_name"], cfg["from_addr"]))
    message["To"] = to_addr
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain=cfg["from_addr"].split("@")[-1])
    # Mark our own mail as automatic so other systems do not bounce or auto-reply to it.
    message["Auto-Submitted"] = "auto-generated"
    for key, value in (headers or {}).items():
        if value:
            message[key] = value
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")
    return message


def send(client, message: EmailMessage) -> None:
    client.send_message(message)


def send_one(cfg: dict, to_addr: str, subject: str, text: str, html: str | None = None,
             headers: dict | None = None) -> None:
    """Open a session, send a single message and close. Used for low-volume mail."""
    client = connect(cfg)
    try:
        send(client, build_message(cfg, to_addr, subject, text, html, headers))
    finally:
        try:
            client.quit()
        except Exception:
            pass
    print(f"  sent to {to_addr}: {subject}", file=sys.stderr)

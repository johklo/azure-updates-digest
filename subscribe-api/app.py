"""Subscription intake for the Azure Updates digest.

The site is static, so this small service is what the signup form posts to. It keeps no
database: a confirmation link carries an HMAC-signed token, and once the reader clicks it
the address is handed to a GitHub workflow that appends it to the encrypted subscriber
list in the repository.

Routes
    POST /api/subscribe        {"email": "..."} -> sends a confirmation mail
    GET  /api/confirm          double opt-in landing page, records the subscription
    GET  /api/unsubscribe      one-click removal used by the footer and mail clients
    GET  /api/health           liveness probe
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import threading
import time
from collections import defaultdict, deque

from flask import Flask, jsonify, request

app = Flask(__name__)

EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}$")
BLOCKED = ("noreply", "no-reply", "donotreply", "mailer-daemon", "postmaster")

TOKEN_TTL = 60 * 60 * 48          # confirmation links last two days
UNSUB_TTL = 60 * 60 * 24 * 3650   # unsubscribe links must keep working
RATE_LIMIT = 5                    # subscribe attempts per IP per window
RATE_WINDOW = 300

_hits: dict[str, deque] = defaultdict(deque)


def setting(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def site_url() -> str:
    return setting("SITE_URL", "https://johklo.github.io/azure-updates-digest/").rstrip("/")


def allowed_origin(origin: str) -> str:
    allowed = [o.strip().rstrip("/") for o in setting("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    origin = (origin or "").rstrip("/")
    if origin and origin in allowed:
        return origin
    return allowed[0] if allowed else "*"


@app.after_request
def cors(response):
    response.headers["Access-Control-Allow-Origin"] = allowed_origin(request.headers.get("Origin", ""))
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    response.headers["Vary"] = "Origin"
    return response


def valid_email(email: str) -> bool:
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 254:
        return False
    return not any(email.split("@", 1)[0].startswith(bad) for bad in BLOCKED)


def sign(email: str, action: str, expires: int) -> str:
    secret = setting("TOKEN_SECRET").encode("utf-8")
    payload = f"{email}|{action}|{expires}".encode("utf-8")
    digest = hmac.new(secret, payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def make_link(email: str, action: str, ttl: int) -> str:
    expires = int(time.time()) + ttl
    token = sign(email, action, expires)
    encoded = base64.urlsafe_b64encode(email.encode("utf-8")).decode("ascii").rstrip("=")
    base = setting("PUBLIC_BASE_URL", request.url_root.rstrip("/"))
    return f"{base}/api/{action}?e={encoded}&x={expires}&t={token}"


def read_link(action: str) -> str | None:
    """Validate a signed link and return the address it refers to."""
    encoded = request.args.get("e", "")
    expires = request.args.get("x", "")
    token = request.args.get("t", "")
    if not encoded or not expires.isdigit() or not token:
        return None
    if int(expires) < time.time():
        return None
    try:
        email = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8")
    except Exception:
        return None
    if not hmac.compare_digest(token, sign(email, action, int(expires))):
        return None
    return email if valid_email(email) else None


def rate_limited(ip: str) -> bool:
    now = time.time()
    hits = _hits[ip]
    while hits and now - hits[0] > RATE_WINDOW:
        hits.popleft()
    if len(hits) >= RATE_LIMIT:
        return True
    hits.append(now)
    return False


def send_confirmation(email: str) -> None:
    from azure.communication.email import EmailClient

    client = EmailClient.from_connection_string(setting("ACS_CONNECTION_STRING"))
    link = make_link(email, "confirm", TOKEN_TTL)
    text = (
        "\uad6c\ub3c5\uc744 \ud655\uc778\ud574 \uc8fc\uc138\uc694.\n\n"
        "\uc544\ub798 \ub9c1\ud06c\ub97c \ub204\ub974\uba74 \uad6c\ub3c5\uc774 \uc644\ub8cc\ub418\uba70, \ub9e4\uc77c \uc544\uce68 Azure \uc81c\ud488 \uc5c5\ub370\uc774\ud2b8 \uc694\uc57d\uc744 \ubc1b\uc544\ubcf4\uc2e4 \uc218 \uc788\uc2b5\ub2c8\ub2e4.\n"
        f"{link}\n\n"
        "\ubcf8\uc778\uc774 \uc2e0\uccad\ud558\uc9c0 \uc54a\uc558\ub2e4\uba74 \uc774 \uba54\uc77c\uc744 \ubb34\uc2dc\ud558\uc154\ub3c4 \ub429\ub2c8\ub2e4. \ud655\uc778 \uc804\uc5d0\ub294 \uc5b4\ub5a4 \uba54\uc77c\ub3c4 \ubc1c\uc1a1\ub418\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.\n"
    )
    html = f"""<div style="font-family:Segoe UI,Helvetica,Arial,sans-serif;max-width:520px;color:#1b1f23">
<h2 style="color:#0078d4;margin:0 0 12px">\uad6c\ub3c5 \ud655\uc778</h2>
<p style="font-size:15px;line-height:1.6">\uc544\ub798 \ubc84\ud2bc\uc744 \ub204\ub974\uba74 \uad6c\ub3c5\uc774 \uc644\ub8cc\ub418\uba70,
\ub9e4\uc77c \uc544\uce68 Azure \uc81c\ud488 \uc5c5\ub370\uc774\ud2b8 \uc694\uc57d\uc744 \ubc1b\uc544\ubcf4\uc2e4 \uc218 \uc788\uc2b5\ub2c8\ub2e4.</p>
<p style="margin:22px 0"><a href="{link}"
style="background:#0078d4;color:#fff;padding:11px 22px;border-radius:6px;text-decoration:none;font-weight:600">\uad6c\ub3c5 \ud655\uc778\ud558\uae30</a></p>
<p style="font-size:12px;color:#57606a">\ubcf8\uc778\uc774 \uc2e0\uccad\ud558\uc9c0 \uc54a\uc558\ub2e4\uba74 \uc774 \uba54\uc77c\uc744 \ubb34\uc2dc\ud558\uc154\ub3c4 \ub429\ub2c8\ub2e4.
\ud655\uc778 \uc804\uc5d0\ub294 \uc5b4\ub5a4 \uba54\uc77c\ub3c4 \ubc1c\uc1a1\ub418\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.</p></div>"""

    client.begin_send({
        "senderAddress": setting("SENDER_ADDRESS"),
        "recipients": {"to": [{"address": email}]},
        "content": {"subject": "[Azure Updates] \uad6c\ub3c5 \ud655\uc778\uc744 \ub9c8\uc800 \ud574\uc8fc\uc138\uc694", "plainText": text, "html": html},
    }).result()


STORE_PATH = os.environ.get("STORE_PATH", "/home/data/subscribers.json")
_store_lock = threading.Lock()


def _load() -> dict:
    try:
        with open(STORE_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict) and isinstance(data.get("subscribers"), list):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"version": 1, "subscribers": []}


def _save(store: dict) -> None:
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    store["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    store["active"] = sum(1 for s in store["subscribers"] if s.get("status") == "active")
    tmp = STORE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(store, handle, ensure_ascii=False, indent=1)
    os.replace(tmp, STORE_PATH)


def record(action: str, email: str) -> str:
    """Apply a confirmed subscribe or unsubscribe to the durable store."""
    email = email.strip().lower()
    with _store_lock:
        store = _load()
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        existing = next((s for s in store["subscribers"] if s.get("email") == email), None)

        if action == "subscribe":
            if existing is None:
                store["subscribers"].append(
                    {"email": email, "status": "active", "created_at": now, "updated_at": now, "sent_count": 0}
                )
                outcome = "created"
            elif existing.get("status") == "active":
                outcome = "already-active"
            else:
                existing.update(status="active", updated_at=now)
                outcome = "reactivated"
        else:
            if existing is None:
                outcome = "not-found"
            elif existing.get("status") != "active":
                outcome = "already-unsubscribed"
            else:
                existing.update(status="unsubscribed", updated_at=now)
                outcome = "unsubscribed"

        _save(store)
        return outcome


def page(title: str, message: str, tone: str = "#0078d4") -> str:
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title></head>
<body style="margin:0;background:#f4f6f8;font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#1b1f23">
<div style="max-width:520px;margin:12vh auto;background:#fff;border:1px solid #e1e4e8;border-radius:10px;padding:36px">
<h1 style="color:{tone};font-size:22px;margin:0 0 14px">{title}</h1>
<p style="font-size:15px;line-height:1.65;margin:0 0 22px">{message}</p>
<a href="{site_url()}" style="color:#0078d4;font-weight:600;text-decoration:none">&larr; \ub2e4\uc774\uc81c\uc2a4\ud2b8 \uc0ac\uc774\ud2b8\ub85c \uac00\uae30</a>
</div></body></html>"""


@app.route("/api/health")
def health():
    ready = all(setting(k) for k in ("ACS_CONNECTION_STRING", "SENDER_ADDRESS", "TOKEN_SECRET"))
    return jsonify({"ok": True, "configured": ready, "active": _load().get("active", 0)})


@app.route("/api/subscribe", methods=["POST", "OPTIONS"])
def subscribe():
    if request.method == "OPTIONS":
        return ("", 204)

    payload = request.get_json(silent=True) or request.form or {}
    email = str(payload.get("email", "")).strip().lower()

    if not valid_email(email):
        return jsonify({"ok": False, "error": "invalid-email",
                        "message": "\ubc1b\uc744 \uc218 \uc788\ub294 \uc774\uba54\uc77c \uc8fc\uc18c\ub97c \uc785\ub825\ud574 \uc8fc\uc138\uc694."}), 400

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    if rate_limited(ip):
        return jsonify({"ok": False, "error": "rate-limited",
                        "message": "\uc694\uccad\uc774 \ub108\ubb34 \uc0c1\uc2b5\ub2c8\ub2e4. \uc7a0\uc2dc \ud6c4 \ub2e4\uc2dc \uc2dc\ub3c4\ud574 \uc8fc\uc138\uc694."}), 429

    try:
        send_confirmation(email)
    except Exception as error:  # pragma: no cover - depends on the mail service
        app.logger.exception("confirmation failed")
        return jsonify({"ok": False, "error": "send-failed",
                        "message": "\uc9c0\uae08\uc740 \uc2e0\uccad\uc744 \ucc98\ub9ac\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4. \uc7a0\uc2dc \ud6c4 \ub2e4\uc2dc \uc2dc\ub3c4\ud574 \uc8fc\uc138\uc694.",
                        "detail": str(error)[:120]}), 502

    return jsonify({"ok": True,
                    "message": "\ud655\uc778 \uba54\uc77c\uc744 \ubcf4\ub0c8\uc2b5\ub2c8\ub2e4. \uba54\uc77c\uc758 \ub9c1\ud06c\ub97c \ub204\ub974\uc2dc\uba74 \uad6c\ub3c5\uc774 \uc644\ub8cc\ub429\ub2c8\ub2e4."})


@app.route("/api/confirm")
def confirm():
    email = read_link("confirm")
    if not email:
        return page("\ub9c1\ud06c\uac00 \uc720\ud6a8\ud558\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4",
                    "\ub9c1\ud06c\uac00 \ub9cc\ub8cc\ub418\uc5c8\uac70\ub098 \uc190\uc0c1\ub418\uc5c8\uc2b5\ub2c8\ub2e4. \uc0ac\uc774\ud2b8\uc5d0\uc11c \ub2e4\uc2dc \uc2e0\uccad\ud574 \uc8fc\uc138\uc694.", "#b02a37"), 400
    try:
        outcome = record("subscribe", email)
    except Exception:
        app.logger.exception("dispatch failed")
        return page("\uc7a0\uc2dc \ud6c4 \ub2e4\uc2dc \uc2dc\ub3c4\ud574 \uc8fc\uc138\uc694", "\ub4f1\ub85d \uc911 \ubb38\uc81c\uac00 \ubc1c\uc0dd\ud588\uc2b5\ub2c8\ub2e4.", "#b02a37"), 502
    return page("\uad6c\ub3c5\uc774 \uc644\ub8cc\ub418\uc5c8\uc2b5\ub2c8\ub2e4",
                "\ub9e4\uc77c \uc544\uce68 Azure \uc81c\ud488 \uc5c5\ub370\uc774\ud2b8 \uc694\uc57d\uc744 \ubcf4\ub0b4\ub4dc\ub9bd\ub2c8\ub2e4. "
                "\uba54\uc77c \ud558\ub2e8\uc758 \ub9c1\ud06c\ub85c \uc5b8\uc81c\ub4e0 \uc218\uc2e0\uc744 \uba48\ucd9c \uc218 \uc788\uc2b5\ub2c8\ub2e4.")


@app.route("/api/unsubscribe", methods=["GET", "POST"])
def unsubscribe():
    email = read_link("unsubscribe")
    if not email:
        return page("\ub9c1\ud06c\uac00 \uc720\ud6a8\ud558\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4", "\ub9c1\ud06c\uac00 \uc190\uc0c1\ub418\uc5c8\uc2b5\ub2c8\ub2e4.", "#b02a37"), 400
    try:
        record("unsubscribe", email)
    except Exception:
        app.logger.exception("dispatch failed")
        return page("\uc7a0\uc2dc \ud6c4 \ub2e4\uc2dc \uc2dc\ub3c4\ud574 \uc8fc\uc138\uc694", "\ud574\uc9c0 \ucc98\ub9ac \uc911 \ubb38\uc81c\uac00 \ubc1c\uc0dd\ud588\uc2b5\ub2c8\ub2e4.", "#b02a37"), 502
    return page("\uc218\uc2e0\uc774 \ud574\uc9c0\ub418\uc5c8\uc2b5\ub2c8\ub2e4", "\uc55e\uc73c\ub85c\ub294 \uba54\uc77c\uc744 \ubcf4\ub0b4\ub4dc\ub9ac\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4. \uc5b8\uc81c\ub4e0 \ub2e4\uc2dc \uad6c\ub3c5\ud558\uc2e4 \uc218 \uc788\uc2b5\ub2c8\ub2e4.")


@app.route("/api/subscribers")
def subscribers():
    """Authenticated list used by the digest workflow when it sends the daily mail."""
    if not hmac.compare_digest(request.headers.get("X-Api-Key", ""), setting("TOKEN_SECRET")):
        return jsonify({"ok": False}), 403
    store = _load()
    active = [s for s in store["subscribers"] if s.get("status") == "active"]
    out = []
    for entry in active:
        out.append({
            "email": entry["email"],
            "created_at": entry.get("created_at"),
            "unsubscribe_url": make_link(entry["email"], "unsubscribe", UNSUB_TTL),
        })
    return jsonify({"ok": True, "count": len(out), "subscribers": out})


@app.route("/api/unsubscribe-link")
def unsubscribe_link():
    """Used by the digest sender to mint a per-subscriber unsubscribe URL."""
    if not hmac.compare_digest(request.headers.get("X-Api-Key", ""), setting("TOKEN_SECRET")):
        return jsonify({"ok": False}), 403
    email = (request.args.get("email") or "").strip().lower()
    if not valid_email(email):
        return jsonify({"ok": False}), 400
    return jsonify({"ok": True, "url": make_link(email, "unsubscribe", UNSUB_TTL)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

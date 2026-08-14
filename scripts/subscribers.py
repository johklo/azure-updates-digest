"""Encrypted subscriber store for the email digest.

The repository is public, so subscriber addresses are never committed in clear text.
Each record keeps:

* ``id``     - HMAC-SHA256 of the normalised address, used for lookups and dedupe
* ``email``  - the address encrypted with Fernet (key from the ``SUBSCRIBER_KEY`` secret)
* ``masked`` - a display form such as ``jo***@example.com`` for logs and audits
* ``token``  - an unguessable value used to build one-click unsubscribe links

Reading counts, statuses and masked forms needs no key. Only sending mail, which happens
inside GitHub Actions, needs the key to recover the real addresses.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys

from common import DATA_DIR, read_json, utcnow, write_json

SUBSCRIBERS_PATH = DATA_DIR / "subscribers.json"

STATUS_ACTIVE = "active"
STATUS_UNSUBSCRIBED = "unsubscribed"

EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}$")

# Addresses that must never be subscribed: mailing the digest back to itself, or to a
# no-reply mailbox, would create a mail loop.
BLOCKED_LOCAL_PARTS = ("noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon", "postmaster")


class SubscriberError(RuntimeError):
    """Raised when the store cannot satisfy a request."""


def normalise(email: str) -> str:
    return (email or "").strip().strip("<>").lower()


def is_valid(email: str) -> bool:
    email = normalise(email)
    if not EMAIL_RE.match(email):
        return False
    local = email.split("@", 1)[0]
    return not any(local.startswith(bad) for bad in BLOCKED_LOCAL_PARTS)


def mask(email: str) -> str:
    email = normalise(email)
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    head = local[:2] if len(local) > 2 else local[:1]
    return f"{head}***@{domain}"


def _key_material() -> bytes:
    key = os.environ.get("SUBSCRIBER_KEY", "").strip()
    if not key:
        raise SubscriberError(
            "SUBSCRIBER_KEY is not set. Generate one with 'python scripts/subscribers.py keygen' "
            "and store it as a repository secret."
        )
    return key.encode("utf-8")


def _fernet():
    try:
        from cryptography.fernet import Fernet
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise SubscriberError("The 'cryptography' package is required: pip install cryptography") from error
    try:
        return Fernet(_key_material())
    except Exception as error:
        raise SubscriberError(f"SUBSCRIBER_KEY is not a valid Fernet key: {error}") from error


def subscriber_id(email: str) -> str:
    """Stable, non-reversible identifier derived from the address."""
    return hmac.new(_key_material(), normalise(email).encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def encrypt(email: str) -> str:
    return _fernet().encrypt(normalise(email).encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode("ascii")).decode("utf-8")


def has_key() -> bool:
    return bool(os.environ.get("SUBSCRIBER_KEY", "").strip())


def load_store() -> dict:
    store = read_json(SUBSCRIBERS_PATH, {"version": 1, "updated_at": None, "subscribers": []})
    if not isinstance(store, dict) or not isinstance(store.get("subscribers"), list):
        store = {"version": 1, "updated_at": None, "subscribers": []}
    return store


def save_store(store: dict) -> None:
    store["updated_at"] = utcnow().isoformat()
    store["active"] = sum(1 for s in store.get("subscribers", []) if s.get("status") == STATUS_ACTIVE)
    store["subscribers"].sort(key=lambda s: (s.get("status", ""), s.get("created_at") or ""))
    write_json(SUBSCRIBERS_PATH, store)


def find(store: dict, email: str) -> dict | None:
    target = subscriber_id(email)
    for record in store.get("subscribers", []):
        if record.get("id") == target:
            return record
    return None


def find_by_token(store: dict, token: str) -> dict | None:
    token = (token or "").strip()
    if not token:
        return None
    for record in store.get("subscribers", []):
        if hmac.compare_digest(str(record.get("token", "")), token):
            return record
    return None


def subscribe(store: dict, email: str, source: str = "email", prefs: dict | None = None) -> tuple[str, dict]:
    """Add or reactivate a subscriber. Returns (outcome, record).

    outcome is one of: created, reactivated, already-active.
    """
    if not is_valid(email):
        raise SubscriberError(f"Not a subscribable address: {email!r}")

    now = utcnow().isoformat()
    record = find(store, email)
    if record is None:
        record = {
            "id": subscriber_id(email),
            "email": encrypt(email),
            "masked": mask(email),
            "token": secrets.token_urlsafe(18),
            "status": STATUS_ACTIVE,
            "source": source,
            "created_at": now,
            "updated_at": now,
            "prefs": prefs or {},
            "sent_count": 0,
        }
        store.setdefault("subscribers", []).append(record)
        return "created", record

    if record.get("status") == STATUS_ACTIVE:
        if prefs:
            record["prefs"] = prefs
            record["updated_at"] = now
        return "already-active", record

    record["status"] = STATUS_ACTIVE
    record["updated_at"] = now
    record["email"] = encrypt(email)
    record["masked"] = mask(email)
    record.setdefault("token", secrets.token_urlsafe(18))
    if prefs:
        record["prefs"] = prefs
    return "reactivated", record


def unsubscribe(store: dict, email: str | None = None, token: str | None = None) -> tuple[str, dict | None]:
    """Suppress a subscriber by address or unsubscribe token."""
    record = find_by_token(store, token) if token else (find(store, email) if email else None)
    if record is None:
        return "not-found", None
    if record.get("status") == STATUS_UNSUBSCRIBED:
        return "already-unsubscribed", record
    record["status"] = STATUS_UNSUBSCRIBED
    record["updated_at"] = utcnow().isoformat()
    return "unsubscribed", record


def active_records(store: dict) -> list:
    return [s for s in store.get("subscribers", []) if s.get("status") == STATUS_ACTIVE]


def active_recipients(store: dict) -> list:
    """Decrypt the active subscribers. Requires SUBSCRIBER_KEY."""
    out = []
    for record in active_records(store):
        try:
            address = decrypt(record["email"])
        except Exception:
            print(f"  ! could not decrypt {record.get('masked')}, skipping", file=sys.stderr)
            continue
        out.append({"email": address, "record": record})
    return out


def _cmd_keygen(_args) -> int:
    from cryptography.fernet import Fernet

    print(Fernet.generate_key().decode("ascii"))
    print(
        "Store this as the SUBSCRIBER_KEY repository secret. "
        "Losing it makes the existing subscriber list unreadable.",
        file=sys.stderr,
    )
    return 0


def _cmd_add(args) -> int:
    store = load_store()
    prefs = json.loads(args.prefs) if args.prefs else None
    outcome, record = subscribe(store, args.email, source=args.source, prefs=prefs)
    save_store(store)
    print(f"{outcome}: {record['masked']}")
    return 0


def _cmd_remove(args) -> int:
    store = load_store()
    outcome, record = unsubscribe(store, email=args.email, token=args.token)
    save_store(store)
    print(f"{outcome}: {record['masked'] if record else args.email or args.token}")
    return 0


def _cmd_list(args) -> int:
    store = load_store()
    records = store.get("subscribers", [])
    if args.active:
        records = [r for r in records if r.get("status") == STATUS_ACTIVE]
    for record in records:
        print(f"{record.get('status','?'):14} {record.get('masked','?'):34} {record.get('created_at','')[:10]} {record.get('source','')}")
    print(f"\n{len(records)} record(s).", file=sys.stderr)
    return 0


def _cmd_stats(_args) -> int:
    store = load_store()
    records = store.get("subscribers", [])
    active = sum(1 for r in records if r.get("status") == STATUS_ACTIVE)
    print(json.dumps({
        "total": len(records),
        "active": active,
        "unsubscribed": len(records) - active,
        "updated_at": store.get("updated_at"),
        "key_present": has_key(),
    }, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the encrypted digest subscriber list.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("keygen", help="Generate a new SUBSCRIBER_KEY.").set_defaults(func=_cmd_keygen)

    add = sub.add_parser("add", help="Subscribe an address.")
    add.add_argument("email")
    add.add_argument("--source", default="manual")
    add.add_argument("--prefs", default=None, help="JSON object of preferences.")
    add.set_defaults(func=_cmd_add)

    remove = sub.add_parser("remove", help="Unsubscribe an address or token.")
    remove.add_argument("email", nargs="?")
    remove.add_argument("--token", default=None)
    remove.set_defaults(func=_cmd_remove)

    listing = sub.add_parser("list", help="List subscribers (masked).")
    listing.add_argument("--active", action="store_true")
    listing.set_defaults(func=_cmd_list)

    sub.add_parser("stats", help="Show counts.").set_defaults(func=_cmd_stats)

    args = parser.parse_args()
    try:
        return args.func(args)
    except SubscriberError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

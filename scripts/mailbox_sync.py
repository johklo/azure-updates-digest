"""Turn the digest mailbox into a self-service subscription desk.

Anyone can mail the digest address with "subscribe" (or "\uad6c\ub3c5") to join and
"unsubscribe" (or "\uc218\uc2e0\uac70\ubd80") to leave. This script polls the mailbox over IMAP,
applies each request to the encrypted subscriber store and replies with a confirmation.

Because the request arrives from the address itself, the sender has already proven control
of that mailbox, so no extra confirmation round-trip is required.
"""

from __future__ import annotations

import argparse
import email
import imaplib
import os
import re
import sys
from email.header import decode_header
from email.utils import parseaddr

import mailer
import subscribers as subs
from common import load_config, set_action_output

UNSUBSCRIBE_WORDS = ("unsubscribe", "\uc218\uc2e0\uac70\ubd80", "\uc218\uc2e0 \uac70\ubd80", "\uad6c\ub3c5\ud574\uc9c0",
                     "\uad6c\ub3c5 \ud574\uc9c0", "\ud574\uc9c0", "\ucde8\uc18c", "stop", "remove me", "opt out", "opt-out")
SUBSCRIBE_WORDS = ("subscribe", "\uad6c\ub3c5", "\uc2e0\uccad", "\ub4f1\ub85d", "join", "sign up", "signup", "start")

# Never answer robots: doing so creates mail loops.
LOOP_HEADERS = {
    "auto-submitted": lambda v: v.lower().startswith("auto"),
    "precedence": lambda v: v.lower() in ("bulk", "list", "junk", "auto_reply"),
    "x-auto-response-suppress": lambda v: True,
    "list-id": lambda v: True,
    "list-unsubscribe": lambda v: True,
}

TOKEN_RE = re.compile(r"unsubscribe[:\s]+([A-Za-z0-9_\-]{16,})", re.IGNORECASE)


def decode(value) -> str:
    """Decode a header, repairing raw 8-bit bytes that were not RFC 2047 encoded.

    Well-behaved clients encode non-ASCII headers, but some send raw UTF-8 (or legacy
    Korean) bytes. The email package labels those ``unknown-8bit`` and decodes them
    lossily, which would turn a "수신거부" subject into replacement characters and make
    us miss an unsubscribe request. Decoding the original bytes ourselves avoids that.
    """
    if not value:
        return ""
    try:
        parts = decode_header(value)
    except Exception:
        return str(value)

    out = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            candidates = []
            if charset and charset.lower() not in ("unknown-8bit", "raw-unicode-escape"):
                candidates.append(charset)
            candidates += ["utf-8", "cp949", "latin-1"]
            for candidate in candidates:
                try:
                    out.append(chunk.decode(candidate))
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
            else:
                out.append(chunk.decode("utf-8", "replace"))
        else:
            text = str(chunk)
            if any("\udc80" <= ch <= "\udcff" for ch in text):
                try:
                    text = text.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
                except (UnicodeDecodeError, UnicodeEncodeError):
                    pass
            out.append(text)
    return "".join(out)


def body_text(message) -> str:
    """Best-effort plain text of the message, first 4 KB."""
    parts = []
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                try:
                    parts.append(part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace"))
                except Exception:
                    continue
    else:
        try:
            parts.append(message.get_payload(decode=True).decode(message.get_content_charset() or "utf-8", "replace"))
        except Exception:
            pass
    return " ".join(parts)[:4000]


def is_automated(message) -> bool:
    for header, test in LOOP_HEADERS.items():
        value = message.get(header)
        if value and test(str(value)):
            return True
    sender = parseaddr(message.get("From", ""))[1].lower()
    return not subs.is_valid(sender)


def classify(subject: str, body: str) -> str:
    """Decide what the sender wants. Unsubscribe always wins over subscribe."""
    haystack = f"{subject}\n{body}".lower()
    # Only look at the opening of the body so a quoted footer does not flip the intent.
    head = haystack[:600]
    if any(word in subject.lower() for word in UNSUBSCRIBE_WORDS) or any(word in head for word in UNSUBSCRIBE_WORDS):
        return "unsubscribe"
    if any(word in subject.lower() for word in SUBSCRIBE_WORDS) or any(word in head for word in SUBSCRIBE_WORDS):
        return "subscribe"
    # They wrote to the subscription address without a keyword: treat as a join request.
    return "subscribe"


def imap_config() -> dict:
    server = os.environ.get("IMAP_SERVER", "").strip()
    if not server:
        raise mailer.MailError("IMAP_SERVER is not set; cannot read subscription requests.")
    return {
        "server": server,
        "port": int(os.environ.get("IMAP_PORT", "993") or 993),
        "username": os.environ.get("IMAP_USERNAME", "").strip() or os.environ.get("SMTP_USERNAME", "").strip(),
        "password": os.environ.get("IMAP_PASSWORD", "").strip() or os.environ.get("SMTP_PASSWORD", "").strip(),
        "folder": os.environ.get("IMAP_FOLDER", "INBOX").strip() or "INBOX",
    }


CONFIRM_SUBSCRIBE = """\uad6c\ub3c5\uc774 \ub4f1\ub85d\ub418\uc5c8\uc2b5\ub2c8\ub2e4.

\uc774\uc81c Azure \uc81c\ud488 \uc5c5\ub370\uc774\ud2b8 \ub2e4\uc774\uc81c\uc2a4\ud2b8\uac00 \ubc1c\ud589\ub420 \ub54c\ub9c8\ub2e4 \uc774 \uc8fc\uc18c\ub85c \ubcf4\ub0b4\ub4dc\ub9bd\ub2c8\ub2e4.

\uc804\uccb4 \uc544\uce74\uc774\ube0c\uc640 \ud544\ud130: {site}

\uc218\uc2e0\uc744 \uba48\ucd94\ub824\uba74 \uc774 \uba54\uc77c\uc5d0 "unsubscribe" \ub77c\uace0 \ud68c\uc2e0\ud558\uc2dc\uac70\ub098,
\uc544\ub798 \uc8fc\uc18c\ub85c \uc81c\ubaa9\uc744 unsubscribe \ub85c \ud558\uc5ec \uba54\uc77c\uc744 \ubcf4\ub0b4\uc8fc\uc138\uc694.
{address}
"""

CONFIRM_ALREADY = """\uc774\ubbf8 \uad6c\ub3c5 \uc911\uc785\ub2c8\ub2e4.

\ucd94\uac00 \ub4f1\ub85d \uc5c6\uc774 \uae30\uc874 \uad6c\ub3c5\uc774 \uc720\uc9c0\ub429\ub2c8\ub2e4. \ub2e4\uc74c \ubc1c\ud589 \ubd84\ubd80\ud130 \uacc4\uc18d \ubc1b\uc544\ubcf4\uc2e4 \uc218 \uc788\uc2b5\ub2c8\ub2e4.

\uc804\uccb4 \uc544\uce74\uc774\ube0c: {site}
"""

CONFIRM_UNSUBSCRIBE = """\uc218\uc2e0\uc774 \ud574\uc9c0\ub418\uc5c8\uc2b5\ub2c8\ub2e4.

\uc55e\uc73c\ub85c\ub294 \ub2e4\uc774\uc81c\uc2a4\ud2b8\ub97c \ubcf4\ub0b4\ub4dc\ub9ac\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.
\ub2e4\uc2dc \ubc1b\uc544\ubcf4\uc2dc\ub824\uba74 \uc81c\ubaa9\uc744 subscribe \ub85c \ud558\uc5ec \uba54\uc77c\uc744 \ubcf4\ub0b4\uc8fc\uc138\uc694.

\uc6f9\uc5d0\uc11c\ub294 \uacc4\uc18d \ubcf4\uc2e4 \uc218 \uc788\uc2b5\ub2c8\ub2e4: {site}
"""


def confirmation(kind: str, cfg: dict, address: str) -> tuple[str, str]:
    site = str(cfg.get("site_url") or "").rstrip("/")
    if kind == "created" or kind == "reactivated":
        return "\uad6c\ub3c5 \ub4f1\ub85d \uc644\ub8cc | Azure Updates Digest", CONFIRM_SUBSCRIBE.format(site=site, address=address)
    if kind == "already-active":
        return "\uc774\ubbf8 \uad6c\ub3c5 \uc911\uc785\ub2c8\ub2e4 | Azure Updates Digest", CONFIRM_ALREADY.format(site=site)
    return "\uc218\uc2e0 \ud574\uc9c0 \uc644\ub8cc | Azure Updates Digest", CONFIRM_UNSUBSCRIBE.format(site=site)


def main() -> int:
    parser = argparse.ArgumentParser(description="Process subscription mail over IMAP.")
    parser.add_argument("--dry-run", action="store_true", help="Report intents without changing the store or replying.")
    parser.add_argument("--limit", type=int, default=200, help="Maximum messages to process in one run.")
    parser.add_argument("--all", action="store_true", help="Scan every message, not only unread ones.")
    args = parser.parse_args()

    cfg = load_config()
    imap = imap_config()
    if not imap["username"] or not imap["password"]:
        print("IMAP credentials are missing; nothing to do.", file=sys.stderr)
        set_action_output("processed", "0")
        return 0

    store = subs.load_store()
    smtp_cfg = None if args.dry_run else mailer.smtp_config()

    client = imaplib.IMAP4_SSL(imap["server"], imap["port"])
    counts = {"subscribed": 0, "unsubscribed": 0, "skipped": 0, "processed": 0}
    replied: set[str] = set()

    try:
        client.login(imap["username"], imap["password"])
        client.select(imap["folder"])
        status, data = client.search(None, "ALL" if args.all else "UNSEEN")
        if status != "OK":
            raise mailer.MailError(f"IMAP search failed: {status}")
        ids = data[0].split()[: args.limit]
        print(f"{len(ids)} message(s) to inspect in {imap['folder']}.", file=sys.stderr)

        for msg_id in ids:
            status, payload = client.fetch(msg_id, "(RFC822)")
            if status != "OK" or not payload or not isinstance(payload[0], tuple):
                continue
            message = email.message_from_bytes(payload[0][1])
            sender = subs.normalise(parseaddr(message.get("From", ""))[1])
            subject = decode(message.get("Subject"))

            if is_automated(message):
                counts["skipped"] += 1
                print(f"  skip (automated/invalid): {subs.mask(sender)} | {subject[:50]}", file=sys.stderr)
                if not args.dry_run:
                    client.store(msg_id, "+FLAGS", "\\Seen")
                continue

            text = body_text(message)
            intent = classify(subject, text)
            token_match = TOKEN_RE.search(f"{subject}\n{text}")
            counts["processed"] += 1

            if args.dry_run:
                print(f"  {intent:12} {subs.mask(sender)} | {subject[:60]}", file=sys.stderr)
                continue

            if intent == "unsubscribe":
                outcome, _ = subs.unsubscribe(
                    store,
                    email=sender,
                    token=token_match.group(1) if token_match else None,
                )
                if outcome == "not-found":
                    outcome, _ = subs.unsubscribe(store, email=sender)
                counts["unsubscribed"] += 1 if outcome == "unsubscribed" else 0
            else:
                outcome, _ = subs.subscribe(store, sender, source="email")
                counts["subscribed"] += 1 if outcome in ("created", "reactivated") else 0

            print(f"  {outcome:20} {subs.mask(sender)} | {subject[:50]}", file=sys.stderr)

            # One reply per address per run, so a burst of mail cannot become a loop.
            if sender not in replied:
                replied.add(sender)
                subject_line, text_body = confirmation(outcome, cfg, smtp_cfg["from_addr"])
                try:
                    mailer.send_one(smtp_cfg, sender, subject_line, text_body)
                except mailer.MailError as error:
                    print(f"  ! confirmation failed for {subs.mask(sender)}: {error}", file=sys.stderr)

            client.store(msg_id, "+FLAGS", "\\Seen")

        if not args.dry_run and (counts["subscribed"] or counts["unsubscribed"]):
            subs.save_store(store)
    finally:
        try:
            client.close()
        except Exception:
            pass
        try:
            client.logout()
        except Exception:
            pass

    active = len(subs.active_records(store))
    print(f"Done: +{counts['subscribed']} subscribed, -{counts['unsubscribed']} unsubscribed, "
          f"{counts['skipped']} skipped. {active} active subscriber(s).", file=sys.stderr)
    set_action_output("subscribed", str(counts["subscribed"]))
    set_action_output("unsubscribed", str(counts["unsubscribed"]))
    set_action_output("processed", str(counts["processed"]))
    set_action_output("active", str(active))
    set_action_output("changed", "true" if counts["subscribed"] or counts["unsubscribed"] else "false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


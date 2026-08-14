"""End-to-end check of the subscription pipeline.

Runs a real SMTP server on localhost and a stub IMAP server that replays canned
messages through the production code paths in mailbox_sync and send_digest.
"""

import asyncio
import email
import json
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from aiosmtpd.controller import Controller
from cryptography.fernet import Fernet

os.environ["SUBSCRIBER_KEY"] = Fernet.generate_key().decode()
os.environ["SMTP_SERVER"] = "127.0.0.1"
os.environ["SMTP_PORT"] = "8025"
os.environ["SMTP_SECURITY"] = "none"
os.environ["SMTP_FROM"] = "digest@azupdates.test"
os.environ["SMTP_FROM_NAME"] = "Azure Updates Digest"
os.environ["IMAP_SERVER"] = "imap.test"
os.environ["IMAP_USERNAME"] = "digest@azupdates.test"
os.environ["IMAP_PASSWORD"] = "secret"

INBOX = []


class Sink:
    async def handle_DATA(self, server, session, envelope):
        INBOX.append({
            "from": envelope.mail_from,
            "to": list(envelope.rcpt_tos),
            "raw": envelope.content.decode("utf-8", "replace"),
        })
        return "250 OK"


def raw_message(sender, subject, body, extra="", encode_subject=False):
    if encode_subject:
        from email.header import Header
        subject = Header(subject, "utf-8").encode()
    return (
        f"From: {sender}\r\nTo: digest@azupdates.test\r\n"
        f"Subject: {subject}\r\n{extra}"
        f"MIME-Version: 1.0\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{body}\r\n"
    ).encode("utf-8")


class FakeIMAP:
    """Implements the subset of imaplib.IMAP4_SSL that mailbox_sync uses."""
    messages = []

    def __init__(self, host, port):
        self.flags = {}

    def login(self, u, p): return ("OK", [b""])
    def select(self, folder): return ("OK", [b"1"])
    def search(self, charset, *criteria):
        return ("OK", [b" ".join(str(i + 1).encode() for i in range(len(self.messages)))])
    def fetch(self, msg_id, spec):
        return ("OK", [(b"1 (RFC822)", self.messages[int(msg_id) - 1])])
    def store(self, msg_id, cmd, flags):
        self.flags.setdefault(int(msg_id), []).append(flags)
        return ("OK", [b""])
    def close(self): pass
    def logout(self): pass


def section(title):
    print("\n" + "=" * 72 + f"\n{title}\n" + "=" * 72)


def main():
    controller = Controller(Sink(), hostname="127.0.0.1", port=8025)
    controller.start()
    time.sleep(0.5)

    import imaplib
    import subscribers as subs
    import mailbox_sync

    store_path = Path(subs.SUBSCRIBERS_PATH)
    backup = store_path.read_bytes() if store_path.exists() else None
    if store_path.exists():
        store_path.unlink()

    try:
        section("1. Inbox processing: subscribe, duplicate, unsubscribe, loop protection")
        FakeIMAP.messages = [
            raw_message("Jane Kim <jane.kim@contoso.com>", "subscribe", "please add me"),
            raw_message("PARK <park@fabrikam.co.kr>", "\uad6c\ub3c5 \uc2e0\uccad", "\uad6c\ub3c5\ud558\uace0 \uc2f6\uc2b5\ub2c8\ub2e4"),
            raw_message("jane.kim@contoso.com", "subscribe", "again"),
            raw_message("bot@fabrikam.com", "Out of office", "auto", extra="Auto-Submitted: auto-replied\r\n"),
            raw_message("noreply@vendor.com", "subscribe", "spam"),
            raw_message("list@news.com", "subscribe", "x", extra="List-Id: <news.list>\r\n"),
            raw_message("someone@northwind.com", "hello", "no keyword at all"),
        ]
        imaplib.IMAP4_SSL = FakeIMAP
        mailbox_sync.main()

        store = subs.load_store()
        actives = sorted(r["email"] for r in subs.active_recipients(store))
        print("\nactive after inbox run:", actives)
        assert actives == ["jane.kim@contoso.com", "park@fabrikam.co.kr", "someone@northwind.com"], actives
        confirmations = [m for m in INBOX]
        print("confirmation mails:", len(confirmations), "->", [m["to"][0] for m in confirmations])
        assert len(confirmations) == 3, "one confirmation per unique human sender"

        section("2. Unsubscribe by reply and by token")
        token = [r for r in subs.active_records(store) if r["masked"].startswith("ja")][0]["token"]
        INBOX.clear()
        FakeIMAP.messages = [
            raw_message("park@fabrikam.co.kr", "\uc218\uc2e0\uac70\ubd80", "\uadf8\ub9cc \ubc1b\uaca0\uc2b5\ub2c8\ub2e4"),
            raw_message("jane.kim@contoso.com", f"unsubscribe {token}", "one click"),
        ]
        mailbox_sync.main()
        store = subs.load_store()
        actives = sorted(r["email"] for r in subs.active_recipients(store))
        print("active after unsubscribes (raw 8-bit header):", actives)
        assert actives == ["someone@northwind.com"], actives

        print("\n-- same request with an RFC 2047 encoded header --")
        subs.subscribe(store, "park@fabrikam.co.kr")
        subs.save_store(store)
        FakeIMAP.messages = [
            raw_message("park@fabrikam.co.kr", "\uc218\uc2e0\uac70\ubd80", "\ud574\uc9c0\ud569\ub2c8\ub2e4", encode_subject=True),
        ]
        mailbox_sync.main()
        store = subs.load_store()
        actives = sorted(r["email"] for r in subs.active_recipients(store))
        print("active after encoded-header unsubscribe:", actives)
        assert actives == ["someone@northwind.com"], actives

        section("3. Digest send: one personalised message per subscriber")
        subs.subscribe(store, "ops@tailwind.com", source="email")
        rec = subs.find(store, "ops@tailwind.com")
        rec["prefs"] = {"stages": ["ga"]}
        subs.save_store(store)

        INBOX.clear()
        import send_digest
        sys.argv = ["send_digest.py", "--delay", "0"]
        send_digest.main()

        print("\ndigest messages delivered:", len(INBOX))
        for m in INBOX:
            msg = email.message_from_string(m["raw"])
            body_html = ""
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    body_html = part.get_payload(decode=True).decode("utf-8", "replace")
            print(f"  to={m['to'][0]:24} subject={msg['Subject'][:44]}")
            print(f"     List-Unsubscribe={msg['List-Unsubscribe'][:60]}")
            print(f"     one-click={msg['List-Unsubscribe-Post']} | footer={'\uc218\uc2e0 \ud574\uc9c0' in body_html}")
            assert msg["To"] == m["to"][0]
            assert "List-Unsubscribe" in msg
        assert len(INBOX) == 2, INBOX
        addrs = {m["to"][0] for m in INBOX}
        assert addrs == {"someone@northwind.com", "ops@tailwind.com"}, addrs

        section("4. Privacy: recipients isolated, no clear-text at rest")
        for m in INBOX:
            others = addrs - {m["to"][0]}
            assert not any(o in m["raw"] for o in others), "recipient leaked into another message"
        raw = store_path.read_text(encoding="utf-8")
        leaked = [a for a in ["jane.kim@contoso.com", "park@fabrikam.co.kr", "ops@tailwind.com"] if a in raw]
        print("recipients isolated: True")
        print("clear-text addresses in data/subscribers.json:", leaked or "none")
        assert not leaked

        section("RESULT: all subscription checks passed")
    finally:
        controller.stop()
        if backup is not None:
            store_path.write_bytes(backup)
        elif store_path.exists():
            store_path.unlink()


if __name__ == "__main__":
    main()

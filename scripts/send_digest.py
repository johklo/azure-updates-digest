"""Send the daily digest to everyone who subscribed through the site.

The signup form posts to a small Azure App Service app, which keeps the confirmed
subscriber list and hands it back here over an authenticated endpoint. Delivery goes
through Azure Communication Services, so no SMTP password is needed anywhere.

Each subscriber gets their own message carrying their own unsubscribe link.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from build_digest import render_email_html, render_email_text
from common import LATEST_PATH, load_config, load_enrichment, read_json, set_action_output, utcnow

FOOTER_TEXT = """

--
\uc774 \uba54\uc77c\uc740 \uad6c\ub3c5 \uc2e0\uccad\ud558\uc2e0 \uc8fc\uc18c\ub85c \ubc1c\uc1a1\ub418\uc5c8\uc2b5\ub2c8\ub2e4.
\uc218\uc2e0 \ud574\uc9c0: {unsubscribe}
\uc804\uccb4 \ubcf4\uae30: {site}
"""

FOOTER_HTML = """
<div style="margin-top:22px;padding-top:14px;border-top:1px solid #e1e4e8;
font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:12px;color:#57606a;">
\uc774 \uba54\uc77c\uc740 \uad6c\ub3c5 \uc2e0\uccad\ud558\uc2e0 \uc8fc\uc18c\ub85c \ubc1c\uc1a1\ub418\uc5c8\uc2b5\ub2c8\ub2e4.
<a href="{unsubscribe}" style="color:#0078d4;">\uc218\uc2e0 \ud574\uc9c0</a>
&middot; <a href="{site}" style="color:#0078d4;">\uc6f9\uc5d0\uc11c \ubcf4\uae30</a>
</div>
"""


def mask(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:2]}***@{domain}" if domain else "***"


def fetch_subscribers(base: str, api_key: str) -> list:
    """Read the confirmed subscriber list from the subscription service."""
    url = base.rstrip("/") + "/api/subscribers"
    request = urllib.request.Request(url, headers={"X-Api-Key": api_key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Subscriber service returned {error.code}: {error.reason}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach the subscriber service: {error.reason}") from error
    if not payload.get("ok"):
        raise RuntimeError("Subscriber service rejected the request.")
    return payload.get("subscribers", [])


def acs_client():
    from azure.communication.email import EmailClient

    connection = os.environ.get("ACS_CONNECTION_STRING", "").strip()
    if not connection:
        raise RuntimeError("ACS_CONNECTION_STRING is not set.")
    return EmailClient.from_connection_string(connection)


def main() -> int:
    parser = argparse.ArgumentParser(description="Send the digest to confirmed subscribers.")
    parser.add_argument("--input", default=str(LATEST_PATH))
    parser.add_argument("--date", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Render and report without sending.")
    parser.add_argument("--to", default=None, help="Send only to this address, for a test run.")
    parser.add_argument("--delay", type=float, default=0.3)
    args = parser.parse_args()

    cfg = load_config()
    payload = read_json(args.input, {"items": []})
    enrichment = load_enrichment()
    date_str = args.date or utcnow().strftime("%Y-%m-%d")
    items = payload.get("items", [])

    if not items and not cfg.get("email", {}).get("send_when_empty", False):
        print("No updates in this digest; nothing to send.", file=sys.stderr)
        set_action_output("sent", "0")
        return 0

    base = os.environ.get("SUBSCRIBE_API_BASE", "").strip()
    api_key = os.environ.get("SUBSCRIBE_API_KEY", "").strip()
    sender = os.environ.get("ACS_SENDER", "").strip()
    if not sender:
        raise RuntimeError("ACS_SENDER is not set.")

    if args.to:
        recipients = [{"email": args.to, "unsubscribe_url": base.rstrip("/") + "/api/unsubscribe"}]
    else:
        if not base or not api_key:
            raise RuntimeError("SUBSCRIBE_API_BASE and SUBSCRIBE_API_KEY must be set.")
        recipients = fetch_subscribers(base, api_key)

    if not recipients:
        print("No confirmed subscribers yet.", file=sys.stderr)
        set_action_output("sent", "0")
        return 0

    prefix = cfg.get("email", {}).get("subject_prefix", "[Azure Updates]")
    site = str(cfg.get("site_url") or "").rstrip("/")
    subject = f"{prefix} {date_str} - {len(items)} update(s)"
    html_body = render_email_html(cfg, payload, date_str, enrichment)
    text_body = render_email_text(cfg, payload, date_str, enrichment)

    print(f"{len(recipients)} subscriber(s); digest has {len(items)} update(s).", file=sys.stderr)
    if args.dry_run:
        for entry in recipients:
            print(f"  would send to {mask(entry['email'])}: {subject}", file=sys.stderr)
        set_action_output("sent", str(len(recipients)))
        return 0

    client = acs_client()
    sent = failed = 0
    for entry in recipients:
        address = entry["email"]
        unsubscribe = entry.get("unsubscribe_url") or site
        message = {
            "senderAddress": sender,
            "recipients": {"to": [{"address": address}]},
            "content": {
                "subject": subject,
                "plainText": text_body + FOOTER_TEXT.format(unsubscribe=unsubscribe, site=site),
                "html": html_body + FOOTER_HTML.format(unsubscribe=unsubscribe, site=site),
            },
            "headers": {"List-Unsubscribe": f"<{unsubscribe}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"},
        }
        try:
            result = client.begin_send(message).result()
            if str(result.get("status", "")).lower() not in ("succeeded", "running"):
                raise RuntimeError(f"status {result.get('status')}")
            sent += 1
            print(f"  sent {mask(address)}", file=sys.stderr)
        except Exception as error:
            failed += 1
            print(f"  ! failed {mask(address)}: {error}", file=sys.stderr)
        if args.delay:
            time.sleep(args.delay)

    print(f"Sent {sent}, failed {failed}.", file=sys.stderr)
    set_action_output("sent", str(sent))
    set_action_output("failed", str(failed))
    return 1 if failed and not sent else 0


if __name__ == "__main__":
    raise SystemExit(main())

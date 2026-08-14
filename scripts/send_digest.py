"""Send the digest to every active subscriber, one personalised message each.

Recipients are never exposed to one another: each subscriber gets their own message with
their own unsubscribe token in the footer and in the List-Unsubscribe header, so mail
clients can offer a native unsubscribe button.
"""

from __future__ import annotations

import argparse
import sys
import time

import mailer
import subscribers as subs
from build_digest import digest_title, render_email_html, render_email_text
from common import LATEST_PATH, load_config, load_enrichment, read_json, set_action_output, utcnow

FOOTER_TEXT = """
--
\uc218\uc2e0\uc744 \uc6d0\ud558\uc9c0 \uc54a\uc73c\uc2dc\uba74 \uc774 \uba54\uc77c\uc5d0 \uadf8\ub300\ub85c \ud68c\uc2e0\ud558\uc138\uc694 (\uc81c\ubaa9: unsubscribe).
\ub610\ub294 {mailto}
"""

FOOTER_HTML = """
<div style="margin-top:22px;padding-top:14px;border-top:1px solid #e1e4e8;
font-family:Segoe UI,Helvetica,Arial,sans-serif;font-size:12px;color:#57606a;">
\uc774 \uba54\uc77c\uc740 \uad6c\ub3c5 \uc2e0\uccad\ud558\uc2e0 \uc8fc\uc18c\ub85c \ubc1c\uc1a1\ub418\uc5c8\uc2b5\ub2c8\ub2e4.
<a href="{mailto}" style="color:#0078d4;">\uc218\uc2e0 \ud574\uc9c0</a>
&middot; <a href="{site}" style="color:#0078d4;">\uc6f9\uc5d0\uc11c \ubcf4\uae30</a>
</div>
"""


def unsubscribe_mailto(from_addr: str, token: str) -> str:
    return f"mailto:{from_addr}?subject=unsubscribe%20{token}"


def filtered_payload(payload: dict, prefs: dict) -> dict:
    """Apply a subscriber's category and stage preferences to the digest payload."""
    items = payload.get("items", [])
    categories = {c.lower() for c in (prefs.get("categories") or [])}
    stages = {s.lower() for s in (prefs.get("stages") or [])}
    if not categories and not stages:
        return payload

    from common import release_stage

    kept = []
    for item in items:
        item_categories = {c.lower() for c in (item.get("productCategories") or [])}
        if categories and not (item_categories & categories):
            continue
        if stages and release_stage(item).lower() not in stages:
            continue
        kept.append(item)
    return dict(payload, items=kept, count=len(kept))


def main() -> int:
    parser = argparse.ArgumentParser(description="Send the digest to all active subscribers.")
    parser.add_argument("--input", default=str(LATEST_PATH))
    parser.add_argument("--date", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Render and report without sending.")
    parser.add_argument("--limit", type=int, default=0, help="Send to at most N subscribers.")
    parser.add_argument("--delay", type=float, default=0.4, help="Seconds to wait between messages.")
    parser.add_argument("--to", default=None, help="Send only to this address (test send).")
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

    store = subs.load_store()
    recipients = subs.active_recipients(store)
    if args.to:
        recipients = [{"email": args.to, "record": {"token": "test", "masked": subs.mask(args.to), "prefs": {}}}]
    if args.limit:
        recipients = recipients[: args.limit]

    if not recipients:
        print("No active subscribers.", file=sys.stderr)
        set_action_output("sent", "0")
        return 0

    prefix = cfg.get("email", {}).get("subject_prefix", "[Azure Updates]")
    site = str(cfg.get("site_url") or "").rstrip("/")
    smtp_cfg = mailer.smtp_config() if not args.dry_run else {"from_addr": "digest@example.com", "from_name": "test"}

    print(f"{len(recipients)} active subscriber(s); digest has {len(items)} update(s).", file=sys.stderr)

    client = None if args.dry_run else mailer.connect(smtp_cfg)
    sent = failed = skipped = 0
    try:
        for entry in recipients:
            address = entry["email"]
            record = entry["record"]
            personal = filtered_payload(payload, record.get("prefs") or {})
            if not personal.get("items"):
                skipped += 1
                print(f"  skip {record.get('masked')}: no updates match their filters", file=sys.stderr)
                continue

            mailto = unsubscribe_mailto(smtp_cfg["from_addr"], record.get("token", ""))
            subject = f"{prefix} {date_str} - {len(personal['items'])} update(s)"
            html = render_email_html(cfg, personal, date_str, enrichment) + FOOTER_HTML.format(mailto=mailto, site=site)
            text = render_email_text(cfg, personal, date_str, enrichment) + FOOTER_TEXT.format(mailto=mailto)

            if args.dry_run:
                print(f"  would send to {record.get('masked')}: {subject}", file=sys.stderr)
                sent += 1
                continue

            message = mailer.build_message(
                smtp_cfg, address, subject, text, html,
                headers={
                    "List-Unsubscribe": f"<{mailto}>",
                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                    "List-Id": f"Azure Updates Digest <digest.{smtp_cfg['from_addr'].split('@')[-1]}>",
                },
            )
            try:
                mailer.send(client, message)
                record["sent_count"] = int(record.get("sent_count", 0)) + 1
                record["last_sent_at"] = utcnow().isoformat()
                sent += 1
                print(f"  sent {record.get('masked')} ({len(personal['items'])} updates)", file=sys.stderr)
            except Exception as error:
                failed += 1
                print(f"  ! failed {record.get('masked')}: {error}", file=sys.stderr)
                # A dropped session should not lose the rest of the run.
                try:
                    client = mailer.connect(smtp_cfg)
                except mailer.MailError:
                    break
            if args.delay:
                time.sleep(args.delay)
    finally:
        if client is not None:
            try:
                client.quit()
            except Exception:
                pass

    if not args.dry_run and not args.to:
        subs.save_store(store)

    print(f"Sent {sent}, skipped {skipped}, failed {failed}.", file=sys.stderr)
    set_action_output("sent", str(sent))
    set_action_output("failed", str(failed))
    return 1 if failed and not sent else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Fetch Azure product updates from the official Microsoft release communications API.

The API behind https://azure.microsoft.com/en-us/updates returns structured records
including productCategories, products, tags and availability rings, so no HTML
scraping is required.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from common import (
    ARCHIVE_PATH,
    LATEST_PATH,
    STATE_PATH,
    item_date,
    load_config,
    matches_filters,
    read_json,
    set_action_output,
    sort_items,
    utcnow,
    write_json,
)

USER_AGENT = "azure-updates-digest/1.0 (+https://github.com)"


def fetch_page(api: str, top: int, skip: int, retries: int = 4) -> list:
    query = urllib.parse.urlencode({"$top": top, "$skip": skip, "$orderby": "created desc"})
    url = f"{api}?{query}"
    last_error = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return payload.get("value", [])
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def fetch_updates(cfg: dict, days: int) -> list:
    api = cfg["source_api"]
    page_size = int(cfg.get("page_size", 100))
    max_pages = int(cfg.get("max_pages", 20))
    cutoff = utcnow() - timedelta(days=days)

    collected: dict[str, dict] = {}
    for page in range(max_pages):
        items = fetch_page(api, page_size, page * page_size)
        if not items:
            break

        reached_cutoff = False
        for item in items:
            created = item_date(item)
            if created is None:
                continue
            if created < cutoff:
                reached_cutoff = True
                continue
            collected[str(item.get("id"))] = item

        print(f"  page {page + 1}: {len(items)} records, {len(collected)} within window", file=sys.stderr)
        if reached_cutoff or len(items) < page_size:
            break

    return sort_items(collected.values())


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch recent Azure product updates.")
    parser.add_argument("--days", type=int, default=None, help="Lookback window in days (default: config lookback_days).")
    parser.add_argument("--include-seen", action="store_true", help="Do not filter out updates already published in a previous digest.")
    parser.add_argument("--dry-run", action="store_true", help="Do not write data/state.json or data/archive.json.")
    args = parser.parse_args()

    cfg = load_config()
    days = args.days if args.days is not None else int(cfg.get("lookback_days", 7))

    print(f"Fetching Azure updates from the last {days} day(s)...", file=sys.stderr)
    fetched = fetch_updates(cfg, days)
    filtered = [item for item in fetched if matches_filters(item, cfg)]

    state = read_json(STATE_PATH, {"seen_ids": [], "last_run": None})
    seen = set(state.get("seen_ids", []))
    new_items = filtered if args.include_seen else [i for i in filtered if str(i.get("id")) not in seen]

    now = utcnow()
    window_start = now - timedelta(days=days)
    payload = {
        "generated_at": now.isoformat(),
        "window_start": window_start.isoformat(),
        "window_end": now.isoformat(),
        "window_days": days,
        "fetched_count": len(fetched),
        "matched_count": len(filtered),
        "count": len(new_items),
        "items": new_items,
    }
    write_json(LATEST_PATH, payload)

    print(
        f"Fetched {len(fetched)} update(s); {len(filtered)} matched filters; {len(new_items)} new.",
        file=sys.stderr,
    )

    if not args.dry_run:
        archive = read_json(ARCHIVE_PATH, {"items": []})
        merged = {str(i.get("id")): i for i in archive.get("items", [])}
        for item in filtered:
            merged[str(item.get("id"))] = item
        archive_items = sort_items(merged.values())[: int(cfg.get("archive_limit", 3000))]
        write_json(ARCHIVE_PATH, {"updated_at": now.isoformat(), "count": len(archive_items), "items": archive_items})

        seen.update(str(i.get("id")) for i in filtered)
        write_json(STATE_PATH, {"last_run": now.isoformat(), "seen_ids": sorted(seen)})

    set_action_output("new_count", str(len(new_items)))
    set_action_output("has_updates", "true" if new_items else "false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Enrich Azure updates by reading their linked documentation and summarizing it.

Results are cached in data/enrichment.json keyed by update id, so each run only
processes updates that have not been summarized yet.
"""

from __future__ import annotations

import argparse
import sys
import time

from common import (
    ARCHIVE_PATH,
    DATA_DIR,
    LATEST_PATH,
    read_json,
    set_action_output,
    sort_items,
    strip_html,
    utcnow,
    write_json,
)
from summarizer import extract_links, extractive_summary, fetch_document, llm_config, llm_summary

ENRICHMENT_PATH = DATA_DIR / "enrichment.json"


def enrich_item(item: dict, cfg_llm: dict | None, fetch_docs: bool = True) -> dict:
    title = str(item.get("title", "")).strip()
    update_text = strip_html(item.get("description", ""))
    links = extract_links(item.get("description", ""))

    doc = None
    if fetch_docs:
        for url in links[:3]:
            doc = fetch_document(url)
            if doc and (doc.get("blocks") or doc.get("meta_description")):
                break
            doc = None

    summary, points = "", []
    source = "extractive"
    if cfg_llm:
        result = llm_summary(cfg_llm, title, update_text, doc)
        if result and result[1]:
            summary, points = result
            source = "llm"
    if not points:
        summary, points = extractive_summary(update_text, doc)

    return {
        "summary": summary,
        "key_points": points,
        "doc_url": doc.get("url") if doc else (links[0] if links else ""),
        "doc_title": doc.get("title") if doc else "",
        "doc_read": bool(doc),
        "links": links[:5],
        "source": source,
        "updated_at": utcnow().isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize the documentation behind each Azure update.")
    parser.add_argument("--input", default="archive", choices=["archive", "latest"], help="Which dataset to enrich.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of updates to process (0 = no limit).")
    parser.add_argument("--refresh", action="store_true", help="Re-summarize updates that already have an entry.")
    parser.add_argument("--sleep", type=float, default=0.6, help="Delay between documentation fetches, in seconds.")
    parser.add_argument("--no-fetch", action="store_true", help="Summarize without opening documentation links.")
    args = parser.parse_args()

    path = ARCHIVE_PATH if args.input == "archive" else LATEST_PATH
    items = sort_items(read_json(path, {"items": []}).get("items", []))
    cache = read_json(ENRICHMENT_PATH, {})
    if not isinstance(cache, dict):
        cache = {}

    cfg_llm = llm_config()
    print(f"Summarizer backend: {'LLM' if cfg_llm else 'extractive (no LLM credentials configured)'}", file=sys.stderr)

    pending = [i for i in items if args.refresh or str(i.get("id")) not in cache]
    if args.limit:
        pending = pending[: args.limit]
    print(f"{len(items)} update(s) in {args.input}; {len(pending)} to summarize.", file=sys.stderr)

    processed = 0
    docs_read = 0
    for index, item in enumerate(pending, start=1):
        update_id = str(item.get("id"))
        entry = enrich_item(item, cfg_llm, fetch_docs=not args.no_fetch)
        cache[update_id] = entry
        processed += 1
        docs_read += 1 if entry["doc_read"] else 0
        marker = "doc" if entry["doc_read"] else "---"
        print(f"  [{index}/{len(pending)}] {marker} {str(item.get('title'))[:70]}", file=sys.stderr)
        if processed % 25 == 0:
            write_json(ENRICHMENT_PATH, cache)
        if not args.no_fetch and args.sleep:
            time.sleep(args.sleep)

    write_json(ENRICHMENT_PATH, cache)
    print(f"Summarized {processed} update(s); documentation read for {docs_read}.", file=sys.stderr)
    set_action_output("enriched_count", str(processed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

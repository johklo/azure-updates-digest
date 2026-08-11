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
from summarizer import (
    extract_links,
    extractive_summary,
    fetch_document,
    llm_config,
    llm_summary,
    llm_translate,
)

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


def needs_translation(entry: dict) -> bool:
    """True when an entry has English content but no usable Korean counterpart."""
    if not isinstance(entry, dict):
        return False
    if not (entry.get("summary") or entry.get("key_points")):
        return False
    return not (entry.get("summary_ko") or entry.get("title_ko"))


def translate_entry(item: dict, entry: dict, cfg_llm: dict) -> bool:
    """Add Korean fields to a cached entry in place. Returns True when it changed."""
    result = llm_translate(
        cfg_llm,
        str(item.get("title", "")).strip(),
        entry.get("summary") or "",
        entry.get("key_points") or [],
    )
    if not result:
        return False
    entry.update(result)
    entry["translated_at"] = utcnow().isoformat()
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize the documentation behind each Azure update.")
    parser.add_argument("--input", default="archive", choices=["archive", "latest"], help="Which dataset to enrich.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of updates to process (0 = no limit).")
    parser.add_argument("--refresh", action="store_true", help="Re-summarize updates that already have an entry.")
    parser.add_argument("--sleep", type=float, default=0.6, help="Delay between documentation fetches, in seconds.")
    parser.add_argument("--no-fetch", action="store_true", help="Summarize without opening documentation links.")
    parser.add_argument(
        "--translate",
        dest="translate",
        action="store_true",
        default=True,
        help="Add Korean translations to entries that do not have one yet (default).",
    )
    parser.add_argument("--no-translate", dest="translate", action="store_false", help="Skip the Korean pass.")
    parser.add_argument(
        "--translate-only",
        action="store_true",
        help="Skip summarization and only backfill Korean translations for cached entries.",
    )
    parser.add_argument(
        "--translate-limit",
        type=int,
        default=0,
        help="Maximum number of updates to translate in this run (0 = no limit).",
    )
    parser.add_argument(
        "--retranslate", action="store_true", help="Re-translate entries that already carry Korean text."
    )
    args = parser.parse_args()

    path = ARCHIVE_PATH if args.input == "archive" else LATEST_PATH
    items = sort_items(read_json(path, {"items": []}).get("items", []))
    cache = read_json(ENRICHMENT_PATH, {})
    if not isinstance(cache, dict):
        cache = {}

    cfg_llm = llm_config()
    print(f"Summarizer backend: {'LLM' if cfg_llm else 'extractive (no LLM credentials configured)'}", file=sys.stderr)

    processed = 0
    docs_read = 0
    if not args.translate_only:
        pending = [i for i in items if args.refresh or str(i.get("id")) not in cache]
        if args.limit:
            pending = pending[: args.limit]
        print(f"{len(items)} update(s) in {args.input}; {len(pending)} to summarize.", file=sys.stderr)

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

    translated = translate_pending(items, cache, cfg_llm, args)

    set_action_output("enriched_count", str(processed))
    set_action_output("translated_count", str(translated))
    return 0


def translate_pending(items, cache: dict, cfg_llm: dict | None, args) -> int:
    """Backfill Korean translations for cached entries that do not have one."""
    if not (args.translate or args.translate_only):
        return 0
    if not cfg_llm:
        print("Korean translation skipped: no LLM credentials configured.", file=sys.stderr)
        return 0

    queue = []
    for item in items:
        entry = cache.get(str(item.get("id")))
        if not isinstance(entry, dict):
            continue
        if args.retranslate:
            if entry.get("summary") or entry.get("key_points"):
                queue.append((item, entry))
        elif needs_translation(entry):
            queue.append((item, entry))
    if args.translate_limit:
        queue = queue[: args.translate_limit]

    if not queue:
        print("Korean translation: nothing pending.", file=sys.stderr)
        return 0

    print(f"Korean translation: {len(queue)} update(s) queued.", file=sys.stderr)
    done = 0
    for index, (item, entry) in enumerate(queue, start=1):
        if translate_entry(item, entry, cfg_llm):
            done += 1
            marker = "ko "
        else:
            marker = "---"
        print(f"  [{index}/{len(queue)}] {marker} {str(item.get('title'))[:70]}", file=sys.stderr)
        if done and done % 25 == 0:
            write_json(ENRICHMENT_PATH, cache)

    write_json(ENRICHMENT_PATH, cache)
    print(f"Translated {done} of {len(queue)} update(s) into Korean.", file=sys.stderr)
    return done


if __name__ == "__main__":
    raise SystemExit(main())

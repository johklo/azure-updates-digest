"""Assemble a sample digest payload from the archive so the mail layout can be judged.

Picks the most recent updates that already have summaries, spreading them across
categories and release stages rather than taking a single day's batch.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from common import ARCHIVE_PATH, enrichment_for, item_date_str, load_enrichment, read_json, utcnow


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a sample payload for a test mail.")
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--per-category", type=int, default=2)
    parser.add_argument("--output", default="build/sample.json")
    args = parser.parse_args()

    archive = read_json(str(ARCHIVE_PATH), {"items": []})
    items = archive.get("items", archive if isinstance(archive, list) else [])
    enrichment = load_enrichment()

    summarized = [i for i in items if enrichment_for(i, enrichment)["summary"]]
    summarized.sort(key=item_date_str, reverse=True)

    chosen: list = []
    seen_per_category: dict[str, int] = {}
    for item in summarized:
        category = (item.get("productCategories") or ["Other"])[0]
        if seen_per_category.get(category, 0) >= args.per_category:
            continue
        seen_per_category[category] = seen_per_category.get(category, 0) + 1
        chosen.append(item)
        if len(chosen) >= args.count:
            break

    payload = {
        "generated_at": utcnow().isoformat(),
        "window_days": 7,
        "items": chosen,
        "sample": True,
    }
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{len(chosen)}건을 {out} 에 담았다. 카테고리 {len(seen_per_category)}종")
    for item in chosen:
        info = enrichment_for(item, enrichment)
        mark = "한글" if info["title_ko"] else "영문"
        print(f"  [{mark}] {item_date_str(item)}  {str(item.get('title'))[:64]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

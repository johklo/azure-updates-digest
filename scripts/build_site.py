"""Generate the static GitHub Pages site from the update archive and digest history."""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
from collections import Counter

from common import (
    ARCHIVE_PATH,
    DIGEST_DIR,
    SITE_DIR,
    group_by_category,
    item_date_str,
    load_config,
    read_json,
    sort_items,
    status_label,
    summarize,
    update_url,
    utcnow,
)

STYLE = """
:root{--bg:#f4f6f8;--card:#fff;--ink:#1b1f23;--muted:#57606a;--brand:#0078d4;--line:#e1e4e8}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 "Segoe UI",Helvetica,Arial,sans-serif}
a{color:var(--brand)}
header{background:linear-gradient(135deg,#0078d4,#004578);color:#fff;padding:36px 20px}
header .wrap{max-width:960px;margin:0 auto}
header h1{margin:0;font-size:26px}
header p{margin:8px 0 0;opacity:.92;font-size:15px}
nav{max-width:960px;margin:0 auto;padding:14px 20px;display:flex;gap:16px;flex-wrap:wrap;font-size:14px}
main{max-width:960px;margin:0 auto;padding:8px 20px 56px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:18px 20px;margin-bottom:16px}
.stats{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 16px;min-width:130px}
.stat b{display:block;font-size:22px;color:var(--brand)}
.stat span{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
h2{font-size:18px;margin:28px 0 10px;padding-bottom:6px;border-bottom:2px solid var(--brand)}
h2 small{color:var(--muted);font-weight:400}
.item{padding:14px 0;border-bottom:1px solid #eef0f2}
.item:last-child{border-bottom:none}
.item a.title{font-weight:600;font-size:15px;text-decoration:none;color:#0b4f9e}
.item a.title:hover{text-decoration:underline}
.meta{margin:6px 0;font-size:12px;color:var(--muted)}
.badge{display:inline-block;background:#eef4fb;color:#0b4f9e;border-radius:10px;padding:2px 9px;margin-right:8px;font-size:11px}
.summary{font-size:13.5px;color:#24292f}
ul.list{list-style:none;padding:0;margin:0}
ul.list li{padding:8px 0;border-bottom:1px solid #eef0f2;font-size:14px}
footer{max-width:960px;margin:0 auto;padding:20px;color:var(--muted);font-size:12px}
"""


def esc(value) -> str:
    return html_lib.escape(str(value or ""), quote=True)


def page(cfg: dict, title: str, body_html: str, depth: int = 0) -> str:
    prefix = "../" * depth
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(cfg.get('site_description'))}">
<link rel="stylesheet" href="{prefix}style.css"></head>
<body>
<header><div class="wrap"><h1>{esc(cfg.get('site_title'))}</h1>
<p>{esc(cfg.get('site_description'))}</p></div></header>
<nav><a href="{prefix}index.html">Latest</a><a href="{prefix}archive.html">Digest archive</a>
<a href="{prefix}categories.html">Categories</a>
<a href="{esc(cfg.get('azure_updates_url'))}">Azure Updates source</a></nav>
<main>{body_html}</main>
<footer>Generated {esc(utcnow().strftime('%Y-%m-%d %H:%M UTC'))} from the official Microsoft Azure release communications feed.</footer>
</body></html>
"""


def render_item(item: dict) -> str:
    products = ", ".join(p for p in (item.get("products") or []) if p)
    summary = summarize(item.get("description", ""), 340)
    product_html = " &middot; " + esc(products) if products else ""
    summary_html = '<div class="summary">' + esc(summary) + "</div>" if summary else ""
    return (
        '<div class="item">'
        f'<a class="title" href="{esc(update_url(item))}">{esc(item.get("title"))}</a>'
        f'<div class="meta"><span class="badge">{esc(status_label(item))}</span>{esc(item_date_str(item))}'
        f"{product_html}</div>"
        f"{summary_html}"
        "</div>"
    )


def render_groups(groups: dict) -> str:
    out = []
    for category, bucket in groups.items():
        out.append(f'<div class="card"><h2>{esc(category)} <small>({len(bucket)})</small></h2>')
        out.extend(render_item(item) for item in bucket)
        out.append("</div>")
    return "\n".join(out)


def digest_meta(path):
    text = path.read_text(encoding="utf-8")
    count = 0
    match = re.search(r"^count:\s*(\d+)\s*$", text, re.MULTILINE)
    if match:
        count = int(match.group(1))
    return {"date": path.stem, "count": count}


def build(cfg: dict, days: int) -> None:
    archive = read_json(ARCHIVE_PATH, {"items": []})
    items = sort_items(archive.get("items", []))

    from common import item_date, utcnow as _now
    from datetime import timedelta

    cutoff = _now() - timedelta(days=days)
    recent = [i for i in items if (item_date(i) or cutoff) >= cutoff]

    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "style.css").write_text(STYLE, encoding="utf-8")
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")

    category_counts = Counter()
    product_counts = Counter()
    for item in items:
        for category in item.get("productCategories") or []:
            category_counts[category] += 1
        for product in item.get("products") or []:
            product_counts[product] += 1

    digest_files = sorted(DIGEST_DIR.glob("*.md"), reverse=True) if DIGEST_DIR.exists() else []
    digests = [digest_meta(p) for p in digest_files]

    stats = (
        '<div class="stats">'
        f'<div class="stat"><b>{len(recent)}</b><span>last {days} days</span></div>'
        f'<div class="stat"><b>{len(items)}</b><span>tracked updates</span></div>'
        f'<div class="stat"><b>{len(category_counts)}</b><span>categories</span></div>'
        f'<div class="stat"><b>{len(digests)}</b><span>digests</span></div>'
        "</div>"
    )

    body = stats + (render_groups(group_by_category(recent)) if recent else '<div class="card"><p>No updates in the current window yet.</p></div>')
    (SITE_DIR / "index.html").write_text(page(cfg, cfg.get("site_title"), body, 0), encoding="utf-8")

    rows = "".join(
        f'<li><a href="digests/{esc(d["date"])}.html">{esc(d["date"])}</a> &mdash; {d["count"]} update(s)</li>'
        for d in digests
    ) or "<li>No digests published yet.</li>"
    archive_body = f'<div class="card"><h2>Digest archive</h2><ul class="list">{rows}</ul></div>'
    (SITE_DIR / "archive.html").write_text(page(cfg, "Digest archive", archive_body, 0), encoding="utf-8")

    cat_rows = "".join(
        f'<li><b>{esc(name)}</b> &mdash; {count} update(s)</li>' for name, count in category_counts.most_common()
    ) or "<li>No data yet.</li>"
    prod_rows = "".join(
        f'<li>{esc(name)} &mdash; {count}</li>' for name, count in product_counts.most_common(40)
    ) or "<li>No data yet.</li>"
    cat_body = (
        f'<div class="card"><h2>Product categories</h2><ul class="list">{cat_rows}</ul></div>'
        f'<div class="card"><h2>Top products</h2><ul class="list">{prod_rows}</ul></div>'
    )
    (SITE_DIR / "categories.html").write_text(page(cfg, "Categories", cat_body, 0), encoding="utf-8")

    digest_dir = SITE_DIR / "digests"
    digest_dir.mkdir(parents=True, exist_ok=True)
    for path in digest_files:
        raw = path.read_text(encoding="utf-8")
        raw = re.sub(r"^---\n.*?\n---\n", "", raw, flags=re.DOTALL)
        html_body = f'<div class="card"><pre style="white-space:pre-wrap;font:14px/1.6 ui-monospace,Consolas,monospace;">{esc(raw)}</pre></div>'
        (digest_dir / f"{path.stem}.html").write_text(page(cfg, f"Digest {path.stem}", html_body, 1), encoding="utf-8")

    (SITE_DIR / "updates.json").write_text(
        json.dumps({"generated_at": utcnow().isoformat(), "count": len(items), "items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Site built in {SITE_DIR} ({len(items)} tracked updates, {len(digests)} digests).", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the static GitHub Pages site.")
    parser.add_argument("--days", type=int, default=None, help="Window shown on the landing page.")
    args = parser.parse_args()
    cfg = load_config()
    build(cfg, args.days if args.days is not None else int(cfg.get("lookback_days", 7)) * 4)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Generate the static GitHub Pages site from the update archive and digest history."""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
from collections import Counter
from datetime import timedelta
from urllib.parse import quote
from pathlib import Path

from common import (
    ARCHIVE_PATH,
    DEFAULT_CONFIG,
    DIGEST_DIR,
    SITE_DIR,
    STAGE_LABELS,
    STAGE_ORDER,
    enrichment_for,
    group_by_category,
    item_date,
    item_date_str,
    load_config,
    load_enrichment,
    read_json,
    release_stage,
    sort_items,
    status_label,
    summarize,
    update_url,
    utcnow,
)

ASSETS = Path(__file__).resolve().parent / "assets"

PILL_CLASS = {
    "ga": "ga",
    "public-preview": "pv",
    "private-preview": "pp",
    "retirement": "rt",
    "in-development": "dv",
    "other": "muted",
}

DATE_PRESETS = [(7, "7 days"), (30, "30 days"), (90, "90 days"), (0, "All time")]


def esc(value) -> str:
    return html_lib.escape(str(value or ""), quote=True)


def anchor(category: str) -> str:
    return "cat-" + re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-")


def page(cfg: dict, title: str, body_html: str, depth: int = 0) -> str:
    prefix = "../" * depth
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(cfg.get('site_description'))}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{prefix}style.css"></head>
<body>
<header><div class="wrap"><h1>{esc(cfg.get('site_title'))}</h1>
<p>{esc(cfg.get('site_description'))}</p></div></header>
<nav><a href="{prefix}index.html">Latest</a><a href="{prefix}archive.html">Digest archive</a>
<a href="{prefix}categories.html">Categories</a>
<a href="{prefix}index.html#subscribe">Subscribe</a>
<a href="{esc(cfg.get('azure_updates_url'))}">Azure Updates source</a></nav>
<main>{body_html}</main>
<footer><b>Colophon</b>
Generated {esc(utcnow().strftime('%Y-%m-%d %H:%M UTC'))} from the official Microsoft Azure release
communications feed. Summaries are produced from each announcement and its linked Microsoft
documentation. Set in Newsreader, IBM Plex Sans and JetBrains Mono.</footer>
<script src="{prefix}pptx.js"></script>
<script src="{prefix}app.js"></script>
</body></html>
"""


def render_item(item: dict, enrichment: dict) -> str:
    info = enrichment_for(item, enrichment)
    stage = release_stage(item)
    products = [p for p in (item.get("products") or []) if p]
    product_text = ", ".join(products)
    summary = info["summary"] or summarize(item.get("description", ""), 260)
    points = info["key_points"][:4]
    points_ko = info["key_points_ko"][:4] if len(info["key_points_ko"]) >= len(points) else []

    haystack = " ".join(
        [
            str(item.get("title", "")),
            product_text,
            summary,
            " ".join(points),
            " ".join(item.get("tags") or []),
            info["title_ko"],
            info["summary_ko"],
            " ".join(info["key_points_ko"]),
        ]
    ).lower()

    parts = [
        f'<div class="item{" bilingual" if info["title_ko"] else ""}"'
        f' data-stage="{esc(stage)}" data-category="{esc(item.get("_category"))}"',
        f' data-date="{esc(item_date_str(item))}" data-search="{esc(haystack)}">',
        f'<a class="title" href="{esc(update_url(item))}">{esc(item.get("title"))}</a>',
    ]
    # The DOM keeps English canonical so the deck can read it by class; CSS `order` is what
    # puts Korean on top when a translation exists.
    if info["title_ko"]:
        parts.append(f'<div class="title-ko" lang="ko">{esc(info["title_ko"])}</div>')
    parts.extend(
        [
            f'<div class="meta"><span class="pill {PILL_CLASS.get(stage, "muted")}">{esc(STAGE_LABELS.get(stage))}</span> ',
            esc(item_date_str(item)),
        ]
    )
    if product_text:
        parts.append(" &middot; " + esc(product_text))
    parts.append("</div>")
    if summary:
        parts.append(f'<div class="summary-line">{esc(summary)}</div>')
    if info["summary_ko"]:
        parts.append(f'<div class="summary-line-ko" lang="ko">{esc(info["summary_ko"])}</div>')
    if points:
        items_html = []
        for index, point in enumerate(points):
            ko = points_ko[index] if index < len(points_ko) else ""
            ko_html = f'<span class="ko" lang="ko">{esc(ko)}</span>' if ko else ""
            items_html.append(f'<li><span class="en">{esc(point)}</span>{ko_html}</li>')
        parts.append('<ul class="points">' + "".join(items_html) + "</ul>")
    if info["doc_url"]:
        label = info["doc_title"] or "Microsoft documentation"
        parts.append(f'<div class="doclink"><a href="{esc(info["doc_url"])}">{esc(label)}</a></div>')
    parts.append("</div>")
    return "".join(parts)


def render_filters(groups: dict, stage_counts: Counter, default_days: int, default_stage: str) -> str:
    stage_chips = "".join(
        f'<button class="chip s-{esc(stage)}" data-stage="{esc(stage)}" '
        f'aria-pressed="{"true" if stage == default_stage else "false"}">'
        f'{esc(STAGE_LABELS[stage])}<span class="n">{stage_counts[stage]}</span></button>'
        for stage in STAGE_ORDER
        if stage_counts.get(stage)
    )
    cat_chips = "".join(
        f'<button class="chip" data-cat="{esc(category)}" aria-pressed="false">'
        f'{esc(category)}<span class="n">{len(bucket)}</span></button>'
        for category, bucket in groups.items()
    )
    date_chips = "".join(
        f'<button class="chip" data-days="{days}" aria-pressed="{"true" if days == default_days else "false"}">'
        f"Last {esc(label)}</button>"
        if days
        else f'<button class="chip" data-days="0" aria-pressed="{"true" if default_days == 0 else "false"}">{esc(label)}</button>'
        for days, label in DATE_PRESETS
    )
    return (
        '<div class="card filters">'
        f'<div class="row"><span class="lbl">View</span>'
        '<button class="chip" data-view="browse" aria-pressed="true">Browse list</button>'
        '<button class="chip" data-view="slides" aria-pressed="false">Slide deck</button>'
        '<span class="hint">'
        "One update per screen &mdash; arrow keys or the buttons below move between slides."
        "</span></div>"
        f'<div class="row"><span class="lbl">Date range</span>{date_chips}'
        '<input type="date" id="from" aria-label="From date">'
        '<span class="hint">to</span>'
        '<input type="date" id="to" aria-label="To date">'
        '<span class="result" id="result"></span></div>'
        f'<div class="row"><span class="lbl">Release stage</span>{stage_chips}</div>'
        f'<div class="row"><span class="lbl">Service category</span>{cat_chips}</div>'
        '<div class="row"><span class="lbl">Search</span>'
        '<input type="search" id="q" placeholder="Filter by product, keyword or service name...">'
        '<button class="btn" data-toggle="reset">Reset filters</button></div>'
        "</div>"
    )


def render_deck() -> str:
    return (
        '<div class="deck hidden" id="deck">'
        '<div class="slide" id="slide"></div>'
        '<div class="deckbar">'
        '<button class="btn step" id="prev">&larr; Prev</button>'
        '<span class="counter" id="counter">00 / 00</span>'
        '<button class="btn step" id="next">Next &rarr;</button>'
        '<span class="langs hidden" id="langs" role="group" aria-label="Slide language">'
        '<button class="btn lang" data-lang="en" aria-pressed="false">EN</button>'
        '<button class="btn lang" data-lang="both" aria-pressed="true">\ubcd1\uae30</button>'
        '<button class="btn lang" data-lang="ko" aria-pressed="false">\ud55c\uae00</button>'
        "</span>"
        '<span class="spacer"></span>'
        '<span class="hint">Arrow keys, Space, Home / End &middot; Esc returns to the list</span>'
        '<button class="btn" id="ppt">PowerPoint</button>'
        '<button class="btn" id="pdf">PDF</button>'
        '<button class="btn" id="dl">HTML</button>'
        '<button class="btn" id="fs">Fullscreen</button>'
        "</div>"
        '<div class="progress"><span id="progressbar"></span></div>'
        "</div>"
    )


def render_newsletter(cfg: dict) -> str:
    """Signup panel, written in Korean.

    With a hosted endpoint the form posts in place. Without one it shows the contact address
    and a copy button, so subscribing never launches a mail client. The feed always works.
    """
    nl = cfg.get("newsletter") or {}
    if not nl.get("enabled", True):
        return ""

    t = dict((DEFAULT_CONFIG.get("newsletter") or {}).get("copy") or {})
    t.update(nl.get("copy") or {})

    action = str(nl.get("form_action") or "").strip()
    contact = str(nl.get("contact") or "").strip()

    parts = [
        '<div class="card subscribe" id="subscribe">',
        f'<h2 lang="ko">{esc(t["heading"])}<small>{esc(t["sub"])}</small></h2>',
        '<div class="subscribe-grid">',
    ]

    if action:
        strings = json.dumps(
            {k: t[k] for k in ("invalid", "sending", "sent", "failed", "form_note")},
            ensure_ascii=False,
        )
        parts += [
            f'<form class="signup" lang="ko" action="{esc(action)}" method="post"'
            f' data-mode="post" data-strings="{esc(strings)}" novalidate>',
            f'<label class="lbl" for="nl-email">{esc(t["email_label"])}</label>',
            '<div class="signup-row">',
            '<input type="email" id="nl-email" name="email" autocomplete="email" required',
            ' placeholder="you@example.com" aria-describedby="nl-help">',
            f'<button class="btn" type="submit">{esc(t["submit"])}</button>',
            "</div>",
            f'<p class="signup-help" id="nl-help" role="status">{esc(t["form_note"])}</p>',
            "</form>",
        ]
    elif contact:
        # Fallback for when no form endpoint is configured. The old mail-in automation
        # was removed, so this only offers the address for a manual request.
        strings = json.dumps({k: t[k] for k in ("copied", "copy_failed", "manual_note")}, ensure_ascii=False)
        subscribe_link = f"mailto:{contact}?subject={quote(str(nl.get('subject') or 'Subscribe'))}"
        parts += [
            f'<div class="signup" lang="ko" data-mode="copy" data-contact="{esc(contact)}"'
            f' data-strings="{esc(strings)}">',
            f'<p class="lbl">{esc(t["email_label"])}</p>',
            '<div class="signup-row">',
            f'<output class="address" id="nl-address">{esc(contact)}</output>',
            f'<button class="btn" type="button" id="nl-copy">{esc(t["copy_button"])}</button>',
            "</div>",
            '<div class="signup-row signup-row--links">',
            f'<a class="btn btn--primary" href="{esc(subscribe_link)}">메일로 문의</a>',
            "</div>",
            '<p class="signup-help" id="nl-help" role="status">'
            "지금은 자동 등록 창구가 열려 있지 않습니다. 위 주소로 메일을 주시면 수동으로 등록해 드립니다.</p>",
            "</div>",
        ]
    else:
        parts += [
            '<div class="signup" lang="ko">',
            f'<p class="signup-help signup-help--static">{esc(t["manual_note"])}</p>',
            "</div>",
        ]

    parts += [
        '<div class="feedbox" lang="ko">',
        f'<p class="lbl">{esc(t["feed_label"])}</p>',
        f'<p class="feedbox-note">{esc(t["feed_note"])}</p>',
        '<a class="btn" href="feed.xml">feed.xml</a>',
        "</div>",
        "</div></div>",
    ]
    return "".join(parts)


def build_feed(cfg: dict, digests: list) -> str:
    """Atom feed of published digests: a subscription path that needs no backend."""
    site_url = str(cfg.get("site_url") or "").rstrip("/")
    updated = digests[0]["date"] if digests else utcnow().strftime("%Y-%m-%d")
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        f"<title>{esc(cfg.get('site_title'))}</title>",
        f"<subtitle>{esc(cfg.get('site_description'))}</subtitle>",
        f'<link rel="alternate" type="text/html" href="{esc(site_url)}/"/>',
        f'<link rel="self" type="application/atom+xml" href="{esc(site_url)}/feed.xml"/>',
        f"<id>{esc(site_url)}/</id>",
        f"<updated>{esc(updated)}T00:00:00Z</updated>",
    ]
    for d in digests[:50]:
        url = f"{site_url}/digests/{d['date']}.html"
        parts += [
            "<entry>",
            f"<title>Azure product updates &#8212; {esc(d['date'])}</title>",
            f'<link rel="alternate" type="text/html" href="{esc(url)}"/>',
            f"<id>{esc(url)}</id>",
            f"<updated>{esc(d['date'])}T00:00:00Z</updated>",
            f"<summary>{d['count']} update(s) published in this digest.</summary>",
            "</entry>",
        ]
    parts.append("</feed>")
    return "\n".join(parts) + "\n"


def render_summary_table(groups: dict) -> str:
    if not groups:
        return ""
    largest = max(len(bucket) for bucket in groups.values())
    rows = []
    for category, bucket in groups.items():
        counts = Counter(release_stage(i) for i in bucket)
        products = Counter()
        for item in bucket:
            for product in item.get("products") or []:
                products[product] += 1
        top = ", ".join(name for name, _ in products.most_common(3))
        latest = max((item_date_str(i) for i in bucket if item_date_str(i)), default="")
        width = max(0.03, len(bucket) / largest)
        cells = [
            f'<td><a class="cat" href="#{anchor(category)}">{esc(category)}</a>'
            f'<span class="bar" style="transform:scaleX({width:.3f})"></span></td>',
            f'<td class="num c-n"><b>{len(bucket)}</b></td>',
            _stage_cell("c-ga", "ga", counts["ga"]),
            _stage_cell("c-pv", "pv", counts["public-preview"]),
            _stage_cell("c-pp", "pp", counts["private-preview"]),
            _stage_cell("c-rt", "rt", counts["retirement"]),
            f'<td class="num">{esc(latest)}</td>',
            f'<td class="top">{esc(top)}</td>',
        ]
        rows.append(f'<tr data-category="{esc(category)}">' + "".join(cells) + "</tr>")

    return (
        '<div class="card"><h2>Summary by category '
        "<small>updates the counts as you change the filters</small></h2>"
        '<div class="table-wrap">'
        '<table class="summary"><thead><tr><th>Category</th><th class="num">Total</th>'
        '<th class="num">GA</th><th class="num">Public preview</th><th class="num">Private preview</th>'
        '<th class="num">Retirement</th><th class="num">Latest</th><th>Top products</th></tr></thead>'
        "<tbody>" + "".join(rows) + "</tbody>"
        '<tfoot><tr id="tfoot"><td>All categories</td><td class="num c-n"></td>'
        '<td class="num c-ga"></td><td class="num c-pv"></td><td class="num c-pp"></td>'
        '<td class="num c-rt"></td><td></td><td></td></tr></tfoot></table></div></div>'
    )


def _stage_cell(css_class: str, pill: str, count: int) -> str:
    inner = f'<span class="pill {pill}">{count}</span>' if count else ""
    return f'<td class="num {css_class}">{inner}</td>'


def render_groups(groups: dict, enrichment: dict) -> str:
    out = ['<div class="columns">']
    for index, (category, bucket) in enumerate(groups.items()):
        open_attr = " open" if index < 3 else ""
        out.append(
            f'<details id="{anchor(category)}" data-category="{esc(category)}"{open_attr}>'
            f'<summary>{esc(category)}<span class="count">{len(bucket)} update(s)</span></summary>'
            '<div class="body">'
            + "".join(render_item(item, enrichment) for item in bucket)
            + "</div></details>"
        )
    out.append("</div>")
    return "".join(out)


def digest_meta(path):
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^count:\s*(\d+)\s*$", text, re.MULTILINE)
    return {"date": path.stem, "count": int(match.group(1)) if match else 0}


def build(cfg: dict, default_days: int, default_stage: str) -> None:
    items = sort_items(read_json(ARCHIVE_PATH, {"items": []}).get("items", []))
    enrichment = load_enrichment()

    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "style.css").write_text((ASSETS / "style.css").read_text(encoding="utf-8"), encoding="utf-8")
    (SITE_DIR / "app.js").write_text((ASSETS / "app.js").read_text(encoding="utf-8"), encoding="utf-8")
    (SITE_DIR / "pptx.js").write_text((ASSETS / "pptx.js").read_text(encoding="utf-8"), encoding="utf-8")
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")

    groups = group_by_category(items)
    for category, bucket in groups.items():
        for item in bucket:
            item["_category"] = category

    stage_counts = Counter(release_stage(i) for i in items)
    product_counts = Counter(p for i in items for p in (i.get("products") or []))
    category_counts = Counter(c for i in items for c in (i.get("productCategories") or []))
    summarized = sum(1 for i in items if enrichment_for(i, enrichment)["key_points"])
    docs_read = sum(1 for i in items if enrichment_for(i, enrichment)["doc_url"])

    recent_cutoff = utcnow() - timedelta(days=7)
    this_week = sum(1 for i in items if (item_date(i) or recent_cutoff) >= recent_cutoff)

    digest_files = sorted(DIGEST_DIR.glob("*.md"), reverse=True) if DIGEST_DIR.exists() else []
    digests = [digest_meta(p) for p in digest_files]

    stats = (
        '<div class="stats">'
        f'<div class="stat"><b>{this_week}</b><span>last 7 days</span></div>'
        f'<div class="stat"><b>{len(items)}</b><span>tracked updates</span></div>'
        f'<div class="stat"><b>{stage_counts["ga"]}</b><span>generally available</span></div>'
        f'<div class="stat"><b>{stage_counts["public-preview"]}</b><span>public preview</span></div>'
        f'<div class="stat"><b>{len(groups)}</b><span>categories</span></div>'
        f'<div class="stat"><b>{docs_read}</b><span>docs summarized</span></div>'
        "</div>"
    )

    if items:
        body = (
            stats
            + render_filters(groups, stage_counts, default_days, default_stage)
            + f'<div id="explorer" data-default-days="{default_days}" data-default-stage="{esc(default_stage)}">'
            + render_deck()
            + '<div class="browse-only">'
            + render_summary_table(groups)
            + '<div class="toolbar"><h2>Updates by category</h2>'
            '<button class="btn" data-toggle="open">Expand all</button>'
            '<button class="btn" data-toggle="close">Collapse all</button></div>'
            + render_groups(groups, enrichment)
            + '<div class="card empty hidden" id="empty">No updates match the selected filters.</div>'
            + render_newsletter(cfg)
            + "</div>"
            + "</div>"
        )
    else:
        body = stats + '<div class="card"><p>No updates tracked yet.</p></div>' + render_newsletter(cfg)
    (SITE_DIR / "index.html").write_text(page(cfg, cfg.get("site_title"), body, 0), encoding="utf-8")

    rows = "".join(
        f'<li><a href="digests/{esc(d["date"])}.html">{esc(d["date"])}</a> &mdash; {d["count"]} update(s)</li>'
        for d in digests
    ) or "<li>No digests published yet.</li>"
    (SITE_DIR / "archive.html").write_text(
        page(cfg, "Digest archive", f'<div class="card"><h2>Digest archive</h2><ul class="list">{rows}</ul></div>', 0),
        encoding="utf-8",
    )

    cat_rows = "".join(
        f'<li><b>{esc(name)}</b> &mdash; {count} update(s)</li>' for name, count in category_counts.most_common()
    ) or "<li>No data yet.</li>"
    prod_rows = "".join(
        f'<li>{esc(name)} &mdash; {count}</li>' for name, count in product_counts.most_common(60)
    ) or "<li>No data yet.</li>"
    stage_rows = "".join(
        f'<li><span class="pill {PILL_CLASS.get(stage, "muted")}">{esc(STAGE_LABELS[stage])}</span> '
        f"&mdash; {stage_counts[stage]} update(s)</li>"
        for stage in STAGE_ORDER
        if stage_counts.get(stage)
    )
    (SITE_DIR / "categories.html").write_text(
        page(
            cfg,
            "Categories",
            f'<div class="card"><h2>Release stages</h2><ul class="list">{stage_rows}</ul></div>'
            f'<div class="card"><h2>Product categories</h2><ul class="list">{cat_rows}</ul></div>'
            f'<div class="card"><h2>Top products</h2><ul class="list">{prod_rows}</ul></div>',
            0,
        ),
        encoding="utf-8",
    )

    digest_dir = SITE_DIR / "digests"
    digest_dir.mkdir(parents=True, exist_ok=True)
    for path in digest_files:
        raw = re.sub(r"^---\n.*?\n---\n", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
        html_body = f'<div class="card"><pre class="digest-source">{esc(raw)}</pre></div>'
        (digest_dir / f"{path.stem}.html").write_text(page(cfg, f"Digest {path.stem}", html_body, 1), encoding="utf-8")

    (SITE_DIR / "feed.xml").write_text(build_feed(cfg, digests), encoding="utf-8")

    (SITE_DIR / "updates.json").write_text(        json.dumps(
            {
                "generated_at": utcnow().isoformat(),
                "count": len(items),
                "items": [
                    dict(
                        {k: v for k, v in i.items() if k != "_category"},
                        category=i.get("_category"),
                        release_stage=release_stage(i),
                        enrichment=enrichment_for(i, enrichment),
                    )
                    for i in items
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"Site built in {SITE_DIR}: {len(items)} updates, {len(groups)} categories, "
        f"{summarized} summarized, {docs_read} with documentation.",
        file=sys.stderr,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the static GitHub Pages site.")
    parser.add_argument("--default-days", type=int, default=30, help="Date filter preset selected on load (0 = all).")
    parser.add_argument(
        "--default-stage",
        default="ga",
        choices=["ga", "public-preview", "private-preview", "retirement", "in-development", "none"],
        help="Release stage pre-selected on load ('none' selects every stage).",
    )
    args = parser.parse_args()
    stage = "" if args.default_stage == "none" else args.default_stage
    build(load_config(), args.default_days, stage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

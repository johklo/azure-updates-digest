"""Render a Markdown digest and an HTML/plain-text email from fetched Azure updates."""

from __future__ import annotations

import argparse
import html as html_lib
import sys

from common import (
    BUILD_DIR,
    DIGEST_DIR,
    LATEST_PATH,
    enrichment_for,
    group_by_category,
    is_ga,
    is_preview,
    item_date_str,
    load_config,
    load_enrichment,
    read_json,
    set_action_output,
    status_label,
    summarize,
    update_url,
    utcnow,
)


def digest_title(cfg: dict, date_str: str) -> str:
    return f"Azure product updates - {date_str}"


def anchor(category: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-")


def category_rows(groups: dict):
    for category, bucket in groups.items():
        ga = sum(1 for i in bucket if is_ga(i))
        preview = sum(1 for i in bucket if is_preview(i))
        yield category, bucket, ga, preview


def render_markdown(cfg: dict, payload: dict, date_str: str, enrichment: dict) -> str:
    items = payload.get("items", [])
    groups = group_by_category(items)
    window_days = payload.get("window_days", cfg.get("lookback_days", 7))

    lines = [
        "---",
        f'title: "{digest_title(cfg, date_str)}"',
        f"date: {date_str}",
        f"count: {len(items)}",
        f"window_days: {window_days}",
        "---",
        "",
        f"# {digest_title(cfg, date_str)}",
        "",
        f"**{len(items)} update(s)** published in the last {window_days} day(s), grouped by Azure product category.",
        "",
        f"Source: [Azure Updates]({cfg.get('azure_updates_url')})",
        "",
    ]

    if not items:
        lines += ["_No new Azure updates were published in this window._", ""]
        return "\n".join(lines)

    lines += ["## Summary by category", "", "| Category | Updates | GA | Preview | Top products |", "| --- | ---: | ---: | ---: | --- |"]
    for category, bucket, ga, preview in category_rows(groups):
        from collections import Counter

        products = Counter()
        for item in bucket:
            for product in item.get("products") or []:
                products[product] += 1
        top = ", ".join(name for name, _ in products.most_common(3))
        lines.append(f"| [{category}](#{anchor(category)}) | {len(bucket)} | {ga or '-'} | {preview or '-'} | {top} |")
    lines.append("")

    for category, bucket, _, _ in category_rows(groups):
        lines += [f"## {category}", ""]
        for item in bucket:
            info = enrichment_for(item, enrichment)
            lines.append(f"### [{str(item.get('title', '')).strip()}]({update_url(item)})")
            lines.append("")
            meta = [f"**Status:** {status_label(item)}", f"**Published:** {item_date_str(item)}"]
            products = [p for p in (item.get("products") or []) if p]
            if products:
                meta.append("**Products:** " + ", ".join(products))
            tags = [t for t in (item.get("tags") or []) if t]
            if tags:
                meta.append("**Tags:** " + ", ".join(tags))
            lines += [" | ".join(meta), ""]

            summary = info["summary"] or summarize(item.get("description", ""), 400)
            if summary:
                lines += [summary, ""]
            if info["key_points"]:
                lines += [f"- {point}" for point in info["key_points"]]
                lines.append("")
            if info["doc_url"]:
                label = info["doc_title"] or "Microsoft documentation"
                lines += [f"Documentation: [{label}]({info['doc_url']})", ""]

    lines += ["---", "", f"_Generated automatically on {utcnow().strftime('%Y-%m-%d %H:%M UTC')}._", ""]
    return "\n".join(lines)


def _esc(value) -> str:
    return html_lib.escape(str(value or ""), quote=True)


def render_email_html(cfg: dict, payload: dict, date_str: str, enrichment: dict) -> str:
    items = payload.get("items", [])
    groups = group_by_category(items)
    max_items = int(cfg.get("email", {}).get("max_items_per_category", 25))
    window_days = payload.get("window_days", cfg.get("lookback_days", 7))
    site_url = cfg.get("site_url") or cfg.get("azure_updates_url")

    parts = [
        "<!DOCTYPE html>",
        '<html><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_esc(digest_title(cfg, date_str))}</title></head>",
        '<body style="margin:0;padding:0;background:#f4f6f8;">',
        '<div style="max-width:760px;margin:0 auto;padding:24px 16px;font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#1b1f23;">',
        '<div style="background:#0078d4;color:#ffffff;padding:20px 24px;border-radius:8px 8px 0 0;">',
        f'<h1 style="margin:0;font-size:20px;line-height:1.3;">{_esc(cfg.get("site_title"))}</h1>',
        f'<p style="margin:6px 0 0;font-size:13px;opacity:.9;">{_esc(date_str)} &middot; {len(items)} update(s) from the last {window_days} day(s)</p>',
        "</div>",
        '<div style="background:#ffffff;padding:8px 24px 24px;border:1px solid #e1e4e8;border-top:none;border-radius:0 0 8px 8px;">',
    ]

    if not items:
        parts.append('<p style="font-size:14px;">No new Azure updates were published in this window.</p>')
    else:
        parts.append('<h2 style="font-size:15px;margin:18px 0 8px;">Summary by category</h2>')
        parts.append('<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;font-size:13px;">')
        parts.append(
            '<tr style="background:#f2f6fa;">'
            '<th align="left" style="padding:7px 9px;border-bottom:2px solid #e1e4e8;color:#57606a;font-size:11px;text-transform:uppercase;">Category</th>'
            '<th align="right" style="padding:7px 9px;border-bottom:2px solid #e1e4e8;color:#57606a;font-size:11px;text-transform:uppercase;">Updates</th>'
            '<th align="right" style="padding:7px 9px;border-bottom:2px solid #e1e4e8;color:#57606a;font-size:11px;text-transform:uppercase;">GA</th>'
            '<th align="right" style="padding:7px 9px;border-bottom:2px solid #e1e4e8;color:#57606a;font-size:11px;text-transform:uppercase;">Preview</th>'
            "</tr>"
        )
        for index, (category, bucket, ga, preview) in enumerate(category_rows(groups)):
            parts.append(
                f'<tr><td style="padding:7px 9px;border-bottom:1px solid #eef0f2;">'
                f'<a href="#cat-{index}" style="color:#0b4f9e;text-decoration:none;font-weight:600;">{_esc(category)}</a></td>'
                f'<td align="right" style="padding:7px 9px;border-bottom:1px solid #eef0f2;"><b>{len(bucket)}</b></td>'
                f'<td align="right" style="padding:7px 9px;border-bottom:1px solid #eef0f2;color:#0f7b34;">{ga or "&ndash;"}</td>'
                f'<td align="right" style="padding:7px 9px;border-bottom:1px solid #eef0f2;color:#8a5a00;">{preview or "&ndash;"}</td></tr>'
            )
        parts.append("</table>")

        for index, (category, bucket, _, _) in enumerate(category_rows(groups)):
            parts.append(
                f'<h2 id="cat-{index}" style="font-size:16px;margin:26px 0 8px;padding-bottom:6px;'
                f'border-bottom:2px solid #0078d4;">{_esc(category)} '
                f'<span style="color:#57606a;font-weight:400;">({len(bucket)})</span></h2>'
            )
            for item in bucket[:max_items]:
                info = enrichment_for(item, enrichment)
                products = ", ".join(p for p in (item.get("products") or []) if p)
                summary = info["summary"] or summarize(item.get("description", ""), 300)
                parts.append('<div style="padding:12px 0;border-bottom:1px solid #eaecef;">')
                parts.append(
                    f'<a href="{_esc(update_url(item))}" style="font-size:15px;font-weight:600;'
                    f'color:#0b4f9e;text-decoration:none;">{_esc(item.get("title"))}</a>'
                )
                meta_tail = " &middot; " + _esc(products) if products else ""
                parts.append(
                    f'<div style="margin:6px 0;font-size:12px;color:#57606a;">'
                    f'<span style="display:inline-block;background:#eef4fb;color:#0b4f9e;border-radius:10px;'
                    f'padding:2px 8px;margin-right:6px;">{_esc(status_label(item))}</span>'
                    f'{_esc(item_date_str(item))}{meta_tail}</div>'
                )
                if summary:
                    parts.append(f'<div style="font-size:13px;line-height:1.5;color:#24292f;">{_esc(summary)}</div>')
                if info["key_points"]:
                    bullets = "".join(f"<li style=\"margin:3px 0;\">{_esc(p)}</li>" for p in info["key_points"][:4])
                    parts.append(f'<ul style="margin:7px 0 0;padding-left:18px;font-size:12.5px;color:#3a4048;">{bullets}</ul>')
                if info["doc_url"]:
                    label = info["doc_title"] or "Microsoft documentation"
                    parts.append(
                        f'<div style="margin-top:6px;font-size:12px;">&#128196; '
                        f'<a href="{_esc(info["doc_url"])}" style="color:#0078d4;">{_esc(label)}</a></div>'
                    )
                parts.append("</div>")
            if len(bucket) > max_items:
                parts.append(
                    f'<p style="font-size:12px;color:#57606a;margin:8px 0;">+ {len(bucket) - max_items} '
                    "more in this category - see the full digest online.</p>"
                )

    parts += [
        f'<p style="margin:24px 0 0;font-size:12px;color:#57606a;">Full archive: '
        f'<a href="{_esc(site_url)}" style="color:#0078d4;">{_esc(site_url)}</a><br>Source: '
        f'<a href="{_esc(cfg.get("azure_updates_url"))}" style="color:#0078d4;">Azure Updates</a> &middot; '
        f'generated {_esc(utcnow().strftime("%Y-%m-%d %H:%M UTC"))}</p>',
        "</div></div></body></html>",
    ]
    return "\n".join(parts)


def render_email_text(cfg: dict, payload: dict, date_str: str, enrichment: dict) -> str:
    items = payload.get("items", [])
    groups = group_by_category(items)
    title = digest_title(cfg, date_str)
    lines = [title, "=" * len(title), ""]
    if not items:
        return "\n".join(lines + ["No new Azure updates were published in this window."]) + "\n"

    lines += ["SUMMARY BY CATEGORY", "-" * 19]
    for category, bucket, ga, preview in category_rows(groups):
        lines.append(f"  {category}: {len(bucket)} update(s) (GA {ga}, preview {preview})")
    lines.append("")

    for category, bucket, _, _ in category_rows(groups):
        lines += [f"{category} ({len(bucket)})", "-" * (len(category) + 6)]
        for item in bucket:
            info = enrichment_for(item, enrichment)
            lines.append(f"* {item.get('title')} [{status_label(item)}, {item_date_str(item)}]")
            if info["summary"]:
                lines.append(f"  {info['summary']}")
            for point in info["key_points"][:3]:
                lines.append(f"    - {point}")
            lines.append(f"  {update_url(item)}")
            if info["doc_url"]:
                lines.append(f"  Docs: {info['doc_url']}")
        lines.append("")
    lines.append(f"Source: {cfg.get('azure_updates_url')}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Markdown digest and email payloads.")
    parser.add_argument("--input", default=str(LATEST_PATH))
    parser.add_argument("--date", default=None, help="Digest date (YYYY-MM-DD). Defaults to today in UTC.")
    parser.add_argument("--skip-empty", action="store_true", help="Do not write a digest file when there are no updates.")
    args = parser.parse_args()

    cfg = load_config()
    payload = read_json(args.input, {"items": []})
    items = payload.get("items", [])
    enrichment = load_enrichment()
    date_str = args.date or utcnow().strftime("%Y-%m-%d")

    subject = f"{cfg.get('email', {}).get('subject_prefix', '[Azure Updates]')} {date_str} - {len(items)} update(s)"

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    (BUILD_DIR / "email.html").write_text(render_email_html(cfg, payload, date_str, enrichment), encoding="utf-8")
    (BUILD_DIR / "email.txt").write_text(render_email_text(cfg, payload, date_str, enrichment), encoding="utf-8")
    (BUILD_DIR / "subject.txt").write_text(subject + "\n", encoding="utf-8")

    digest_path = DIGEST_DIR / f"{date_str}.md"
    if items or not args.skip_empty:
        DIGEST_DIR.mkdir(parents=True, exist_ok=True)
        digest_path.write_text(render_markdown(cfg, payload, date_str, enrichment), encoding="utf-8")
        print(f"Wrote {digest_path} ({len(items)} update(s)).", file=sys.stderr)
    else:
        print("No updates; skipped writing a digest file.", file=sys.stderr)

    set_action_output("has_updates", "true" if items else "false")
    set_action_output("count", str(len(items)))
    set_action_output("subject", subject)
    set_action_output("digest_path", str(digest_path.relative_to(digest_path.parents[1])))
    set_action_output("digest_date", date_str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

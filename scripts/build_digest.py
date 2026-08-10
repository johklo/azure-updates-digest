"""Render a Markdown digest and an HTML/plain-text email from fetched Azure updates."""

from __future__ import annotations

import argparse
import html as html_lib
import sys

from common import (
    BUILD_DIR,
    DIGEST_DIR,
    LATEST_PATH,
    group_by_category,
    item_date_str,
    load_config,
    read_json,
    set_action_output,
    status_label,
    strip_html,
    summarize,
    update_url,
    utcnow,
)


def digest_title(cfg: dict, date_str: str) -> str:
    return f"Azure product updates - {date_str}"


def render_markdown(cfg: dict, payload: dict, date_str: str) -> str:
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

    lines.append("## Contents")
    lines.append("")
    for category, bucket in groups.items():
        anchor = category.lower().replace(" ", "-").replace("+", "").replace("--", "-").strip("-")
        lines.append(f"- [{category}](#{anchor}) ({len(bucket)})")
    lines.append("")

    for category, bucket in groups.items():
        lines.append(f"## {category}")
        lines.append("")
        for item in bucket:
            title = str(item.get("title", "")).strip()
            lines.append(f"### [{title}]({update_url(item)})")
            lines.append("")
            meta = [f"**Status:** {status_label(item)}", f"**Published:** {item_date_str(item)}"]
            products = [p for p in (item.get("products") or []) if p]
            if products:
                meta.append("**Products:** " + ", ".join(products))
            tags = [t for t in (item.get("tags") or []) if t]
            if tags:
                meta.append("**Tags:** " + ", ".join(tags))
            lines.append(" | ".join(meta))
            lines.append("")
            summary = summarize(item.get("description", ""), 600)
            if summary:
                lines.append(summary)
                lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"_Generated automatically on {utcnow().strftime('%Y-%m-%d %H:%M UTC')}._")
    lines.append("")
    return "\n".join(lines)


def _esc(value: str) -> str:
    return html_lib.escape(str(value or ""), quote=True)


def render_email_html(cfg: dict, payload: dict, date_str: str) -> str:
    items = payload.get("items", [])
    groups = group_by_category(items)
    max_items = int(cfg.get("email", {}).get("max_items_per_category", 25))
    window_days = payload.get("window_days", cfg.get("lookback_days", 7))

    parts = [
        "<!DOCTYPE html>",
        '<html><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_esc(digest_title(cfg, date_str))}</title></head>",
        '<body style="margin:0;padding:0;background:#f4f6f8;">',
        '<div style="max-width:720px;margin:0 auto;padding:24px 16px;font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#1b1f23;">',
        '<div style="background:#0078d4;color:#ffffff;padding:20px 24px;border-radius:8px 8px 0 0;">',
        f'<h1 style="margin:0;font-size:20px;line-height:1.3;">{_esc(cfg.get("site_title"))}</h1>',
        f'<p style="margin:6px 0 0;font-size:13px;opacity:.9;">{_esc(date_str)} &middot; {len(items)} update(s) from the last {window_days} day(s)</p>',
        "</div>",
        '<div style="background:#ffffff;padding:8px 24px 24px;border:1px solid #e1e4e8;border-top:none;border-radius:0 0 8px 8px;">',
    ]

    if not items:
        parts.append('<p style="font-size:14px;">No new Azure updates were published in this window.</p>')
    else:
        parts.append('<p style="font-size:13px;color:#57606a;margin:16px 0;">Jump to a category:</p><p style="font-size:13px;margin:0 0 16px;">')
        parts.append(" &middot; ".join(f"<a href=\"#cat-{i}\" style=\"color:#0078d4;text-decoration:none;\">{_esc(c)} ({len(b)})</a>" for i, (c, b) in enumerate(groups.items())))
        parts.append("</p>")

        for index, (category, bucket) in enumerate(groups.items()):
            parts.append(f'<h2 id="cat-{index}" style="font-size:16px;margin:24px 0 8px;padding-bottom:6px;border-bottom:2px solid #0078d4;">{_esc(category)} <span style="color:#57606a;font-weight:400;">({len(bucket)})</span></h2>')
            for item in bucket[:max_items]:
                products = ", ".join(p for p in (item.get("products") or []) if p)
                parts.append('<div style="padding:12px 0;border-bottom:1px solid #eaecef;">')
                parts.append(f'<a href="{_esc(update_url(item))}" style="font-size:15px;font-weight:600;color:#0b4f9e;text-decoration:none;">{_esc(item.get("title"))}</a>')
                parts.append(f'<div style="margin:6px 0;font-size:12px;color:#57606a;"><span style="display:inline-block;background:#eef4fb;color:#0b4f9e;border-radius:10px;padding:2px 8px;margin-right:6px;">{_esc(status_label(item))}</span>{_esc(item_date_str(item))}{" &middot; " + _esc(products) if products else ""}</div>')
                summary = summarize(item.get("description", ""), 320)
                if summary:
                    parts.append(f'<div style="font-size:13px;line-height:1.5;color:#24292f;">{_esc(summary)}</div>')
                parts.append("</div>")
            if len(bucket) > max_items:
                parts.append(f'<p style="font-size:12px;color:#57606a;margin:8px 0;">+ {len(bucket) - max_items} more in this category - see the full digest online.</p>')

    site_url = cfg.get("site_url") or cfg.get("azure_updates_url")
    parts += [
        f'<p style="margin:24px 0 0;font-size:12px;color:#57606a;">Full archive: <a href="{_esc(site_url)}" style="color:#0078d4;">{_esc(site_url)}</a><br>Source: <a href="{_esc(cfg.get("azure_updates_url"))}" style="color:#0078d4;">Azure Updates</a> &middot; generated {_esc(utcnow().strftime("%Y-%m-%d %H:%M UTC"))}</p>',
        "</div></div></body></html>",
    ]
    return "\n".join(parts)


def render_email_text(cfg: dict, payload: dict, date_str: str) -> str:
    items = payload.get("items", [])
    groups = group_by_category(items)
    lines = [digest_title(cfg, date_str), "=" * len(digest_title(cfg, date_str)), ""]
    if not items:
        lines.append("No new Azure updates were published in this window.")
        return "\n".join(lines) + "\n"
    for category, bucket in groups.items():
        lines += [f"{category} ({len(bucket)})", "-" * (len(category) + 6)]
        for item in bucket:
            lines.append(f"* {item.get('title')} [{status_label(item)}, {item_date_str(item)}]")
            lines.append(f"  {update_url(item)}")
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
    date_str = args.date or utcnow().strftime("%Y-%m-%d")

    subject = f"{cfg.get('email', {}).get('subject_prefix', '[Azure Updates]')} {date_str} - {len(items)} update(s)"

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    (BUILD_DIR / "email.html").write_text(render_email_html(cfg, payload, date_str), encoding="utf-8")
    (BUILD_DIR / "email.txt").write_text(render_email_text(cfg, payload, date_str), encoding="utf-8")
    (BUILD_DIR / "subject.txt").write_text(subject + "\n", encoding="utf-8")

    digest_path = DIGEST_DIR / f"{date_str}.md"
    if items or not args.skip_empty:
        DIGEST_DIR.mkdir(parents=True, exist_ok=True)
        digest_path.write_text(render_markdown(cfg, payload, date_str), encoding="utf-8")
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

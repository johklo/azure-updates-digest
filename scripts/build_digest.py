"""Render a Markdown digest and an HTML/plain-text email from fetched Azure updates."""

from __future__ import annotations

import argparse
import html as html_lib
import sys

from common import (
    stage_label,
    STAGE_LABELS,
    release_stage,
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
        f"**{len(items)} new update(s)** &mdash; first seen in this run. The last {window_days} "
        "day(s) are rescanned every time so late or backdated announcements are not missed. "
        "Grouped by Azure product category.",
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


# The site palette, converted from oklch because mail clients do not support it.
C = {
    "paper": "#F4F7FB", "paper2": "#E9EEF3", "rule": "#CED5DD", "ruleStrong": "#9BA6B2",
    "muted": "#5F6A77", "ink2": "#384350", "ink": "#131E2A", "accent": "#0064B6",
    "cover": "#0E253E", "coverInk": "#E9EFF7", "coverMuted": "#9EADBE", "coverRule": "#415771",
}

STAGE_COLOR = {
    "ga": ("#09672E", "#E7F5E9"), "public-preview": ("#8A5600", "#F9EEE2"),
    "private-preview": ("#643B9A", "#F3ECFF"), "retirement": ("#A5292B", "#FFE9E6"),
    "in-development": ("#135F83", "#E6F2FA"), "other": ("#5F6A77", "#E9EEF3"),
}

# Web fonts do not survive most mail clients, so these mirror the site's serif display /
# sans body pairing with stacks that are actually installed.
FONT_DISPLAY = "Georgia,'Times New Roman',serif"
FONT_BODY = "'Segoe UI',-apple-system,'Malgun Gothic','Apple SD Gothic Neo',Helvetica,Arial,sans-serif"
FONT_MONO = "Consolas,'Courier New',monospace"


def _label(text: str, color: str | None = None) -> str:
    """Small-caps monospace label, the same device the site uses for eyebrows."""
    return (
        f'<div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:.14em;'
        f'text-transform:uppercase;color:{color or C["muted"]};margin:0 0 6px">{text}</div>'
    )


def render_email_html(cfg: dict, payload: dict, date_str: str, enrichment: dict) -> str:
    """Bilingual HTML digest laid out like the site: Korean first, English beneath."""
    items = payload.get("items", [])
    groups = group_by_category(items)
    max_items = int(cfg.get("email", {}).get("max_items_per_category", 25))
    site = str(cfg.get("site_url") or "").rstrip("/")

    out = [
        '<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta name="color-scheme" content="light only">',
        f"<title>{_esc(digest_title(cfg, date_str))}</title></head>",
        f'<body style="margin:0;padding:0;background:{C["paper"]};">',
        f'<div style="max-width:680px;margin:0 auto;padding:24px 16px;font-family:{FONT_BODY};'
        f'color:{C["ink"]};-webkit-text-size-adjust:100%;">',

        # Masthead, echoing the site cover
        f'<div style="background:{C["cover"]};padding:26px 28px;">',
        f'<div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:.18em;'
        f'text-transform:uppercase;color:{C["coverMuted"]};margin-bottom:10px">'
        f'Azure Product Updates &middot; {_esc(date_str)}</div>',
        f'<div style="font-family:{FONT_DISPLAY};font-size:27px;line-height:1.2;color:{C["coverInk"]};'
        f'font-weight:600">오늘의 Azure 업데이트</div>',
        f'<div style="font-size:13px;color:{C["coverMuted"]};margin-top:8px">'
        f'{len(items)}건의 새 업데이트 &middot; 카테고리별 정리</div>',
        "</div>",

        f'<div style="background:#ffffff;padding:4px 28px 28px;border:1px solid {C["rule"]};border-top:none;">',
    ]

    if not items:
        out.append(f'<p style="font-size:14px;color:{C["muted"]}">이 기간에 새로 게시된 업데이트가 없습니다.</p>')
    else:
        # Summary table
        out.append('<div style="margin:22px 0 6px">' + _label("Summary by category / 카테고리 요약") + "</div>")
        out.append('<table role="presentation" cellpadding="0" cellspacing="0" width="100%" '
                   'style="width:100%;border-collapse:collapse;font-size:13px">')
        out.append(
            f'<tr><th align="left" style="padding:7px 8px;border-bottom:2px solid {C["ruleStrong"]};'
            f'font-family:{FONT_MONO};font-size:10px;letter-spacing:.1em;text-transform:uppercase;'
            f'color:{C["muted"]};font-weight:400">Category</th>'
            f'<th align="right" style="padding:7px 8px;border-bottom:2px solid {C["ruleStrong"]};'
            f'font-family:{FONT_MONO};font-size:10px;letter-spacing:.1em;text-transform:uppercase;'
            f'color:{C["muted"]};font-weight:400">Total</th>'
            f'<th align="right" style="padding:7px 8px;border-bottom:2px solid {C["ruleStrong"]};'
            f'font-family:{FONT_MONO};font-size:10px;letter-spacing:.1em;text-transform:uppercase;'
            f'color:{C["muted"]};font-weight:400">GA</th>'
            f'<th align="right" style="padding:7px 8px;border-bottom:2px solid {C["ruleStrong"]};'
            f'font-family:{FONT_MONO};font-size:10px;letter-spacing:.1em;text-transform:uppercase;'
            f'color:{C["muted"]};font-weight:400">Preview</th></tr>'
        )
        for index, (category, bucket, ga, preview) in enumerate(category_rows(groups)):
            out.append(
                f'<tr><td style="padding:8px;border-bottom:1px solid {C["rule"]}">'
                f'<a href="#cat-{index}" style="color:{C["accent"]};text-decoration:none;font-weight:600">'
                f'{_esc(category)}</a></td>'
                f'<td align="right" style="padding:8px;border-bottom:1px solid {C["rule"]};'
                f'font-family:{FONT_MONO}"><b>{len(bucket)}</b></td>'
                f'<td align="right" style="padding:8px;border-bottom:1px solid {C["rule"]};'
                f'font-family:{FONT_MONO};color:{STAGE_COLOR["ga"][0]}">{ga or "&ndash;"}</td>'
                f'<td align="right" style="padding:8px;border-bottom:1px solid {C["rule"]};'
                f'font-family:{FONT_MONO};color:{STAGE_COLOR["public-preview"][0]}">{preview or "&ndash;"}</td></tr>'
            )
        out.append("</table>")

        for index, (category, bucket, _, _) in enumerate(category_rows(groups)):
            out.append(
                f'<h2 id="cat-{index}" style="font-family:{FONT_DISPLAY};font-size:19px;font-weight:600;'
                f'margin:34px 0 2px;padding-bottom:8px;border-bottom:2px solid {C["ink"]};color:{C["ink"]}">'
                f'{_esc(category)} <span style="font-family:{FONT_MONO};font-size:11px;color:{C["muted"]};'
                f'font-weight:400">{len(bucket)}</span></h2>'
            )
            for item in bucket[:max_items]:
                out.append(_render_item(cfg, item, enrichment))
            if len(bucket) > max_items:
                out.append(
                    f'<p style="font-size:12px;color:{C["muted"]};margin:10px 0">'
                    f'이 카테고리에 {len(bucket) - max_items}건이 더 있습니다. '
                    f'<a href="{_esc(site)}" style="color:{C["accent"]}">웹에서 보기</a></p>'
                )

    out += [
        f'<div style="margin-top:30px;padding-top:16px;border-top:1px solid {C["rule"]};'
        f'font-size:12px;color:{C["muted"]};line-height:1.7">',
        f'출처: <a href="{_esc(cfg.get("azure_updates_url"))}" style="color:{C["accent"]};'
        f'text-decoration:none">Azure Updates</a> &middot; '
        f'요약은 각 공지와 연결된 Microsoft 문서를 읽어 생성했습니다.<br>'
        f'<a href="{_esc(site)}" style="color:{C["accent"]};text-decoration:none">'
        f'전체 아카이브와 필터 보기 &rarr;</a>',
        "</div></div></div></body></html>",
    ]
    return "\n".join(out)


def _render_item(cfg: dict, item: dict, enrichment: dict) -> str:
    """One update: Korean on top, English underneath, matching the site's bilingual order."""
    info = enrichment_for(item, enrichment)
    stage = release_stage(item)
    fg, bg = STAGE_COLOR.get(stage, STAGE_COLOR["other"])
    products = ", ".join(p for p in (item.get("products") or []) if p)

    summary_en = info["summary"] or summarize(item.get("description", ""), 300)
    points_en = info["key_points"][:4]
    points_ko = info["key_points_ko"][:4] if len(info["key_points_ko"]) >= len(points_en) else []

    parts = [f'<div style="padding:18px 0;border-bottom:1px solid {C["rule"]}">']

    parts.append(
        f'<div style="margin-bottom:9px">'
        f'<span style="display:inline-block;background:{bg};color:{fg};font-family:{FONT_MONO};'
        f'font-size:10px;letter-spacing:.08em;text-transform:uppercase;padding:3px 9px;'
        f'margin-right:8px">{_esc(STAGE_LABELS.get(stage, "Other"))}</span>'
        f'<span style="font-family:{FONT_MONO};font-size:11px;color:{C["muted"]}">'
        f'{_esc(item_date_str(item))}{" &middot; " + _esc(products) if products else ""}</span></div>'
    )

    # Title: Korean first when translated, English kept as the canonical link.
    if info["title_ko"]:
        parts.append(
            f'<div lang="ko" style="font-family:{FONT_DISPLAY};font-size:17px;line-height:1.4;'
            f'font-weight:600;color:{C["ink"]};margin:0 0 3px;word-break:keep-all">'
            f'{_esc(info["title_ko"])}</div>'
        )
        parts.append(
            f'<a href="{_esc(update_url(item))}" style="display:block;font-size:12.5px;line-height:1.45;'
            f'color:{C["muted"]};text-decoration:none;margin:0 0 9px">{_esc(item.get("title"))}</a>'
        )
    else:
        parts.append(
            f'<a href="{_esc(update_url(item))}" style="display:block;font-family:{FONT_DISPLAY};'
            f'font-size:17px;line-height:1.4;font-weight:600;color:{C["ink"]};'
            f'text-decoration:none;margin:0 0 9px">{_esc(item.get("title"))}</a>'
        )

    if info["summary_ko"]:
        parts.append(
            f'<div lang="ko" style="font-size:14px;line-height:1.65;color:{C["ink2"]};'
            f'border-left:3px solid {C["accent"]};padding-left:11px;margin:0 0 6px;'
            f'word-break:keep-all">{_esc(info["summary_ko"])}</div>'
        )
        if summary_en:
            parts.append(
                f'<div style="font-size:12.5px;line-height:1.6;color:{C["muted"]};'
                f'padding-left:14px;margin:0 0 10px">{_esc(summary_en)}</div>'
            )
    elif summary_en:
        parts.append(
            f'<div style="font-size:14px;line-height:1.65;color:{C["ink2"]};'
            f'border-left:3px solid {C["accent"]};padding-left:11px;margin:0 0 10px">'
            f'{_esc(summary_en)}</div>'
        )

    if points_en:
        parts.append('<table role="presentation" cellpadding="0" cellspacing="0" width="100%" '
                     'style="width:100%;border-collapse:collapse;margin:2px 0 0">')
        for position, point in enumerate(points_en):
            ko = points_ko[position] if position < len(points_ko) else ""
            body = (
                f'<div lang="ko" style="font-size:13px;line-height:1.6;color:{C["ink2"]};'
                f'word-break:keep-all">{_esc(ko)}</div>'
                f'<div style="font-size:12px;line-height:1.55;color:{C["muted"]};margin-top:2px">'
                f'{_esc(point)}</div>'
            ) if ko else (
                f'<div style="font-size:13px;line-height:1.6;color:{C["ink2"]}">{_esc(point)}</div>'
            )
            parts.append(
                f'<tr><td width="14" valign="top" style="padding:4px 0 0;color:{C["accent"]};'
                f'font-size:13px;line-height:1.6">&bull;</td>'
                f'<td valign="top" style="padding:4px 0 0">{body}</td></tr>'
            )
        parts.append("</table>")

    if info["doc_url"]:
        label = info["doc_title"] or "Microsoft 문서"
        parts.append(
            f'<div style="margin-top:11px;font-family:{FONT_MONO};font-size:11px">'
            f'<a href="{_esc(info["doc_url"])}" style="color:{C["accent"]};text-decoration:none">'
            f'&#8599; {_esc(label)}</a></div>'
        )

    parts.append("</div>")
    return "".join(parts)


def render_email_text(cfg: dict, payload: dict, date_str: str, enrichment: dict) -> str:
    """Plain-text twin of the HTML mail, Korean first with the English kept underneath."""
    items = payload.get("items", [])
    groups = group_by_category(items)
    title = f"오늘의 Azure 업데이트 · {date_str}"
    lines = [title, "=" * 46, ""]

    if not items:
        return "\n".join(lines + ["이 기간에 새로 게시된 업데이트가 없습니다."]) + "\n"

    lines += ["카테고리 요약 / SUMMARY BY CATEGORY", "-" * 46]
    for category, bucket, ga, preview in category_rows(groups):
        lines.append(f"  {category}: {len(bucket)}건 (GA {ga}, preview {preview})")
    lines.append("")

    for category, bucket, _, _ in category_rows(groups):
        lines += [f"{category} ({len(bucket)})", "-" * 46]
        for item in bucket:
            info = enrichment_for(item, enrichment)
            lines.append(f"[{stage_label(item)}] {item_date_str(item)}")
            lines.append(f"  {info['title_ko'] or item.get('title')}")
            if info["title_ko"]:
                lines.append(f"  {item.get('title')}")
            summary = info["summary_ko"] or info["summary"]
            if summary:
                lines.append(f"    {summary}")
            points_ko = info["key_points_ko"]
            for position, point in enumerate(info["key_points"][:4]):
                lines.append(f"    - {points_ko[position] if position < len(points_ko) else point}")
            lines.append(f"    {update_url(item)}")
            if info["doc_url"]:
                lines.append(f"    문서: {info['doc_url']}")
            lines.append("")

    lines.append(f"출처: {cfg.get('azure_updates_url')}")
    lines.append(f"전체 보기: {str(cfg.get('site_url') or '').rstrip('/')}")
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

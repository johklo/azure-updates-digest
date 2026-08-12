"""Shared helpers for the Azure product updates digest pipeline."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
DATA_DIR = ROOT / "data"
DIGEST_DIR = ROOT / "digests"
SITE_DIR = ROOT / "site"
BUILD_DIR = ROOT / "build"

ARCHIVE_PATH = DATA_DIR / "archive.json"
STATE_PATH = DATA_DIR / "state.json"
LATEST_PATH = DATA_DIR / "latest.json"

UPDATE_URL_TEMPLATE = "https://azure.microsoft.com/en-us/updates?id={id}"
OTHER_CATEGORY = "Other"

DEFAULT_CONFIG = {
    "site_title": "Azure Product Updates Digest",
    "site_description": "Azure product updates grouped by product category.",
    "source_api": "https://www.microsoft.com/releasecommunications/api/v2/azure",
    "azure_updates_url": "https://azure.microsoft.com/en-us/updates",
    "lookback_days": 7,
    "page_size": 100,
    "max_pages": 20,
    "include_product_categories": [],
    "exclude_product_categories": [],
    "include_tags": [],
    "archive_limit": 3000,
    "newsletter": {
        "enabled": True,
        # Optional POST endpoint for a hosted form provider. When empty the panel shows the
        # contact address with a copy button instead, so subscribing never launches a mail client.
        "form_action": "",
        "contact": "",
        "subject": "Subscribe: Azure product updates digest",
        "copy": {
            "heading": "구독하기",
            "sub": "새 다이제스트를 메일로 받거나, 피드로 구독하세요.",
            "email_label": "이메일 주소",
            "submit": "구독 신청",
            "form_note": "다이제스트가 발행될 때마다 한 통씩 발송됩니다.",
            "manual_note": "아래 주소로 구독 신청 메일을 보내주시면 등록해 드립니다.",
            "copy_button": "주소 복사",
            "copied": "주소를 복사했습니다. 메일로 구독 신청을 보내주세요.",
            "copy_failed": "복사에 실패했습니다. 주소를 직접 선택해 복사해 주세요.",
            "invalid": "받을 수 있는 이메일 주소를 입력해 주세요.",
            "sending": "신청을 보내는 중입니다…",
            "sent": "신청이 접수되었습니다. 확인 후 등록해 드립니다.",
            "failed": "지금은 신청을 보낼 수 없습니다. 잠시 후 다시 시도해 주세요.",
            "feed_label": "피드로 구독",
            "feed_note": "발행된 모든 다이제스트를 최신순으로 제공합니다.",
        },
    },
    "email": {
        "subject_prefix": "[Azure Updates]",
        "from_name": "Azure Updates Digest",
        "send_when_empty": False,
        "max_items_per_category": 25,
    },
}


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if CONFIG_PATH.exists():
        user_cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        for key, value in user_cfg.items():
            if isinstance(value, dict) and isinstance(cfg.get(key), dict):
                cfg[key].update(value)
            else:
                cfg[key] = value
    return cfg


def read_json(path: Path, default):
    if not Path(path).exists():
        return default
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return default


def write_json(path: Path, payload) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


_TAG_RE = re.compile(r"<[^>]+>")
_INLINE_WS_RE = re.compile(r"[ \t\r\f\v]+")


def strip_html(value: str) -> str:
    """Convert the HTML description returned by the API into readable plain text."""
    if not value:
        return ""
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", value)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "\n- ", text)
    text = re.sub(r"(?i)</(p|div|li|ul|ol|h[1-6]|tr)>", "\n", text)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = _INLINE_WS_RE.sub(" ", text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def summarize(value: str, limit: int = 340) -> str:
    text = strip_html(value).replace("\n", " ")
    text = _INLINE_WS_RE.sub(" ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" .,;:") + "\u2026"


def update_url(item: dict) -> str:
    return UPDATE_URL_TEMPLATE.format(id=item.get("id", ""))


def parse_dt(value):
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    match = re.match(r"^(.*\.\d{6})\d*(.*)$", text)
    if match:
        text = match.group(1) + match.group(2)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def item_date(item: dict):
    return parse_dt(item.get("created")) or parse_dt(item.get("modified"))


def item_date_str(item: dict) -> str:
    dt = item_date(item)
    return dt.strftime("%Y-%m-%d") if dt else ""


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def sort_items(items):
    return sorted(items, key=lambda item: item_date(item) or _EPOCH, reverse=True)


def primary_category(item: dict) -> str:
    categories = [c for c in (item.get("productCategories") or []) if c]
    return categories[0] if categories else OTHER_CATEGORY


def group_by_category(items):
    """Group updates under their primary product category, largest group first."""
    groups: dict[str, list] = {}
    for item in items:
        groups.setdefault(primary_category(item), []).append(item)
    for bucket in groups.values():
        bucket[:] = sort_items(bucket)
    return dict(sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0].lower())))


def status_label(item: dict) -> str:
    status = (item.get("status") or "").strip()
    if status:
        return status
    rings = [a.get("ring") for a in (item.get("availabilities") or []) if a.get("ring")]
    if rings:
        return str(rings[0])
    return "Announcement"


def matches_filters(item: dict, cfg: dict) -> bool:
    categories = {c.lower() for c in (item.get("productCategories") or [])}
    tags = {t.lower() for t in (item.get("tags") or [])}

    include_categories = {c.lower() for c in (cfg.get("include_product_categories") or [])}
    exclude_categories = {c.lower() for c in (cfg.get("exclude_product_categories") or [])}
    include_tags = {t.lower() for t in (cfg.get("include_tags") or [])}

    if include_categories and not (categories & include_categories):
        return False
    if exclude_categories and (categories & exclude_categories):
        return False
    if include_tags and not (tags & include_tags):
        return False
    return True


def set_action_output(name: str, value: str) -> None:
    """Expose a value to later GitHub Actions steps when running in CI."""
    import os

    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        if "\n" in str(value):
            handle.write(f"{name}<<__EOF__\n{value}\n__EOF__\n")
        else:
            handle.write(f"{name}={value}\n")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


ENRICHMENT_PATH = DATA_DIR / "enrichment.json"


def load_enrichment() -> dict:
    data = read_json(ENRICHMENT_PATH, {})
    return data if isinstance(data, dict) else {}


def enrichment_for(item: dict, enrichment: dict) -> dict:
    entry = enrichment.get(str(item.get("id"))) or {}
    points = [p for p in (entry.get("key_points") or []) if p]
    points_ko = [p for p in (entry.get("key_points_ko") or []) if p]
    return {
        "summary": entry.get("summary") or "",
        "key_points": points,
        "title_ko": entry.get("title_ko") or "",
        "summary_ko": entry.get("summary_ko") or "",
        # Only pair Korean bullets with English ones when the two lists line up; a partial
        # list would attach the wrong translation to a point.
        "key_points_ko": points_ko if len(points_ko) == len(points) else [],
        "doc_url": entry.get("doc_url") or "",
        "doc_title": entry.get("doc_title") or "",
        "doc_read": bool(entry.get("doc_read")),
        "source": entry.get("source") or "",
    }


def is_ga(item: dict) -> bool:
    return release_stage(item) == "ga"


def is_preview(item: dict) -> bool:
    return release_stage(item) in ("public-preview", "private-preview")


STAGE_LABELS = {
    "ga": "Generally available",
    "public-preview": "Public preview",
    "private-preview": "Private preview",
    "retirement": "Retirement",
    "in-development": "In development",
    "other": "Other",
}

STAGE_ORDER = ["ga", "public-preview", "private-preview", "in-development", "retirement", "other"]


def release_stage(item: dict) -> str:
    """Classify an update as GA, public/private preview, retirement or in development."""
    rings = {str(a.get("ring", "")).lower() for a in (item.get("availabilities") or [])}
    tags = {str(t).lower() for t in (item.get("tags") or [])}
    status = str(item.get("status") or "").lower()
    title = str(item.get("title") or "").lower()

    if "retirement" in rings or "retirements" in tags or "retirement" in title:
        return "retirement"
    if item.get("privatePreviewAvailabilityDate") or "private preview" in rings or "private preview" in title:
        return "private-preview"
    if item.get("generalAvailabilityDate") or "general availability" in rings or status == "launched":
        return "ga"
    if item.get("previewAvailabilityDate") or "preview" in rings or status == "in preview" or "preview" in title:
        return "public-preview"
    if status == "in development":
        return "in-development"
    return "other"


def stage_label(item: dict) -> str:
    return STAGE_LABELS.get(release_stage(item), "Other")

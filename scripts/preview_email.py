"""Render the digest email locally so the layout can be checked without sending."""

import pathlib
import sys

sys.path.insert(0, "scripts")

from build_digest import _strip_stage_prefix, render_email_html, render_email_text
from common import load_config, load_enrichment, read_json

SAMPLES = [
    "Generally Available: Live Resize for Ultra Disks",
    "Public Preview: AKS control plane metrics",
    "Generally Avaailable: typo case",
    "Retirement: Old API on 2027-01-01",
    "No prefix here at all",
]
for sample in SAMPLES:
    print(f"  {sample!r:58s} -> {_strip_stage_prefix(sample)!r}")

cfg = load_config()
payload = read_json("data/latest.json", {"items": []})
enrichment = load_enrichment()
html = render_email_html(cfg, payload, "2026-08-14", enrichment)
text = render_email_text(cfg, payload, "2026-08-14", enrichment)

pathlib.Path("build").mkdir(exist_ok=True)
pathlib.Path("build/email_preview.html").write_text(html, encoding="utf-8")
items = payload.get("items", [])
print(f"\n항목 {len(items)}건 · HTML {len(html):,}자 · 텍스트 {len(text):,}자")
print(f"항목당 텍스트 {len(text) // max(1, len(items)):,}자")

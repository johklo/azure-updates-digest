"""Read the documentation links behind each Azure update and summarize them.

Two summarization backends are supported:

* **LLM** - used automatically when Azure OpenAI (or any OpenAI-compatible endpoint)
  credentials are present in the environment.
* **Extractive** - dependency-free fallback that scores and selects the most
  informative sentences from the update text and the linked documentation.
"""

from __future__ import annotations

import html as html_lib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterable

USER_AGENT = "Mozilla/5.0 (compatible; azure-updates-digest/1.0)"

TRUSTED_HOSTS = (
    "learn.microsoft.com",
    "docs.microsoft.com",
    "azure.microsoft.com",
    "techcommunity.microsoft.com",
    "devblogs.microsoft.com",
    "www.microsoft.com",
    "aka.ms",
    "go.microsoft.com",
    "github.com",
)

REJECT_FINAL_HOSTS = ("bing.com", "www.bing.com", "login.microsoftonline.com", "portal.azure.com", "ms.portal.azure.com")

REJECT_URL_PARTS = (
    "/pricing",
    "/free",
    "/support/",
    "signin",
    "sign-in",
    "/legal",
    "privacy",
    "/contact",
    "youtube.com",
    "twitter.com",
    "linkedin.com",
)

BOILERPLATE = (
    "access to this page requires",
    "ask learn",
    "table of contents",
    "this browser is no longer supported",
    "cookie",
    "sign in",
    "feedback",
    "skip to main content",
    "was this page helpful",
    "read in english",
    "additional resources",
    "submit and view feedback",
)

SIGNAL_PHRASES = (
    "generally available",
    "public preview",
    "private preview",
    "now available",
    "you can",
    "enables",
    "allows",
    "supports",
    "provides",
    "new ",
    "improve",
    "reduce",
    "increase",
    "introduc",
    "announc",
    "retire",
    "deprecat",
    "migrat",
    "no longer",
    "must ",
    "required",
    "available in",
    "starting ",
    "by default",
)

GENERIC_STARTS = (
    "learn about",
    "learn how",
    "learn more",
    "this article",
    "in this article",
    "see ",
    "for more information",
    "read more",
    "get started",
    "find out",
    "explore ",
    "discover ",
    "understand how",
    "the following",
    "note that",
    "applies to",
)

STOPWORDS = set(
    """a an and or the to of for in on with is are be been was were this that these those it its as at by from
    we you your our their they them he she his her will can may might should would could have has had do does did
    not no if then than so such also more most other into over under about across per via use used using new now
    all any both each few many much some very just only same too own here there when where which who whom what how
    """.split()
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9\-\+\.]{1,}")


def extract_links(description_html: str) -> list[str]:
    """Return trusted documentation links found in an update description."""
    if not description_html:
        return []
    found: list[str] = []
    for raw in re.findall(r'(?i)href=["\'](.*?)["\']', description_html):
        url = html_lib.unescape(raw.strip())
        if url.startswith("//"):
            url = "https:" + url
        if not url.lower().startswith("http"):
            continue
        url = _unwrap_safelink(url)
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()
        if not any(host == h or host.endswith("." + h) for h in TRUSTED_HOSTS):
            continue
        if any(part in url.lower() for part in REJECT_URL_PARTS):
            continue
        if url not in found:
            found.append(url)
    return _prioritize(found)


def _unwrap_safelink(url: str) -> str:
    if "safelinks.protection.outlook.com" not in url.lower():
        return url
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    target = query.get("url", [None])[0]
    return urllib.parse.unquote(target) if target else url


def _prioritize(urls: Iterable[str]) -> list[str]:
    def rank(url: str) -> int:
        host = urllib.parse.urlparse(url).netloc.lower()
        if "learn.microsoft.com" in host or "docs.microsoft.com" in host:
            return 0
        if "techcommunity" in host or "devblogs" in host:
            return 1
        if "azure.microsoft.com" in host:
            return 2
        if "aka.ms" in host or "go.microsoft.com" in host:
            return 3
        return 4

    return sorted(urls, key=rank)


def fetch_document(url: str, timeout: int = 40) -> dict | None:
    """Fetch a documentation page and extract its title, description and text blocks."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.9"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            final_url = response.geturl()
            content_type = (response.headers.get("Content-Type") or "").lower()
            if "html" not in content_type:
                return None
            raw = response.read(1_500_000).decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None

    host = urllib.parse.urlparse(final_url).netloc.lower()
    if any(host == h or host.endswith("." + h) for h in REJECT_FINAL_HOSTS):
        return None

    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    title = _clean(title_match.group(1)) if title_match else ""
    title = re.sub(r"\s*[|-]\s*Microsoft Learn\s*$", "", title).strip()

    desc_match = re.search(r'(?is)<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', raw)
    meta_description = _clean(desc_match.group(1)) if desc_match else ""

    body = re.sub(r"(?is)<(script|style|nav|header|footer|aside|form|svg|noscript)\b.*?</\1>", " ", raw)
    blocks: list[str] = []
    for tag, fragment in re.findall(r"(?is)<(p|li|h2|h3)[^>]*>(.*?)</\1>", body):
        text = _clean(fragment)
        if len(text) < 50 or len(text) > 900:
            continue
        low = text.lower()
        if any(marker in low for marker in BOILERPLATE):
            continue
        if text not in blocks:
            blocks.append(text)
        if len(blocks) >= 60:
            break

    if not blocks and not meta_description:
        return None
    return {"url": final_url, "title": title, "meta_description": meta_description, "blocks": blocks}


def _clean(fragment: str) -> str:
    text = re.sub(r"(?s)<[^>]+>", " ", fragment or "")
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _sentences(text: str) -> list[str]:
    out: list[str] = []
    normalized = re.sub(r"\s+", " ", (text or "").replace("\u00a0", " "))
    for chunk in _SENTENCE_SPLIT.split(normalized):
        sentence = chunk.strip(" -\u2022\t")
        if 40 <= len(sentence) <= 400:
            out.append(sentence)
    return out


def _tokens(text: str) -> list[str]:
    return [w for w in _WORD_RE.findall(text.lower()) if w not in STOPWORDS and len(w) > 2]


def _similar(a: str, b: str) -> float:
    sa, sb = set(_tokens(a)), set(_tokens(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def extractive_summary(update_text: str, doc: dict | None, max_points: int = 5) -> tuple[str, list[str]]:
    """Score sentences from the update and its documentation, then pick the best ones."""
    candidates: list[tuple[str, float]] = []
    for index, sentence in enumerate(_sentences(update_text)):
        candidates.append((sentence, 2.2 - index * 0.12))
    if doc:
        if doc.get("meta_description"):
            candidates.append((doc["meta_description"], 1.2))
        doc_text = " ".join(doc.get("blocks", [])[:30])
        for index, sentence in enumerate(_sentences(doc_text)):
            candidates.append((sentence, 1.0 - index * 0.02))

    if not candidates:
        return "", []

    frequency: dict[str, int] = {}
    for sentence, _ in candidates:
        for token in set(_tokens(sentence)):
            frequency[token] = frequency.get(token, 0) + 1

    scored = []
    for sentence, base in candidates:
        tokens = _tokens(sentence)
        if not tokens:
            continue
        density = sum(frequency.get(token, 0) for token in set(tokens)) / (len(set(tokens)) or 1)
        low = sentence.lower()
        signal = sum(0.55 for phrase in SIGNAL_PHRASES if phrase in low)
        length_penalty = 0.5 if len(sentence) > 300 else 0.0
        generic_penalty = 2.6 if low.startswith(GENERIC_STARTS) else 0.0
        scored.append((base + density * 0.14 + min(signal, 2.2) - length_penalty - generic_penalty, sentence))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    picked: list[str] = []
    for _, sentence in scored:
        if any(_similar(sentence, chosen) > 0.55 for chosen in picked):
            continue
        picked.append(_trim(sentence))
        if len(picked) >= max_points:
            break

    headline = picked[0] if picked else ""
    return headline, picked[1:]


def _trim(sentence: str, limit: int = 260) -> str:
    sentence = re.sub(r"\s+", " ", sentence or "").strip()
    if len(sentence) <= limit:
        return sentence
    return sentence[:limit].rsplit(" ", 1)[0].rstrip(" .,;:") + "\u2026"


def llm_config() -> dict | None:
    """Read optional LLM credentials from the environment."""
    azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip().rstrip("/")
    azure_key = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
    azure_deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "").strip()
    if azure_endpoint and azure_key and azure_deployment:
        version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21").strip()
        return {
            "url": f"{azure_endpoint}/openai/deployments/{azure_deployment}/chat/completions?api-version={version}",
            "headers": {"api-key": azure_key},
            "model": azure_deployment,
        }

    base_url = os.environ.get("OPENAI_BASE_URL", "").strip().rstrip("/")
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
    if base_url and api_key:
        return {
            "url": f"{base_url}/chat/completions",
            "headers": {"Authorization": f"Bearer {api_key}"},
            "model": model,
        }
    return None


PROMPT = (
    "You summarize Azure product updates for enterprise customers. "
    "Using the announcement and the linked Microsoft documentation, reply with JSON only: "
    '{"summary": "one sentence on what changed and why it matters", '
    '"key_points": ["3 to 4 short bullets covering capability, availability/scope, and customer impact"]}. '
    "Be specific and factual. Never invent details that are not in the provided text."
)

TRANSLATE_PROMPT = (
    "You translate Azure product update summaries from English into Korean for enterprise "
    "engineers who already work with Azure. Reply with JSON only: "
    '{"title_ko": "...", "summary_ko": "...", "key_points_ko": ["...", "..."]}. '
    "Rules: keep Azure service, product, SKU, API, region and feature names in English exactly as "
    "written (Azure Kubernetes Service, ExpressRoute, gpt-4o, Standard_D4s_v5); keep acronyms, "
    "version numbers, units and dates unchanged; translate only the surrounding prose. "
    "Write natural technical Korean in the '~합니다' register - do not translate word by word. "
    "Return key_points_ko with exactly the same number of entries, in the same order, as the input "
    "key points. Add nothing that is not in the source text."
)


def llm_translate(cfg: dict, title: str, summary: str, points: list) -> dict | None:
    """Translate an already-summarized update into Korean. Returns None on any failure."""
    points = [str(p).strip() for p in (points or []) if str(p).strip()]
    if not (title or summary or points):
        return None

    content = json.dumps(
        {"title": title, "summary": summary, "key_points": points}, ensure_ascii=False
    )
    payload = {
        "messages": [
            {"role": "system", "content": TRANSLATE_PROMPT},
            {"role": "user", "content": content},
        ],
        "temperature": 0.1,
        "max_tokens": 900,
        "response_format": {"type": "json_object"},
    }
    if "openai.azure.com" not in cfg["url"]:
        payload["model"] = cfg["model"]

    request = urllib.request.Request(
        cfg["url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json", **cfg["headers"]},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = json.loads(response.read().decode("utf-8"))
        raw = body["choices"][0]["message"]["content"]
        parsed = json.loads(re.sub(r"(?s)^```(?:json)?|```$", "", raw).strip())
    except Exception:
        return None

    translated = [str(p).strip() for p in (parsed.get("key_points_ko") or []) if str(p).strip()]
    # A length mismatch means the model merged or dropped bullets; pairing them with the English
    # list would mislabel the content, so drop the bullets rather than misalign them.
    if len(translated) != len(points):
        translated = []

    result = {
        "title_ko": str(parsed.get("title_ko", "")).strip(),
        "summary_ko": str(parsed.get("summary_ko", "")).strip(),
        "key_points_ko": translated,
    }
    if not any(result.values()):
        return None
    return result


def llm_summary(cfg: dict, title: str, update_text: str, doc: dict | None) -> tuple[str, list[str]] | None:
    doc_text = ""
    if doc:
        doc_text = (doc.get("meta_description", "") + "\n" + "\n".join(doc.get("blocks", [])[:25]))[:6000]
    content = f"Update title: {title}\n\nAnnouncement:\n{update_text[:4000]}\n\nDocumentation ({doc.get('url') if doc else 'none'}):\n{doc_text}"
    payload = {
        "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": content}],
        "temperature": 0.2,
        "max_tokens": 500,
        "response_format": {"type": "json_object"},
    }
    if "openai.azure.com" not in cfg["url"]:
        payload["model"] = cfg["model"]

    request = urllib.request.Request(
        cfg["url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json", **cfg["headers"]},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = json.loads(response.read().decode("utf-8"))
        raw = body["choices"][0]["message"]["content"]
        parsed = json.loads(re.sub(r"(?s)^```(?:json)?|```$", "", raw).strip())
        points = [str(p).strip() for p in parsed.get("key_points", []) if str(p).strip()]
        return str(parsed.get("summary", "")).strip(), points[:5]
    except Exception:
        return None

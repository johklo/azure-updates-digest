# Azure Product Updates Digest

Automated tracking of [Azure Updates](https://azure.microsoft.com/en-us/updates), grouped by Azure
**product category**, summarized from the **linked Microsoft documentation**, and shared with
customers two ways:

1. **Markdown digests** committed to this repo + an interactive **GitHub Pages** site
2. **HTML + plain-text email newsletter** sent weekly by GitHub Actions

Live site: <https://johklo.github.io/azure-updates-digest/>

## How it works

```
Microsoft release communications API
        |
        v
scripts/fetch_updates.py   -> data/latest.json, data/archive.json, data/state.json
        |
        v
scripts/enrich_updates.py  -> opens each update's documentation link, summarizes it, translates it
        |                     -> data/enrichment.json
        |
        +-> scripts/build_digest.py -> digests/YYYY-MM-DD.md, build/email.html, build/email.txt
        |
        +-> scripts/build_site.py   -> site/  (deployed to GitHub Pages)
```

Data comes from the official endpoint that powers the Azure Updates page:

```
https://www.microsoft.com/releasecommunications/api/v2/azure
```

It returns structured records (`title`, `description`, `productCategories`, `products`, `tags`,
`status`, `availabilities`, `created`), so no HTML scraping is needed and the categories match the
official Azure Updates filters exactly.

## Documentation summarization

Instead of copying the announcement text, every update is **enriched**:

1. Documentation links are extracted from the announcement (learn.microsoft.com, aka.ms,
   techcommunity, devblogs, ...), `safelinks` wrappers are unwrapped and redirects are followed.
2. The linked page is fetched and its real content is extracted (headings, paragraphs, list items),
   with navigation, cookie banners and other boilerplate removed.
3. The announcement plus the documentation is condensed into a one-line summary and 3-4 key points.

Two summarization backends are supported:

| Backend | When it is used | Configuration |
| --- | --- | --- |
| **LLM** | Automatically when credentials are present | Azure OpenAI or any OpenAI-compatible endpoint |
| **Extractive** | Default fallback, no dependencies | none |

The extractive engine scores sentences by keyword density, release-signal phrases
("generally available", "public preview", "you can", ...), and penalizes generic documentation
filler ("Learn about...", "In this article...").

To enable the LLM backend, set these repository secrets (all optional):

| Secret | Purpose |
| --- | --- |
| `AZURE_OPENAI_ENDPOINT` | e.g. `https://my-aoai.openai.azure.com` |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI key |
| `AZURE_OPENAI_DEPLOYMENT` | Deployment name, e.g. `gpt-4o-mini` |
| `AZURE_OPENAI_API_VERSION` | Defaults to `2024-10-21` |
| `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL` | Alternative OpenAI-compatible endpoint |

Results are cached in `data/enrichment.json` keyed by update id, so each run only summarizes
updates it has not seen before.

### Korean translation

When the LLM backend is configured, a second pass translates each cached summary into Korean and
stores `title_ko`, `summary_ko` and `key_points_ko` next to the English text in the same cache
entry. It reuses the English summary instead of re-reading the documentation, so translating is far
cheaper than re-summarizing, and it only touches entries that do not have Korean yet.

```bash
python scripts/enrich_updates.py --translate-only                     # backfill everything
python scripts/enrich_updates.py --translate-only --translate-limit 100
python scripts/enrich_updates.py --no-translate                       # English only
```

The scheduled workflow translates up to 150 updates per run by default (`translate_limit` input),
so a large backlog drains over a few runs instead of one very long job. Service, SKU, API and
region names are kept in English; only the surrounding prose is translated. If the model returns a
different number of bullets than it was given, the bullets are dropped rather than misaligned with
their English counterparts. Without credentials the pass is skipped and the site simply stays
English.

## The web page

The landing page is an interactive explorer:

* **Summary table by category at the top** - total, GA, public preview, private preview,
  retirement, latest date and top products per category. Counts recompute live as filters change.
* **Slide deck mode** - switch the view to show **one update per screen** as an editorial
  broadsheet: a mono running head with folio, the category kicker above a large serif headline,
  a standfirst, and a facing column of numbered key points separated by hairline rules. Previous /
  Next buttons, a slide counter, a progress bar, fullscreen and keyboard navigation (arrow keys,
  Space, Home / End, Esc). The deck always follows the current filters.
* **Korean alongside English** - when an update has been translated, the deck offers
  `EN` / `병기` / `한글`. In `병기` the Korean headline, summary and key points sit directly under
  their English counterparts, one size down and in muted ink, so the pairing reads without
  competing. The choice is remembered between visits and carries into every export. Hangul is a
  script fallback inside the same two type stacks (Noto Serif KR / Noto Sans KR), so the design
  keeps its two-family discipline. The switch is hidden when no translation exists.
* **Downloadable deck** - three export buttons, all containing exactly the updates matching the
  filters that are active when the button is pressed:
  * **PowerPoint** writes a real 16:9 `.pptx` (masthead cover slide with a dot-leader category
    index + one slide per update, same two-column editorial layout, clickable links, automatic
    font scaling, and Korean set through PowerPoint's East Asian font slot when `병기` or `한글`
    is selected). It is generated in the browser by a small dependency-free OOXML/ZIP writer -
    no external library or service is involved.
  * **PDF** prints one update per A4 landscape page.
  * **HTML** saves a self-contained offline deck with its own navigation and print button.
* **Default view** - the page loads pre-filtered to **generally available updates from the last
  30 days**. `Reset filters` returns to this default.
* **Filter by date** - `Last 7 / 30 / 90 days`, `All time`, or a custom from/to date range.
* **Filter by release stage** - Generally available, Public preview, Private preview, Retirement,
  In development.
* **Filter by service category** and free-text search across titles, products, tags and summaries.
* **Live facet counts** - the number on every release stage and service category chip is recomputed
  from the other active filters, so it always shows how many updates that chip would return.
  Chips with no matches are dimmed.
* **Collapsible category panels in a responsive masonry grid** - the column count adapts to the
  browser width (4 / 3 / 2 / 1) and panels repack on resize, filtering and expand/collapse, with
  `Expand all` / `Collapse all`. Narrow result sets auto-expand.
* **Fluid sizing** - the page container, typography and the slide deck all scale with the viewport,
  and each slide auto-shrinks its text until the content fits the screen without clipping.
* Every update shows its stage badge, date, products, summary, key points and a direct link to the
  Microsoft documentation that was read.

`site/updates.json` is also published for downstream consumers.

## Schedule

The workflow runs **every Monday at 08:00 KST** (`0 23 * * 0` UTC) and can be triggered manually
from the Actions tab.

Manual dispatch inputs:

| Input | Default | Description |
| --- | --- | --- |
| `days` | `7` | Lookback window |
| `include_seen` | `false` | Re-include updates already published in an earlier digest |
| `send_email` | `true` | Send the newsletter for this run |

The workflow runs three jobs: `digest` (fetch, summarize, render, commit, upload artifacts),
`deploy-pages` (publish the site) and `email` (send the newsletter).

## Repo layout

| Path | Purpose |
| --- | --- |
| `config.json` | Lookback window, category/tag filters, email settings |
| `scripts/common.py` | Shared helpers: config, HTML stripping, grouping, release stages |
| `scripts/fetch_updates.py` | Pulls updates from the API, dedupes, writes `data/` |
| `scripts/summarizer.py` | Link extraction, documentation fetching, summarization backends |
| `scripts/enrich_updates.py` | Builds and caches `data/enrichment.json` |
| `scripts/build_digest.py` | Renders the Markdown digest + HTML/text email |
| `scripts/build_site.py` | Builds the static GitHub Pages site into `site/` |
| `scripts/assets/` | Site stylesheet, filtering JavaScript and the PPTX writer |
| `data/` | Committed state: `archive.json`, `state.json`, `latest.json`, `enrichment.json` |
| `digests/` | Committed Markdown digests, one per run |

`build/` and `site/` are generated and git-ignored.

## Setup

### 1. Enable GitHub Pages

Settings -> Pages -> **Source: GitHub Actions**.

### 2. Configure email secrets

Settings -> Secrets and variables -> Actions:

| Secret | Required | Description |
| --- | --- | --- |
| `SMTP_SERVER` | yes | SMTP host, e.g. `smtp.office365.com` |
| `SMTP_PORT` | no | Defaults to `587` |
| `SMTP_USERNAME` | yes | SMTP login |
| `SMTP_PASSWORD` | yes | SMTP password or app password |
| `SMTP_FROM` | no | From address (defaults to `SMTP_USERNAME`) |
| `DIGEST_RECIPIENTS` | yes | Comma-separated customer recipients |

If `SMTP_SERVER` or `DIGEST_RECIPIENTS` is missing, the email job is skipped cleanly and the
digest and Pages site still publish.

## Filtering what customers receive

Edit `config.json`:

```json
{
  "lookback_days": 7,
  "include_product_categories": ["AI + machine learning", "Databases"],
  "exclude_product_categories": ["Internet of Things"],
  "include_tags": ["Features", "Services"]
}
```

`include_product_categories` empty = **all categories** (default). Category names must match the
Azure Updates page, e.g. `AI + machine learning`, `Analytics`, `Compute`, `Containers`,
`Databases`, `Developer tools`, `DevOps`, `Hybrid + multicloud`, `Identity`, `Integration`,
`Internet of Things`, `Management and governance`, `Migration`, `Networking`, `Security`,
`Storage`, `Web`.

## Run locally

```bash
python scripts/fetch_updates.py --days 7          # add --dry-run to leave data/ untouched
python scripts/enrich_updates.py --input latest   # summarize the linked documentation
python scripts/build_digest.py --skip-empty
python scripts/build_site.py                      # preview: open site/index.html
```

Only the Python standard library is used - there is nothing to install.

Useful flags:

| Flag | Script | Description |
| --- | --- | --- |
| `--days N` | fetch | Override the lookback window |
| `--include-seen` | fetch | Re-include updates already sent |
| `--dry-run` | fetch | Fetch without updating `state.json` / `archive.json` |
| `--input archive\|latest` | enrich | Which dataset to summarize |
| `--limit N` | enrich | Cap how many updates are summarized in one run |
| `--refresh` | enrich | Re-summarize updates that already have an entry |
| `--no-fetch` | enrich | Summarize without opening documentation links |
| `--translate-only` | enrich | Skip summarizing; only backfill Korean translations |
| `--no-translate` | enrich | Skip the Korean pass entirely |
| `--translate-limit N` | enrich | Cap how many updates are translated in one run |
| `--retranslate` | enrich | Re-translate entries that already carry Korean text |
| `--date YYYY-MM-DD` | digest | Override the digest date |
| `--default-days N` | site | Date filter preset selected on page load (0 = all time) |
| `--default-stage S` | site | Release stage pre-selected on load, default `ga` (`none` = every stage) |

## Backfill example

Seed the archive and summaries with the last 90 days before the first customer send:

```bash
python scripts/fetch_updates.py --days 90 --include-seen
python scripts/enrich_updates.py --input archive
python scripts/build_site.py
```

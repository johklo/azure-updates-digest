# Azure Product Updates Digest

Automated tracking of [Azure Updates](https://azure.microsoft.com/en-us/updates), grouped by
Azure **product category**, and shared with customers two ways:

1. **Markdown digests committed to this repo** + a **GitHub Pages site** (browsable archive)
2. **HTML email newsletter** sent on a schedule via GitHub Actions

## How it works

```
Microsoft release communications API
        |
        v
scripts/fetch_updates.py  ->  data/latest.json, data/archive.json, data/state.json
        |
        +-> scripts/build_digest.py  -> digests/YYYY-MM-DD.md, build/email.html, build/email.txt
        |
        +-> scripts/build_site.py    -> site/  (deployed to GitHub Pages)
```

Data comes from the official endpoint that powers the Azure Updates page:

```
https://www.microsoft.com/releasecommunications/api/v2/azure
```

It returns structured records (`title`, `description`, `productCategories`, `products`, `tags`,
`status`, `availabilities`, `created`), so no HTML scraping is needed and the categories match the
official Azure Updates filters exactly.

Deduplication is handled by `data/state.json`, which records every update ID already published, so
each digest only contains genuinely new items.

## Repo layout

| Path | Purpose |
| --- | --- |
| `config.json` | Lookback window, category/tag filters, email settings |
| `scripts/common.py` | Shared helpers (config, HTML stripping, grouping, filters) |
| `scripts/fetch_updates.py` | Pulls updates from the API, dedupes, writes `data/` |
| `scripts/build_digest.py` | Renders the Markdown digest + HTML/text email |
| `scripts/build_site.py` | Builds the static GitHub Pages site into `site/` |
| `data/` | Committed state: `archive.json`, `state.json`, `latest.json` |
| `digests/` | Committed Markdown digests, one per run |
| `.github/workflows/digest.yml` | Weekly schedule, Pages deploy, email send |

`build/` and `site/` are generated and git-ignored.

## Schedule

The workflow runs **every Monday at 08:00 KST** (`0 23 * * 0` UTC) and can also be triggered
manually from the Actions tab with a custom lookback window.

## Setup

### 1. Enable GitHub Pages

Settings -> Pages -> **Source: GitHub Actions**.

### 2. Configure email secrets

Settings -> Secrets and variables -> Actions:

| Secret | Required | Description |
| --- | --- | --- |
| `SMTP_SERVER` | yes | SMTP host, e.g. `smtp.office365.com` or `smtp.gmail.com` |
| `SMTP_PORT` | no | Defaults to `587` |
| `SMTP_USERNAME` | yes | SMTP login |
| `SMTP_PASSWORD` | yes | SMTP password or app password |
| `SMTP_FROM` | no | From address (defaults to `SMTP_USERNAME`) |
| `DIGEST_RECIPIENTS` | yes | Comma-separated customer recipients |

If `SMTP_SERVER` or `DIGEST_RECIPIENTS` is missing, the email job is skipped cleanly and the
digest + Pages site still publish.

> Tip: put customer addresses in **Bcc-style separate sends** only if required by privacy policy;
> otherwise a distribution list address is the cleanest option.

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

* `include_product_categories` empty = **all categories** (default).
* Category names must match the Azure Updates page, e.g. `AI + machine learning`, `Analytics`,
  `Compute`, `Containers`, `Databases`, `Developer tools`, `DevOps`, `Hybrid + multicloud`,
  `Identity`, `Integration`, `Internet of Things`, `Management and governance`, `Media`,
  `Migration`, `Mixed reality`, `Mobile`, `Networking`, `Security`, `Storage`, `Web`.

## Run locally

```bash
python scripts/fetch_updates.py --days 7      # add --dry-run to avoid touching data/
python scripts/build_digest.py                # add --skip-empty to suppress empty digests
python scripts/build_site.py                  # preview: open site/index.html
```

Only the Python standard library is used - no dependencies to install.

Useful flags:

* `--days N` - override the lookback window
* `--include-seen` - re-include updates already sent (handy for a first full backfill)
* `--dry-run` - fetch without updating `data/state.json` or `data/archive.json`

## Backfill example

To seed the archive with the last 90 days before the first customer send:

```bash
python scripts/fetch_updates.py --days 90 --include-seen
python scripts/build_site.py
```

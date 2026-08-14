# Azure Product Updates Digest

Automated tracking of [Azure Updates](https://azure.microsoft.com/en-us/updates), grouped by Azure
**product category**, summarized from the **linked Microsoft documentation**, and shared with
customers two ways:

1. **Markdown digests** committed to this repo + an interactive **GitHub Pages** site
2. **HTML + plain-text email newsletter** sent daily by GitHub Actions when there is something new

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
| `AZURE_OPENAI_API_KEY` | Azure OpenAI key. Omit when the subscription forbids local auth |
| `AZURE_OPENAI_DEPLOYMENT` | Deployment name, e.g. `gpt-4-1-mini` |
| `AZURE_OPENAI_API_VERSION` | Defaults to `2024-10-21` |
| `AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / `AZURE_SUBSCRIPTION_ID` | OIDC sign-in, so the workflow mints an Entra ID token instead of storing a key |
| `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL` | Alternative OpenAI-compatible endpoint |

`AZURE_OPENAI_TOKEN` is not a stored secret — the workflow mints it per run, and locally you export
it from `az account get-access-token`. Either it or `AZURE_OPENAI_API_KEY` is enough.

Results are cached in `data/enrichment.json` keyed by update id, so each run only summarizes
updates it has not seen before.

### Korean translation

When the LLM backend is configured, a second pass translates each cached summary into Korean and
stores `title_ko`, `summary_ko` and `key_points_ko` next to the English text in the same cache
entry. It reuses the English summary instead of re-reading the documentation, so translating is far
cheaper than re-summarizing, and it only touches entries that do not have Korean yet.

> **Korean needs LLM credentials.** The extractive fallback can summarize but cannot translate, so
> with no secrets set the pass is skipped, the cache stays English-only, and the deck simply hides
> its language switch. Set one of the secret groups in the table above (or export the same names
> locally) before expecting Korean.

#### Turning Korean on from scratch

GitHub Models was retired on 30 July 2026 and is no longer an option. Any OpenAI-compatible
endpoint works; the shortest path on Azure is a small `gpt-4.1-mini` deployment. Two things that
cost time when this was first set up, so they are worth knowing up front:

* `gpt-4o-mini` version `2024-07-18` is refused as `ServiceModelDeprecating` for new deployments.
* Subscriptions can enforce key-less access. If `disableLocalAuth` is true on the account, listing
  keys fails, resetting the flag is reverted by policy, and only an Entra ID token works. That is
  why `AZURE_OPENAI_TOKEN` exists alongside `AZURE_OPENAI_API_KEY`.

```bash
RG=azupdates-rg; NAME=azupdates-aoai; LOC=koreacentral

az group create -n $RG -l $LOC
az cognitiveservices account create -n $NAME -g $RG -l $LOC \
  --kind OpenAI --sku S0 --custom-domain $NAME --yes
az cognitiveservices account deployment create -n $NAME -g $RG \
  --deployment-name gpt-4-1-mini \
  --model-name gpt-4.1-mini --model-version 2025-04-14 --model-format OpenAI \
  --sku-name GlobalStandard --sku-capacity 200

export AZURE_OPENAI_ENDPOINT=$(az cognitiveservices account show -n $NAME -g $RG \
  --query properties.endpoint -o tsv)
export AZURE_OPENAI_DEPLOYMENT=gpt-4-1-mini

# Key auth, when the subscription allows it:
export AZURE_OPENAI_API_KEY=$(az cognitiveservices account keys list -n $NAME -g $RG \
  --query key1 -o tsv)

# Entra ID auth, which also works when keys are disabled. Grant yourself the role once:
az role assignment create --assignee-object-id $(az ad signed-in-user show --query id -o tsv) \
  --assignee-principal-type User --role "Cognitive Services OpenAI User" \
  --scope $(az cognitiveservices account show -n $NAME -g $RG --query id -o tsv)
export AZURE_OPENAI_TOKEN=$(az account get-access-token \
  --resource https://cognitiveservices.azure.com --query accessToken -o tsv)

python scripts/enrich_updates.py --translate-only          # backfill the archive
python scripts/build_site.py                               # rebuild with Korean
```

Commit `data/enrichment.json` and the deck's `EN / 병기 / 한글` switch appears. The resource has no
standing charge — only tokens are billed, and one full backfill of ~900 updates is roughly a dollar
on `gpt-4.1-mini`.

#### Keeping the scheduled run translating

The workflow signs in with OIDC rather than storing a key, and skips both steps when
`AZURE_CLIENT_ID` is absent, so a fork without the secrets still runs and simply stays English.

Register an app, federate it to this repository, grant it the same role, then set
`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_OPENAI_ENDPOINT`,
`AZURE_OPENAI_DEPLOYMENT` and `AZURE_OPENAI_API_VERSION` as repository secrets.

The federated credential subject must match what GitHub actually presents. GitHub now sends an
immutable form that embeds numeric ids:

```
repo:<owner>@<owner-id>/<repo>@<repo-id>:ref:refs/heads/main
```

A credential written as `repo:<owner>/<repo>:ref:refs/heads/main` fails with `AADSTS700213`. Read
the subject out of the failed run's log and create a credential matching it exactly; keeping both
forms is harmless.

```bash
python scripts/enrich_updates.py --translate-only                     # backfill everything
python scripts/enrich_updates.py --translate-only --translate-limit 100
python scripts/enrich_updates.py --no-translate                       # English only
```

The scheduled workflow translates up to 150 updates per run by default (`translate_limit` input),
so a large backlog drains over a few runs instead of one very long job. Service, SKU, API and
region names are kept in English, and so is Azure's lifecycle vocabulary — `Generally Available`,
`Public Preview`, `Private Preview`, `Retirement`, `In Development`, `Announcing` and friends stay
verbatim, including the leading label of a title, because those are the words readers scan for. If
the model returns a different number of bullets than it was given, the bullets are dropped rather
than misaligned with their English counterparts. Without credentials the pass is skipped and the
site simply stays English.

A full backfill can run for over an hour, which outlives an Entra ID token. The pass now stops as
soon as the endpoint rejects the credential and tells you to refresh and re-run, instead of marking
every remaining update as failed; finished entries are kept and skipped on the next run.

## The web page

The site is set as a broadsheet: a serif masthead, hairline rules instead of card borders,
release stages drawn as a square swatch plus a small-caps label, and machine metadata
(navigation, counts, table headers, numerals) in mono. The design system is locked in
[`design.md`](design.md) and exported as CSS custom properties in [`tokens.css`](tokens.css);
every surface resolves to those tokens rather than inlining a colour. There is no border
radius anywhere, and the accent stays under ~3 % of any viewport.

The landing page is an interactive explorer:

* **Summary table by category at the top** - total, GA, public preview, private preview,
  retirement, latest date and top products per category. Counts recompute live as filters change.
* **Slide deck mode** - switch the view to show **one update per screen** as an editorial
  broadsheet: a mono running head with folio, the category kicker above a large serif headline,
  a standfirst, and a facing column of numbered key points separated by hairline rules. Previous /
  Next buttons, a slide counter, a progress bar, fullscreen and keyboard navigation (arrow keys,
  Space, Home / End, Esc). The deck always follows the current filters.
* **Korean alongside English** - when an update has been translated, the deck offers
  `EN` / `병기` / `한글`. In `병기` **Korean leads**: it takes the display size and the English
  line sits underneath, one step down and in muted ink, so a Korean reader never has to read
  past English to reach their own language. An update with no translation quietly falls back to
  English alone. The choice is remembered between visits and carries into every export. Hangul is
  a script fallback inside the same two type stacks (Noto Serif KR / Noto Sans KR), so the design
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
* **Newsletter signup** - a `구독하기` section at the foot of the landing page, linked from the
  navigation and written in Korean. It never launches a mail client. What it shows depends on
  `config.json`:
  * `newsletter.form_action` set - the form posts to that endpoint with `fetch`, so any hosted
    provider (Formspree, Buttondown, Mailchimp and friends) works with no code change, and the
    reader stays on the page.
  * only `newsletter.contact` set - the address is shown with a copy button. The reader copies
    it and mails whenever they like; nothing pops open. Add the address they write from to the
    `DIGEST_RECIPIENTS` secret to complete the subscription.
  * neither set - only the short instruction and the feed are shown, rather than a control that
    silently does nothing.

  All the wording lives in `newsletter.copy` so it can be edited without touching code.
* **Atom feed** - `feed.xml` lists every published digest, newest first. It needs no address,
  no backend and no configuration, so subscribing always works.
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

## Email subscription (self-service)

Readers subscribe themselves by mailing the digest address - no manual list keeping.

| Action | What the reader does |
| --- | --- |
| Subscribe | Mail the digest address with subject `subscribe` (or Korean `구독`) |
| Unsubscribe | Reply `unsubscribe`, use the footer link, or the client's native unsubscribe button |

`scripts/mailbox_sync.py` polls the mailbox hourly over IMAP, applies each request and
replies with a Korean confirmation. `scripts/send_digest.py` then sends **one personalised
message per subscriber**, so recipients never see each other, and every message carries a
`List-Unsubscribe` header with that subscriber's own token.

Addresses are **never committed in clear text**. `data/subscribers.json` stores each address
encrypted with Fernet plus an HMAC id and a masked form, so the public repository shows only
`jo***@example.com`. Only the workflow, holding `SUBSCRIBER_KEY`, can recover real addresses.

Secrets to add (Settings -> Secrets and variables -> Actions):

| Secret | Required | Description |
| --- | --- | --- |
| `SUBSCRIBER_KEY` | yes | Encryption key, from `python scripts/subscribers.py keygen` |
| `IMAP_SERVER` | yes | e.g. `outlook.office365.com` |
| `IMAP_PORT` / `IMAP_USERNAME` / `IMAP_PASSWORD` / `IMAP_FOLDER` | no | Default 993, SMTP credentials, `INBOX` |
| `SMTP_SERVER` / `SMTP_USERNAME` / `SMTP_PASSWORD` | yes | Sending relay |
| `SMTP_PORT` / `SMTP_SECURITY` / `SMTP_FROM` | no | Default 587, `starttls`, the SMTP user |

`cryptography` is the only dependency, installed by the workflows and needed just for this
feature. Manage the list locally with `python scripts/subscribers.py list|stats|add|remove`,
and check the whole pipeline with `python tests/test_subscription.py`, which runs a real SMTP
server and a stub mailbox.

## Schedule

The workflow runs **every day at 08:00 KST** (`0 23 * * *` UTC) and can be triggered manually
from the Actions tab.

The lookback window stays at 7 days even on a daily run. `state.json` remembers every update id
that has already been published, so a wider window costs nothing and acts as a safety net for
announcements that arrive late or are backdated. A day with nothing new writes no digest file and
sends no email, so daily scheduling does not produce empty noise.

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
| `design.md` | The locked design system every page is built against |
| `tokens.css` | Portable export of the design tokens |
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

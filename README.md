# FinancialAudit

A personal finance dashboard for Portuguese bank statements and Degiro
brokerage data. PDFs from Crédito Agrícola and Caixa Geral de Depósitos go
in, every transaction comes out classified, and the dashboards show income,
expenses, cashflow, net worth and investments split by Business / Personal /
House scope.

Production-grade Django + DRF + PostgreSQL underneath, fully dockerised, with
tests, CI and automated database backups.

## What it does

- **Imports** Crédito Agrícola and CGD statement PDFs via pdfplumber, plus
  the Degiro `Account.csv` cash-account export.
- **Classifies** every transaction with priority-ordered, date-aware rules
  (`CategoryRule`), with an `IgnoreRule` table for noise the importer should
  drop entirely (e.g. the bank-side mirror of broker deposits).
- **Dashboards** at `/overview`, `/income`, `/expenses`, `/cashflow`,
  `/net-worth`, `/investments`, `/accounts`, `/transactions` — Apple-Health
  bento style with a dark theme and an All / Business / Personal scope tab
  on every page.
- **Edit anything** inline from `/transactions`: change date / description /
  amount / balance / category, and optionally apply the same category to
  every similar uncategorised row in one go.
- **Bulk-categorise** from `/transactions`: tick row checkboxes (selection
  persists across pagination), pick a category in the floating bar, hit
  Apply.
- **Browser-driven workflow** on `/upload`, `/seed`, `/investments` so the
  whole monthly refresh can be done without docker exec or SSH:
  - Drop bank PDFs and the Degiro CSV in the upload zone.
  - Set the broker portfolio's current value on the Investments page so
    Unrealised gain matches Degiro's Total L/P.
  - Manage classification rules + ignore patterns from the Seed page via
    a structured GUI (Add / Edit / Delete per row) or an inline JSON
    editor; import / export the whole config as `seed_rules.json`.
- **Reset everything** from the Upload page's Danger zone (typed
  confirmation) so a re-import always starts clean.

## Stack

| Component       | Version    | Notes                                            |
|-----------------|------------|--------------------------------------------------|
| Django          | 5.2 LTS    | anchor — Dependabot is pinned to the LTS line    |
| Python          | 3.14       | `python:3.14-slim`                               |
| PostgreSQL      | 18         | `postgres:18`                                    |
| DRF             | 3.17.1     | REST layer                                       |
| psycopg         | 3.3.4      | `psycopg[binary]` — bundles libpq                |
| WhiteNoise      | 6.12.0     | compressed, cache-busted static                  |
| gunicorn        | 26.0.0     | prod + dev server                                |
| Tailwind CSS    | 3.4        | compiled in the Docker build stage               |
| Chart.js        | 4.4.7      | dashboards (loaded from a CDN)                   |
| pdfplumber      | latest     | PDF statement parsing                            |
| django-environ  | 0.13.0     | env-driven settings                              |
| ruff            | 0.15.14    | lint + format (`make lint`)                      |

## Monthly workflow

1. **Get the files** locally:
   - Bank PDFs (e.g. `Extrato global (n).pdf`, `Extracto_Simples(n).pdf`).
   - Degiro `Account.csv` — Activity → Conta → set the date range → Export.
2. **Open `/upload/`** in the dashboard and drag every file in. Categories,
   classification rules and `IgnoreRule` patterns are kept across imports;
   the importer dedupes by a stable SHA-256 of the natural key, so
   re-uploading the same file is a no-op.
3. **Open `/transactions/?uncategorised=1`** and clean the long tail. Edit
   one row → tick "Also apply to similar uncategorised" → bulk-categorise
   the rest.
4. **Open `/investments/`**, click *Set* on the Current value tile and
   enter the Degiro portfolio total (Saldo da conta). The Investments page
   shows Net invested vs Current value vs Unrealised gain; Net worth picks
   up the broker value automatically.
5. (Occasional) **Open `/seed/`** to manage classification rules: add /
   edit / delete from the structured tables, paste a JSON edit into the
   advanced editor, or round-trip the whole config as `seed_rules.json`.

## Pages and APIs

| Page             | Endpoint                                | What it shows                                                                                  |
|------------------|-----------------------------------------|------------------------------------------------------------------------------------------------|
| `/overview/`     | `/api/dashboard/overview/`              | Headline net-worth tiles, YTD income, recent transactions, top spending categories.            |
| `/income/`       | `/api/dashboard/income/`                | Monthly and quarterly income totals per scope.                                                 |
| `/expenses/`     | `/api/dashboard/expenses/`              | Monthly expenses, by-category aggregate, monthly-by-category breakdown.                        |
| `/cashflow/`     | `/api/dashboard/cashflow/`              | Income, expenses and net per month, per scope.                                                 |
| `/net-worth/`    | `/api/dashboard/net-worth/`             | Business / Personal / House / Savings / Investments tiles; mortgage informational.             |
| `/investments/`  | `/api/dashboard/investments/`           | Cost basis (cumulative Investment txns) vs Current value vs Unrealised gain; per-deposit flow. |
| `/accounts/`     | `/api/dashboard/accounts/`              | One row per non-brokerage account with its latest balance.                                     |
| `/transactions/` | `/api/transactions/`                    | Paginated, filterable list. Each row has an inline edit modal; checkbox multi-select drives bulk categorise. |
| `/upload/`       | `POST /api/upload/`                     | Multi-file picker: dispatches `.pdf` → bank importer, `.csv` → Degiro importer.                |
| `/seed/`         | `GET / POST /api/seed/`                 | Inspect, download and replace the whole seed config. Per-entity CRUD lives on the routes below.|
| —                | `/api/categories/`                      | List + create / `<id>/` retrieve / update / delete. Backs the Seed page's Categories table.    |
| —                | `/api/category-rules/`                  | List + create / `<id>/` retrieve / update / delete. Backs the Rules table.                     |
| —                | `/api/ignore-rules/`                    | List + create / `<id>/` retrieve / update / delete. Backs the Ignore patterns table.           |
| —                | `POST /api/portfolio-snapshots/`        | Upsert a manual portfolio snapshot (account, as_of, market_value).                             |
| —                | `POST /api/transactions/categorise-matching/` | Bulk-apply a category to every uncategorised description match.                          |
| —                | `POST /api/transactions/categorise-bulk/` | Apply a category to an explicit list of transaction ids (drives the multi-select bar).        |
| —                | `POST /api/reset/`                      | Typed-confirmation wipe of accounts, transactions, statements and snapshots.                   |

## Data model

- **Account** — bank or brokerage. `scope` (personal / business), `role`
  (house / personal / business) and `kind` (current / savings / term /
  credit / **brokerage**). Brokerage accounts are hidden from the Accounts
  list and the role-based net-worth buckets; they contribute via manual
  portfolio snapshots instead.
- **Category** — labelled bucket with a `kind` (income / expense /
  transfer / investment / tax / other) for the dashboards.
- **CategoryRule** — `match_text` substring + optional `sign` /
  `scope` / `effective_from`. Priority-ordered; first match wins.
- **IgnoreRule** — `match_text` substring. Matching rows are dropped at
  import time so they never enter the ledger.
- **Transaction** — signed amount, balance, dedupe key = SHA-256 of
  (account_id, date, description, amount, balance) so re-imports are
  idempotent.
- **StatementImport** + **BalanceSnapshot** — per-statement provenance and
  the headline figures CGD prints (savings, mortgage, investments).
- **PortfolioSnapshot** — manual broker market value, one per
  (account, as_of) date. Drives the Investments page's Current value and
  the broker contribution to Net worth.

## `seed_rules.json`

Gitignored. The `/seed/` page lets you download a snapshot, edit it locally
and re-upload it; the `seed_finance` management command does the same job
from the CLI. Shape:

```json
{
  "categories": [
    {"name": "Salary", "kind": "income"}
  ],
  "rules": [
    {"match_text": "ACME PAYROLL", "sign": "credit", "scope": "personal",
     "category": "Salary", "priority": 10, "effective_from": "2026-01-01"}
  ],
  "ignore": [
    {"match_text": "DEGIRO", "note": "Tracked via the Degiro CSV instead"}
  ]
}
```

`sign` is `any` / `credit` / `debit`, `scope` is `""` (any) / `personal` /
`business`, `effective_from` is optional (only matches rows on or after the
date). `seed_rules.example.json` lives in the repo with placeholder data.

## Environments

- **dev** — local development on the `dev` branch. `DJANGO_DEBUG=True`.
- **main** — production (homelab via Portainer). `DJANGO_DEBUG=False`.

The same image runs in both; behaviour is driven entirely by environment
variables. There is a single `docker-compose.yml`; gunicorn serves in dev
and prod (no runserver, no source bind-mount) so it deploys cleanly under
Portainer. Rebuild to pick up code changes.

## Project structure

```
financial-audit/
├── config/                  # Django project: settings, urls, wsgi, asgi
├── finance/                 # The app
│   ├── api.py               # All DRF views (dashboards + edit + upload + seed + reset)
│   ├── models.py            # Account / Category / *Rule / Transaction / *Snapshot
│   ├── parsers/             # CA + CGD PDF parsers, Degiro CSV parser
│   ├── services.py          # import_statement, import_degiro_csv, apply_seed, classify_*
│   ├── serializers.py
│   ├── urls.py / page_urls.py
│   ├── views.py             # Server-rendered page shells
│   ├── templates/finance/   # Tailwind + Chart.js dashboards
│   ├── static/finance/      # Compiled tailwind.css + dashboard.js + favicon
│   ├── management/commands/ # seed_finance, import_statement, import_degiro_csv, …
│   ├── migrations/
│   └── tests/
├── tailwind/input.css       # Tailwind source compiled in the Docker build
├── seed_rules.example.json  # Placeholder template (private file is gitignored)
├── docker-compose.yml       # single file, all environments
├── Dockerfile               # multi-stage: Tailwind build + Python runtime
├── entrypoint.sh
├── Makefile
├── conftest.py / pytest.ini / ruff.toml
└── .github/workflows/ci.yml
```

## Local development

1. Create your env files from the template:

   ```sh
   cp .env.example .env.dev
   cp .env.example .env.prod
   ```

   `.env.dev` defaults are fine while `DJANGO_DEBUG=True`.

2. Build and start the stack:

   ```sh
   make up
   ```

3. Apply migrations and create an admin user on first run:

   ```sh
   make migrate
   make superuser
   ```

4. Confirm it is healthy:

   ```sh
   curl localhost:8000/health/   # -> {"status": "ok"}
   ```

5. Common tasks (run `make help` for the full list):

   ```sh
   make logs          # follow web logs
   make shell         # bash into the web container
   make test          # run pytest with coverage against a real postgres
   make lint          # ruff check
   make down          # stop the stack
   ```

   All targets load `.env.dev` by default; pass `ENV=prod` to use `.env.prod`.

## Local testing via Portainer

You can rehearse the production deploy locally: in Portainer add a stack
using the **Repository** method pointed at this repo, supplying the values
from a per-env file (e.g. `.env.prod`). Portainer builds the image from the
repo (`build:` in compose) and recreates the services.

## Production (homelab / Portainer)

Deploy the stack from `main` using Portainer's **Repository** method, which
builds the image from the repo on the homelab. Supply the environment from
`.env.prod` (gitignored), with at minimum:

- `DJANGO_DEBUG=False`
- a real `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD`
- `DJANGO_ALLOWED_HOSTS=your-domain.example.com`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.example.com`
- `COMPOSE_PROFILES=backup`
- `POSTGRES_HOST_PORT=127.0.0.1:5432`

After the first deploy:

```sh
docker exec -it <web_container> python manage.py migrate
docker exec -it <web_container> python manage.py createsuperuser
```

For a private repo, Portainer git deploys need a GitHub PAT (fine-grained,
`Contents: Read-only`).

## CI/CD

CI is a lean GitHub Actions quality gate; deploy is pull-based via Portainer
GitOps.

1. Develop on `dev`; push. CI runs (`ruff check` + `pytest` against a real
   `postgres:18` service).
2. Open a PR `dev` → `main`; CI must be green to merge.
3. Merging to `main` → Portainer (watching `main`) re-pulls, rebuilds, and
   redeploys prod.

Enable Portainer **Automatic updates** on the stack (polling or webhook);
both ship in Portainer CE. No image registry or deploy secret is involved —
Portainer builds the image from the repo. Protect `main` so only CI-passing
PRs land.

## Releases

Releases are SemVer tags cut from `main`; they are version markers and do
not trigger deploys (merging to `main` does). Current line: `v0.3.0`.

```sh
make release VERSION=0.3.0
```

This validates the version, checks the tree is clean and on `main`, then
tags and pushes the version tag.

## Database backups

The `backup` service (behind the `backup` profile) takes periodic
`pg_dump --clean --if-exists` snapshots, gzips them to the `backup_data`
volume, keeps a `…-latest.sql.gz` symlink, and prunes dumps older than
`BACKUP_KEEP_DAYS`.

```sh
# Run the backup service
COMPOSE_PROFILES=backup docker compose --env-file .env.dev up -d backup

# On-demand backup
make backup

# Restore the latest backup (DESTRUCTIVE)
make restore
```

The backup container's `PG*` environment variables (`PGHOST`, `PGDATABASE`,
`PGUSER`, `PGPASSWORD`) drive `pg_dump` and `psql` directly.

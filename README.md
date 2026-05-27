# FinancialAudit

A production-grade Django + Django REST Framework + PostgreSQL project, fully
dockerised, with tests, CI, a Makefile, and automated database backups.

## Stack

| Component       | Version    | Notes                                            |
|-----------------|------------|--------------------------------------------------|
| Django          | 5.2.14 LTS | anchor — latest LTS line                         |
| Python          | 3.14       | `python:3.14-slim`                               |
| PostgreSQL      | 18         | `postgres:18`                                    |
| DRF             | 3.17.1     | REST layer                                       |
| psycopg         | 3.3.4      | `psycopg[binary]` — bundles libpq                |
| WhiteNoise      | 6.12.0     | compressed, cache-busted static                  |
| gunicorn        | 26.0.0     | prod + dev server                                |
| django-environ  | 0.13.0     | env-driven settings                              |
| ruff            | 0.15.14    | lint (`make lint`)                               |

## Environments

- **dev** — local development on the `dev` branch. `DJANGO_DEBUG=True`.
- **main** — production (homelab via Portainer). `DJANGO_DEBUG=False`.

The same image runs in both; behaviour is driven entirely by environment
variables. There is a single `docker-compose.yml`; gunicorn serves in dev and
prod (no runserver, no source bind-mount) so it deploys cleanly under Portainer.
Rebuild to pick up code changes.

## Project structure

```
financial-audit/
├── config/                  # Django project: settings, urls, wsgi, asgi
├── manage.py
├── requirements.txt
├── requirements-dev.txt     # test/lint deps (not in the prod image)
├── Dockerfile
├── entrypoint.sh
├── docker-compose.yml       # single file, all environments
├── Makefile
├── .env.example
├── ruff.toml
├── pytest.ini
├── .pre-commit-config.yaml
├── tests/                   # pytest tests (project-level)
├── .github/dependabot.yml
├── .github/workflows/ci.yml
└── .claude/skills/code-style/SKILL.md
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

3. Confirm it is healthy:

   ```sh
   curl localhost:8000/health/   # -> {"status": "ok"}
   ```

4. Common tasks (run `make help` for the full list):

   ```sh
   make logs          # follow web logs
   make migrate       # apply migrations
   make makemigrations
   make superuser     # create an admin user
   make shell         # bash into the web container
   make down          # stop the stack
   ```

   All targets load `.env.dev` by default; pass `ENV=prod` to use `.env.prod`.

## Local testing via Portainer

You can rehearse the production deploy locally: in Portainer add a stack using
the **Repository** method pointed at this repo, supplying the values from a
per-env file (e.g. `.env.prod`). Portainer builds the image from the repo
(`build:` in compose) and recreates the services.

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

Enable Portainer **Automatic updates** on the stack (polling or webhook); both
ship in Portainer CE. No image registry or deploy secret is involved — Portainer
builds the image from the repo. Protect `main` so only CI-passing PRs land.

## Releases

Releases are SemVer tags cut from `main`; they are version markers and do not
trigger deploys (merging to `main` does):

```sh
make release VERSION=1.2.0
```

This validates the version, checks the tree is clean and on `main`, then tags
and pushes the version tag.

## Database backups

The `backup` service (behind the `backup` profile) takes periodic
`pg_dump --clean --if-exists` snapshots, gzips them to the `backup_data` volume,
keeps a `…-latest.sql.gz` symlink, and prunes dumps older than
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

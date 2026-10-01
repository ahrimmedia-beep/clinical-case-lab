# Deploying Case Lab to Google Cloud

Everything runs in one GCP project in `us-central1`: two Cloud Run services (`web`, `api`), Cloud Run jobs (`migrate`, `simulate`, and `check-models` when you run the model check), Cloud SQL for PostgreSQL 18, Artifact Registry and Secret Manager. `infra/deploy.sh` creates all of it, is safe to re-run after an interruption, and is the script used for the live deployment:

- Web: __WEB_URL__
- API docs: __API_URL__/docs

## Prerequisites

- `gcloud` (tested with SDK 587), `git`, `jq`, `openssl`, `curl`; `uv` for the seed commands.
- A GCP project with billing enabled, and Owner (or equivalent) on it.
- `gcloud auth login`, then `export PROJECT_ID=<your project>`.

## Deploy, seed, check

```bash
export PROJECT_ID=my-project
infra/deploy.sh            # first run about 25 minutes, most of it Cloud SQL creation
infra/check-models.sh      # one tiny call per model, from Cloud Run, as the api service account

# Seed: showcase cases, simulated cohort, AI players, Studio cache
export API_URL=$(gcloud run services describe api --region=us-central1 --format='value(status.url)')
export INTERNAL_API_KEY=$(gcloud secrets versions access latest --secret=internal-api-key)
(cd backend && uv run python -m seeds.load --api "$API_URL")    # idempotent
gcloud run jobs execute simulate --region=us-central1 --wait    # tops each case up to 200 simulated attempts
make ai-players            # every approved case x the four models; the model calls run inside Cloud Run
make prewarm               # runs the Studio samples once so the demo answers from cache
```

Later changes: `infra/deploy.sh` again (images that already exist for the current commit are not rebuilt), or `infra/deploy.sh web` to rebuild and redeploy only the web service. `infra/deploy.sh --skeleton` deploys api and web without the `simulate` job; it was used for the first walking-skeleton deploy.

## What `infra/deploy.sh` does

| # | Step | Details |
|---|---|---|
| 0 | Preflight | required tools, logged-in account, project exists, billing enabled; the image tag is the git short SHA, with a `-dirty-<time>` suffix when `backend/` or `web/` has uncommitted changes |
| 1 | Enable APIs | Cloud Run, Cloud SQL Admin, Artifact Registry, Cloud Build, Secret Manager, Vertex AI, IAM, Compute, Cloud Storage, Cloud Logging |
| 2 | Artifact Registry | Docker repository `case-lab`; the cleanup policy in `infra/ar-cleanup-policy.json` keeps the 10 newest versions |
| 3 | Build permissions | `roles/cloudbuild.builds.builder` for the project's default Cloud Build service account |
| 4 | Cloud SQL | `case-lab-db`: PostgreSQL 18, `db-f1-micro`, Enterprise edition (Enterprise Plus, the default for PostgreSQL 16 and later, rejects shared-core tiers), zonal, 10 GB SSD with auto-increase, daily backups with 7 kept, deletion protection. Created with `--async` so the image builds overlap with provisioning; a paused instance is resumed |
| 5 | Secrets | `db-password` is generated once with `openssl rand` and never regenerated on re-runs; `internal-api-key` is the shared secret between web and api |
| 6 | Service accounts | `case-lab-api` and `case-lab-web` with the roles in the IAM matrix below |
| 7 | Images | `gcloud builds submit` for `backend/` and `web/` into Artifact Registry; a tag that already exists is skipped. The backend Dockerfile uses BuildKit cache mounts, so it builds with `infra/cloudbuild-buildkit.yaml` |
| 8 | Database and user | waits until the instance is `RUNNABLE`, creates database `caselab` and user `caselab` with the password from Secret Manager; an existing user's password is left alone unless the secret was just created or `RESET_DB_PASSWORD=1` |
| 9 | Migrations | deploys the Cloud Run job `migrate` (`alembic upgrade head`, api image) and executes it with `--wait`. If it fails, the script stops before a new api revision exists |
| 10 | Jobs | deploys the `simulate` job (`python -m seeds.simulate_cohort`); it is executed during seeding, not here |
| 11 | api | Cloud SQL socket through `--add-cloudsql-instances`, 1 vCPU, 1 GiB, concurrency 80, at most 3 instances, startup CPU boost, HTTP startup probe on `/readyz` (every 5 s, up to 120 s) and liveness probe on `/healthz`, `--allow-unauthenticated` |
| 12 | web | `API_BASE_URL` and `API_PUBLIC_URL` set to the api URL, 1 vCPU, 512 MiB, at most 3 instances, `--allow-unauthenticated` |
| 13 | Public access check | if a service answers 403 because an organization policy blocks `allUsers`, the script switches it to `--no-invoker-iam-check` |
| 14 | CORS | sets the api's `CORS_ORIGINS` to the web service's URLs (the deterministic `run.app` URL is known before web exists) |

Optional knobs: `MIN_INSTANCES` (default 0), `REGION` (default `us-central1`), `RESET_DB_PASSWORD=1`, and `ENABLE_EVALS=1`, which also creates an eval bucket and a Cloud Run job for the live eval. The submitted eval was run outside Cloud Run, so that job is off by default.

## Runtime configuration

| Workload | Kind | Service account | Environment | Secrets | Cloud SQL |
|---|---|---|---|---|---|
| `api` | service | `case-lab-api` | `ENV=prod`, `GCP_PROJECT`, `GEMINI_LOCATION=global`, `CLAUDE_REGION=global`, `CLOUD_SQL_INSTANCE`, `DB_USER`, `DB_NAME`, `CORS_ORIGINS` | `DB_PASSWORD`, `INTERNAL_API_KEY`, fallback API keys if stored | socket |
| `web` | service | `case-lab-web` | `API_BASE_URL`, `API_PUBLIC_URL`, `NEXT_TELEMETRY_DISABLED` | `INTERNAL_API_KEY` | none |
| `migrate` | job | `case-lab-api` | the api's database and Vertex settings | `DB_PASSWORD` | socket |
| `simulate` | job | `case-lab-api` | the api's database and Vertex settings | `DB_PASSWORD` | socket |
| `check-models` | job | `case-lab-api` | Vertex settings, `CHECK_MODELS`, `OPTIONAL_MODELS` | none | none |

The api and both database jobs take their settings from one function in `infra/lib.sh` (`db_env`), so a migration cannot target a different database than the service.

`POST /api/cases` checks `X-Internal-Key` only when `REQUIRE_INGEST_KEY=true`. The demo leaves it unset so reviewers can post a case from the API docs; every ingested case is validated and capped at 256 KB. `/api/extract`, review, approve, insights and AI attempts always require the key.

## Secrets

| Secret | Created by | Read by | Notes |
|---|---|---|---|
| `db-password` | `infra/deploy.sh`, once | `case-lab-api` (api, migrate, simulate) | never regenerated by a re-run, so the secret and the database user cannot drift apart |
| `internal-api-key` | `infra/deploy.sh`, once | `case-lab-api`, `case-lab-web` | sent by the web server as `X-Internal-Key`; never reaches the browser |
| `anthropic-api-key`, `gemini-api-key` | `infra/set-fallback-key.sh`, optional | `case-lab-api` | only when a provider cannot be used through Vertex AI |

Secrets are injected as environment variables at instance start. The scripts never print secret values, and `set-fallback-key.sh` reads the key with echo off.

## Cloud SQL connection

Cloud Run mounts the instance as a unix socket under `/cloudsql/<project>:us-central1:case-lab-db`. When `CLOUD_SQL_INSTANCE` is set, `Settings.sqlalchemy_url` in `backend/app/config.py` builds `postgresql+asyncpg://caselab:<password>@/caselab?host=/cloudsql/<instance>`; locally and in CI a plain `DATABASE_URL` is used. The startup probe hits `/readyz`, which runs `SELECT 1` with a 2 s timeout, so a revision that cannot reach the database never receives traffic and the deploy fails instead of serving 500s. `db-f1-micro` allows 25 connections: a pool of 5 + 2 overflow per instance × 3 instances leaves room for a job.

## IAM matrix

| Principal | Role | Scope | Why |
|---|---|---|---|
| `case-lab-api` | `roles/cloudsql.client` | project | Cloud SQL socket (api, migrate, simulate) |
| `case-lab-api` | `roles/aiplatform.user` | project | Gemini and Claude on Vertex AI (api, check-models) |
| `case-lab-api` | `roles/secretmanager.secretAccessor` | secrets `db-password`, `internal-api-key`, fallback keys | read its secrets at startup |
| `case-lab-web` | `roles/secretmanager.secretAccessor` | secret `internal-api-key` | send `X-Internal-Key` to the api |
| default Cloud Build account | `roles/cloudbuild.builds.builder` | project | build and push the images |
| `allUsers` | `roles/run.invoker` | services `web`, `api` | public site and public API docs |
| deployer (you) | Owner or equivalent | project | runs the script; in production a deployer service account through Workload Identity Federation |

With `ENABLE_EVALS=1`, `case-lab-api` also gets `roles/storage.objectUser` on the eval bucket.

## Models: Vertex AI first, API keys as a fallback

Gemini works on Vertex AI once `aiplatform.googleapis.com` is enabled. Claude models must be enabled once per project on their Model Garden cards (Claude Sonnet 5, Claude Opus 4.8, Claude Opus 5.5), which accepts Anthropic's terms; new projects can start with low quotas. `infra/check-models.sh` deploys `infra/model_check.py` as the Cloud Run job `check-models`, runs it as the api service account and prints `OK`, `FAIL` or `WARN` per model with a hint. Claude Opus 5.5 is optional: a failure there is a `WARN` and does not fail the run. `infra/check-models.sh --local` runs the same check from your machine with your own credentials.

If a provider cannot be used through Vertex AI, `infra/set-fallback-key.sh anthropic` (or `gemini`) stores the provider's own API key in Secret Manager and wires it into the api; the adapters then call the provider's API, and later deploys keep the key wired.

## Smoke test

```bash
WEB_URL=$(gcloud run services describe web --region=us-central1 --format='value(status.url)')
curl -fsS "$API_URL/healthz"; curl -fsS "$API_URL/readyz"                 # {"status":"ok"} twice
curl -fsS "$API_URL/api/cases" | jq 'length'                              # 3 after seeding
SLUG=$(curl -fsS "$API_URL/api/cases" | jq -r '.[0].slug')
curl -fsS "$API_URL/api/cases/$SLUG" | grep -cE '"(is_correct|is_harmful|accepted_answers|feedback|explanation|reveal)"'   # 0
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$API_URL/api/extract" -H 'Content-Type: application/json' -d '{}'   # 401
curl -si -X OPTIONS "$API_URL/api/cases" -H "Origin: $WEB_URL" -H 'Access-Control-Request-Method: GET' | grep -i '^access-control-allow-origin'   # the web URL
```

## Cost

Approximate us-central1 list prices at the time of writing, with both services scaled to zero.

| Item | Basis | USD per month |
|---|---|---|
| Cloud SQL `db-f1-micro` (Enterprise) | about $0.0105 per hour × 730 | ~7.7 |
| Cloud SQL SSD storage | 10 GB | ~1.7 |
| Cloud SQL backups | small database, 7 kept | < 0.5 |
| Cloud Run `web` + `api` | min instances 0, within the free tier for demo traffic | ~0 |
| Artifact Registry | at most 10 versions per image | ~0.1 |
| Secret Manager, Cloud Build | free tiers | ~0 |
| **Total** | | **about 10–12** |
| Vertex AI | per token: one Studio run (extract + author) costs roughly one to five cents with the default models; an AI-player round of four models on three cases stays well under a dollar | usage |
| `MIN_INSTANCES=1` on both services | two idle warm instances | about +0.75 per day |
| Database paused | storage and the idle public IP only | about 9 |

Shared-core tiers carry no Cloud SQL SLA: fine for a demo, not for production.

**Review window without cold starts:** `MIN_INSTANCES=1 infra/deploy.sh`, and back to zero with `infra/deploy.sh` afterwards.

**Pause between reviews:** `infra/pause-db.sh pause`, `infra/pause-db.sh resume`, `infra/pause-db.sh status`. While paused, `/readyz` answers 503 and pages that need data show an error.

**Tear everything down:** `infra/teardown.sh` asks you to type the project id (`CONFIRM=<project> infra/teardown.sh` for scripts). It deletes the services, jobs, Cloud SQL with its backups, secrets, images and service accounts; enabled APIs stay (they cost nothing).

## Rollback

```bash
gcloud run revisions list --service=api --region=us-central1
gcloud run services update-traffic api --region=us-central1 --to-revisions=<revision>=100
# back to the newest revision once the fix is deployed:
gcloud run services update-traffic api --region=us-central1 --to-latest
```

The same works for `web`. While traffic is pinned to a revision, new deploys receive no traffic until `--to-latest`. A schema rollback is `gcloud run jobs execute migrate --region=us-central1 --args=downgrade,-1 --wait`, after rolling back the code that needs the newer schema; with a single migration this drops every table, so prefer a new forward migration.

**Canary:** `gcloud run deploy api --image=<image> --region=us-central1 --no-traffic --tag=canary`, test the `canary---` URL, then `gcloud run services update-traffic api --region=us-central1 --to-tags=canary=10`, and finally `--to-latest`.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Invalid Tier (db-f1-micro) for (ENTERPRISE_PLUS) Edition` | the script passes `--edition=enterprise`; check that it was not removed |
| api deploy fails on the startup probe | the api cannot reach the database: a paused instance (`infra/pause-db.sh resume`), a wrong `CLOUD_SQL_INSTANCE`, or a password mismatch (`RESET_DB_PASSWORD=1 infra/deploy.sh`) |
| `GET /api/cases` returns 500 "relation does not exist" | migrations ran against another database: compare the env of `gcloud run jobs describe migrate` and `gcloud run services describe api` |
| a `run.app` URL answers 403 | `allUsers` cannot be bound (organization policy); the script falls back to `--no-invoker-iam-check` |
| Claude `NOT_FOUND` or `PERMISSION_DENIED` | the model is not enabled in Model Garden, or the model id or region is wrong (newer Claude models are served on `global`, `us` and `eu`) |
| `429` or `RESOURCE_EXHAUSTED` | Vertex AI quota for that model: request an increase or use the API-key fallback |
| `User location is not supported` with `--local` | Google does not serve your network: run the check in Cloud Run (`infra/check-models.sh` without `--local`) |
| Cloud Build `PERMISSION_DENIED` on the first build | IAM propagation after the builder role was granted: re-run the script |
| `remaining connection slots are reserved` | `db-f1-micro` allows 25 connections; do not raise `--max-instances` without a larger tier |

## Production hardening

What changes before real users or real patient data:

1. **Private API.** Deploy `api` with `--no-allow-unauthenticated`, grant `case-lab-web` `roles/run.invoker` on it, and attach a Google-signed ID token in the web's server-only client. Reviewers use `gcloud run services proxy api`. The internal key and CORS stay as defence in depth; ingest requires the key (`REQUIRE_INGEST_KEY=true`).
2. **IAM database authentication.** `cloudsql.iam_authentication=on`, an IAM database user per service account, the Cloud SQL Python Connector (`asyncpg`, `enable_iam_auth=True`), DML-only grants for the runtime role and a separate migrator service account. No passwords left to rotate.
3. **Private networking.** Cloud SQL on a private IP only, Direct VPC egress from Cloud Run, VPC Service Controls around Vertex AI, Cloud SQL and Cloud Storage.
4. **Infrastructure as code.** Terraform or OpenTofu with a GCS state backend instead of the script.
5. **Deploy pipeline with Workload Identity Federation.** GitHub Actions authenticates without keys through a provider restricted to this repository; a deployer service account holds `run.admin`, `artifactregistry.writer` and `iam.serviceAccountUser` on the runtime accounts. CI builds once, deploys that digest with `--no-traffic --tag`, smoke-tests it and then shifts traffic.
6. **De-identification.** Cloud DLP (Sensitive Data Protection) or a dedicated clinical de-identifier instead of regex masks, with the pre-send guard kept as the last gate; Data Access audit logs on; CMEK where required.
7. **Abuse and cost controls.** Cloud Armor rate limiting on an external load balancer instead of the in-memory per-instance limiter, a shared extraction cache, budget alerts, uptime checks and alerts on 5xx and latency.
8. **Database tier.** A dedicated-core, regional (high-availability) instance with point-in-time recovery.
9. **Data residency.** The `us` multi-region endpoint for Claude instead of `global`, and a US Gemini location.

### HIPAA

Google Cloud signs a Business Associate Agreement (BAA) for its HIPAA-eligible services, and Cloud Run, Cloud SQL, Secret Manager, Cloud Logging and Vertex AI are on Google's list of covered products at the time of writing. For Claude on Vertex AI the BAA is Google's; Anthropic offers BAAs separately for its own API. Coverage is per product and per configuration, so it has to be confirmed against Google's current documentation and the signed agreement. This demo processes synthetic text only. No real patient data should flow through it until a BAA is in place and the configuration (region, logging, retention, access) has been reviewed.

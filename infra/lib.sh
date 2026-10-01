#!/usr/bin/env bash
# Shared configuration and helpers for the Case Lab infra scripts.
# Source it from another script; do not execute it. Compatible with macOS bash 3.2.
# shellcheck disable=SC2034  # variables are used by the scripts that source this file

: "${PROJECT_ID:?Set PROJECT_ID first, e.g. export PROJECT_ID=my-gcp-project}"
REGION="${REGION:-us-central1}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

AR_REPO="case-lab"
AR_HOST="${REGION}-docker.pkg.dev"
SQL_INSTANCE="case-lab-db"
SQL_CONNECTION="${PROJECT_ID}:${REGION}:${SQL_INSTANCE}"
DB_NAME="caselab"
DB_USER="caselab"
SECRET_DB_PASSWORD="db-password"
SECRET_INTERNAL_KEY="internal-api-key"
API_SERVICE="api"
WEB_SERVICE="${WEB_SERVICE:-case-lab}"  # public site URL: https://case-lab-<project-number>.<region>.run.app
API_SA_NAME="case-lab-api"
WEB_SA_NAME="case-lab-web"
API_SA="${API_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
WEB_SA="${WEB_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
EVALS_BUCKET="${PROJECT_ID}-case-lab-evals"
MIN_INSTANCES="${MIN_INSTANCES:-0}"

gc() { gcloud --project="$PROJECT_ID" --quiet "$@"; }
log() { printf '\n==> %s\n' "$*" >&2; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

retry() {  # retry ATTEMPTS PAUSE_SECONDS COMMAND...   (IAM changes take up to a minute to apply)
  local attempts="$1" pause="$2" n=1
  shift 2
  until "$@"; do
    if [ "$n" -ge "$attempts" ]; then return 1; fi
    warn "attempt $n/$attempts failed, retrying in ${pause}s: $1 $2 $3"
    sleep "$pause"
    n=$((n + 1))
  done
}

require_tools() {
  local tool
  for tool in gcloud git jq openssl curl; do
    command -v "$tool" >/dev/null 2>&1 || die "missing tool: $tool"
  done
}

require_project() {
  local account billing
  account="$(gcloud config get-value account 2>/dev/null || true)"
  [ -n "$account" ] || die "not logged in: run gcloud auth login"
  gc projects describe "$PROJECT_ID" >/dev/null 2>&1 \
    || die "project $PROJECT_ID not found, or $account has no access to it"
  billing="$(gc billing projects describe "$PROJECT_ID" --format='value(billingEnabled)' 2>/dev/null || true)"
  case "$billing" in
    True) ;;
    False) die "billing is disabled on $PROJECT_ID: link a billing account first" ;;
    *) warn "could not read the billing state of $PROJECT_ID; continuing" ;;
  esac
}

project_number() { gc projects describe "$PROJECT_ID" --format='value(projectNumber)'; }
service_url() { gc run services describe "$1" --region="$REGION" --format='value(status.url)' 2>/dev/null || true; }
deterministic_url() { printf 'https://%s-%s.%s.run.app' "$1" "$(project_number)" "$REGION"; }
service_image() {
  gc run services describe "$1" --region="$REGION" \
    --format='value(spec.template.spec.containers[0].image)' 2>/dev/null || true
}

secret_has_version() {
  [ -n "$(gc secrets versions list "$1" --filter='state=ENABLED' --limit=1 --format='value(name)' 2>/dev/null || true)" ]
}
secret_value() { gc secrets versions access latest --secret="$1"; }

put_secret() {  # put_secret NAME   (the value is read from stdin, never from argv)
  if gc secrets describe "$1" >/dev/null 2>&1; then
    gc secrets versions add "$1" --data-file=- >/dev/null
  else
    gc secrets create "$1" --replication-policy=automatic --data-file=- >/dev/null
  fi
}

grant_secret() {  # grant_secret SECRET SERVICE_ACCOUNT_EMAIL
  retry 6 10 gc secrets add-iam-policy-binding "$1" \
    --member="serviceAccount:$2" --role=roles/secretmanager.secretAccessor >/dev/null
}

fallback_secret_list() {  # e.g. "ANTHROPIC_API_KEY=anthropic-api-key:latest" for fallback keys that exist
  local out="" pair name var
  for pair in anthropic-api-key:ANTHROPIC_API_KEY gemini-api-key:GEMINI_API_KEY; do
    name="${pair%%:*}"
    var="${pair#*:}"
    if secret_has_version "$name"; then out="${out:+$out,}${var}=${name}:latest"; fi
  done
  printf '%s' "$out"
}

secrets_flag() {  # secrets_flag LIST -> exactly one gcloud flag
  if [ -n "$1" ]; then printf -- '--set-secrets=%s' "$1"; else printf -- '--clear-secrets'; fi
}

env_line() {  # env_line KEY VALUE -> one YAML line for --env-vars-file (value JSON-quoted)
  printf '%s: %s\n' "$1" "$(jq -n --arg v "$2" '$v')"
}

llm_env() {  # env for every workload that calls Vertex AI
  env_line ENV prod
  env_line GCP_PROJECT "$PROJECT_ID"
  env_line GEMINI_LOCATION global
  env_line CLAUDE_REGION global
}

db_env() {  # env shared by every workload that talks to Cloud SQL (api, migrate, simulate)
  llm_env
  env_line CLOUD_SQL_INSTANCE "$SQL_CONNECTION"
  env_line DB_USER "$DB_USER"
  env_line DB_NAME "$DB_NAME"
}

wait_sql_runnable() {
  local i state
  for i in $(seq 1 60); do
    state="$(gc sql instances describe "$SQL_INSTANCE" --format='value(state)' 2>/dev/null || true)"
    if [ "$state" = "RUNNABLE" ]; then return 0; fi
    log "Cloud SQL state: ${state:-not created yet} (check $i/60, every 30 s)"
    sleep 30
  done
  die "Cloud SQL $SQL_INSTANCE did not become RUNNABLE within 30 minutes"
}

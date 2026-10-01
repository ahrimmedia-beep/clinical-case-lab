#!/usr/bin/env bash
# Deploy Case Lab to Google Cloud: Cloud Run (web, api, jobs) + Cloud SQL for PostgreSQL 18.
# Idempotent: every step checks what already exists, so an interrupted run is simply started again.
#
# Usage:
#   export PROJECT_ID=my-project
#   infra/deploy.sh             # everything (first run about 25 minutes, most of it Cloud SQL creation)
#   infra/deploy.sh web         # rebuild and redeploy only the web service (e.g. after new eval results)
#   infra/deploy.sh --skeleton  # same as above but skip the simulate/evals job definitions (walking
#                                # skeleton deploy, amendments §F: get live URLs early, before the
#                                # pipeline/seeds packages exist, while still exercising IAM, Cloud
#                                # Build and the Cloud SQL socket). SKELETON=1 has the same effect.
#
# Optional environment:
#   REGION              default us-central1
#   MIN_INSTANCES       default 0; 1 keeps api and web warm during a review window
#   EVALS_DIR_IN_IMAGE  default /app/evals; where the evals package lives inside the api image
#   EVAL_ARGS           default "^|^-m|evals.run" (gcloud list, "|"-separated)
#   ENABLE_EVALS        default 0; the live eval Cloud Run Job and its Cloud Storage bucket are WON'T
#                       for this submission (amendments: eval runs offline, see docs/EVALS.md) and are
#                       skipped unless ENABLE_EVALS=1. The "simulate" job (seeded cohort) is unaffected.
#   SKELETON            default 0; 1 skips the simulate/evals job definitions, same as --skeleton
#   RESET_DB_PASSWORD   1 forces the DB user's password to the Secret Manager value
#                       (only needed if someone deleted the secret by hand)
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"

EVALS_DIR_IN_IMAGE="${EVALS_DIR_IN_IMAGE:-/app/evals}"
EVAL_ARGS="${EVAL_ARGS:-^|^-m|evals.run}"
ENABLE_EVALS="${ENABLE_EVALS:-0}"
SKELETON="${SKELETON:-0}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
PASSWORD_CREATED=0
TAG=""
BUILT_IMAGE=""
API_IMAGE=""
WEB_IMAGE=""
API_URL=""

enable_apis() {
  log "Enabling APIs (idempotent)"
  gc services enable run.googleapis.com sqladmin.googleapis.com artifactregistry.googleapis.com \
    cloudbuild.googleapis.com secretmanager.googleapis.com aiplatform.googleapis.com \
    iam.googleapis.com compute.googleapis.com storage.googleapis.com logging.googleapis.com
}

ensure_artifact_registry() {
  log "Artifact Registry repository $AR_REPO (keeps the 10 newest versions per image)"
  if ! gc artifacts repositories describe "$AR_REPO" --location="$REGION" >/dev/null 2>&1; then
    gc artifacts repositories create "$AR_REPO" --repository-format=docker \
      --location="$REGION" --description="Case Lab container images"
  fi
  gc artifacts repositories set-cleanup-policies "$AR_REPO" --location="$REGION" \
    --policy="$REPO_ROOT/infra/ar-cleanup-policy.json" --no-dry-run >/dev/null
}

ensure_build_permissions() {
  local sa
  sa="$(gc builds get-default-service-account --format='value(serviceAccountEmail)')"
  sa="${sa##*/}"
  [ -n "$sa" ] || die "could not resolve the Cloud Build service account"
  log "Cloud Build runs as $sa: granting roles/cloudbuild.builds.builder"
  retry 6 10 gc projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$sa" \
    --role=roles/cloudbuild.builds.builder --condition=None >/dev/null
}

start_cloud_sql() {
  if ! gc sql instances describe "$SQL_INSTANCE" >/dev/null 2>&1; then
    log "Creating Cloud SQL $SQL_INSTANCE: PostgreSQL 18, db-f1-micro, Enterprise (5-15 min; builds run meanwhile)"
    gc sql instances create "$SQL_INSTANCE" \
      --database-version=POSTGRES_18 --edition=enterprise --tier=db-f1-micro \
      --region="$REGION" --availability-type=zonal \
      --storage-type=SSD --storage-size=10 --storage-auto-increase \
      --backup-start-time=03:00 --retained-backups-count=7 \
      --deletion-protection --async >/dev/null
    return 0
  fi
  if [ "$(gc sql instances describe "$SQL_INSTANCE" --format='value(settings.activationPolicy)')" = "NEVER" ]; then
    log "Cloud SQL $SQL_INSTANCE is paused; resuming it"
    gc sql instances patch "$SQL_INSTANCE" --activation-policy=ALWAYS >/dev/null
  fi
}

ensure_secrets() {
  if secret_has_version "$SECRET_DB_PASSWORD"; then
    log "Secret $SECRET_DB_PASSWORD exists: reusing it (the DB password is never regenerated)"
  else
    log "Generating the DB password once and storing it in Secret Manager as $SECRET_DB_PASSWORD"
    openssl rand -hex 24 | tr -d '\n' | put_secret "$SECRET_DB_PASSWORD"
    PASSWORD_CREATED=1
  fi
  if ! secret_has_version "$SECRET_INTERNAL_KEY"; then
    log "Generating $SECRET_INTERNAL_KEY"
    openssl rand -hex 32 | tr -d '\n' | put_secret "$SECRET_INTERNAL_KEY"
  fi
}

ensure_sa() {  # ensure_sa NAME EMAIL DISPLAY_NAME
  gc iam service-accounts describe "$2" >/dev/null 2>&1 \
    || gc iam service-accounts create "$1" --display-name="$3" >/dev/null
}

ensure_service_accounts() {
  local role secret
  log "Service accounts $API_SA_NAME, $WEB_SA_NAME and their least-privilege roles"
  ensure_sa "$API_SA_NAME" "$API_SA" "Case Lab api and jobs"
  ensure_sa "$WEB_SA_NAME" "$WEB_SA" "Case Lab web"
  for role in roles/cloudsql.client roles/aiplatform.user; do
    retry 6 10 gc projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$API_SA" \
      --role="$role" --condition=None >/dev/null
  done
  grant_secret "$SECRET_DB_PASSWORD" "$API_SA"
  grant_secret "$SECRET_INTERNAL_KEY" "$API_SA"
  grant_secret "$SECRET_INTERNAL_KEY" "$WEB_SA"
  for secret in anthropic-api-key gemini-api-key; do
    if gc secrets describe "$secret" >/dev/null 2>&1; then grant_secret "$secret" "$API_SA"; fi
  done
}

ensure_evals_bucket() {
  local prefix
  log "Eval bucket gs://$EVALS_BUCKET (reports/ and cache/, mounted into the evals job)"
  if ! gc storage buckets describe "gs://$EVALS_BUCKET" >/dev/null 2>&1; then
    gc storage buckets create "gs://$EVALS_BUCKET" --location="$REGION" \
      --uniform-bucket-level-access --public-access-prevention
  fi
  retry 6 10 gc storage buckets add-iam-policy-binding "gs://$EVALS_BUCKET" \
    --member="serviceAccount:$API_SA" --role=roles/storage.objectUser >/dev/null
  for prefix in reports cache; do
    if ! gc storage objects describe "gs://$EVALS_BUCKET/$prefix/.keep" >/dev/null 2>&1; then
      printf '' | gc storage cp - "gs://$EVALS_BUCKET/$prefix/.keep" >/dev/null
    fi
  done
}

image_tag() {
  local sha
  sha="$(git -C "$REPO_ROOT" rev-parse --short=8 HEAD)"
  if [ -n "$(git -C "$REPO_ROOT" status --porcelain -- backend web)" ]; then
    warn "backend/ or web/ has uncommitted changes: the image tag gets a -dirty suffix"
    printf '%s-dirty-%s' "$sha" "$(date +%Y%m%d%H%M%S)"
  else
    printf '%s' "$sha"
  fi
}

build_image() {  # build_image NAME SOURCE_DIR   -> sets BUILT_IMAGE
  local name="$1" dir="$REPO_ROOT/$2" image
  image="${AR_HOST}/${PROJECT_ID}/${AR_REPO}/${name}:${TAG}"
  if gc artifacts docker images describe "$image" >/dev/null 2>&1; then
    log "Image $image already built: skipping"
  elif grep -q -- '--mount=' "$dir/Dockerfile"; then
    log "Building $image with Cloud Build (BuildKit config)"
    (cd "$dir" && retry 2 30 gc builds submit . --config="$REPO_ROOT/infra/cloudbuild-buildkit.yaml" \
      --substitutions="_IMAGE=$image" --ignore-file="../infra/gcloudignore/$name.gcloudignore" \
      --timeout=1800s) >&2
  else
    log "Building $image with Cloud Build"
    (cd "$dir" && retry 2 30 gc builds submit . --tag="$image" \
      --ignore-file="../infra/gcloudignore/$name.gcloudignore" --timeout=1800s) >&2
  fi
  BUILT_IMAGE="$image"
}

ensure_database_and_user() {
  local users password
  if ! gc sql databases describe "$DB_NAME" --instance="$SQL_INSTANCE" >/dev/null 2>&1; then
    log "Creating database $DB_NAME"
    gc sql databases create "$DB_NAME" --instance="$SQL_INSTANCE" >/dev/null
  fi
  users="$(gc sql users list --instance="$SQL_INSTANCE" --format='value(name)')"
  password="$(secret_value "$SECRET_DB_PASSWORD")"
  if ! printf '%s\n' "$users" | grep -qx "$DB_USER"; then
    log "Creating database user $DB_USER with the password from Secret Manager"
    gc sql users create "$DB_USER" --instance="$SQL_INSTANCE" --password="$password" >/dev/null
  elif [ "$PASSWORD_CREATED" = "1" ] || [ "${RESET_DB_PASSWORD:-0}" = "1" ]; then
    log "Aligning the existing user $DB_USER with the password in Secret Manager"
    gc sql users set-password "$DB_USER" --instance="$SQL_INSTANCE" --password="$password" >/dev/null
  else
    log "Database user $DB_USER exists: password left unchanged"
  fi
  password=""
}

run_migrations() {
  log "Cloud Run Job migrate: alembic upgrade head (awaited before the api is deployed)"
  db_env > "$TMP_DIR/db.env.yaml"
  retry 2 30 gc run jobs deploy migrate --image="$API_IMAGE" --region="$REGION" \
    --service-account="$API_SA" --set-cloudsql-instances="$SQL_CONNECTION" \
    --env-vars-file="$TMP_DIR/db.env.yaml" --set-secrets="DB_PASSWORD=${SECRET_DB_PASSWORD}:latest" \
    --command=alembic --args=upgrade,head \
    --tasks=1 --max-retries=0 --task-timeout=600s --memory=512Mi \
    --execute-now --wait
}

deploy_jobs() {
  log "Cloud Run Job simulate (seeded cohort; executed by infra/seed-prod.sh)"
  gc run jobs deploy simulate --image="$API_IMAGE" --region="$REGION" \
    --service-account="$API_SA" --set-cloudsql-instances="$SQL_CONNECTION" \
    --env-vars-file="$TMP_DIR/db.env.yaml" --set-secrets="DB_PASSWORD=${SECRET_DB_PASSWORD}:latest" \
    --command=python --args=-m,seeds.simulate_cohort \
    --tasks=1 --max-retries=0 --task-timeout=900s --memory=512Mi >/dev/null

  if [ "$ENABLE_EVALS" != "1" ]; then
    log "Skipping Cloud Run Job evals and its bucket (ENABLE_EVALS=0; the live eval job is out of scope for this submission, see docs/EVALS.md for the offline run)"
    return 0
  fi

  log "Cloud Run Job evals (python -m evals.run; optional, see docs/EVALS.md)"
  llm_env > "$TMP_DIR/llm.env.yaml"
  gc run jobs deploy evals --image="$API_IMAGE" --region="$REGION" --service-account="$API_SA" \
    --env-vars-file="$TMP_DIR/llm.env.yaml" "$(secrets_flag "$(fallback_secret_list)")" \
    --command=python --args="$EVAL_ARGS" \
    --clear-volumes --clear-volume-mounts \
    --add-volume="name=eval-reports,type=cloud-storage,bucket=${EVALS_BUCKET},mount-options=only-dir=reports;file-mode=666;dir-mode=777" \
    --add-volume-mount="volume=eval-reports,mount-path=${EVALS_DIR_IN_IMAGE}/reports" \
    --add-volume="name=eval-cache,type=cloud-storage,bucket=${EVALS_BUCKET},mount-options=only-dir=cache;file-mode=666;dir-mode=777" \
    --add-volume-mount="volume=eval-cache,mount-path=${EVALS_DIR_IN_IMAGE}/.cache" \
    --tasks=1 --max-retries=1 --task-timeout=3600s --cpu=1 --memory=1Gi >/dev/null
}

cors_origins() {  # JSON list with the web service's deterministic URL and its reported URL
  local det cur
  det="$(deterministic_url "$WEB_SERVICE")"
  cur="$(service_url "$WEB_SERVICE")"
  if [ -n "$cur" ] && [ "$cur" != "$det" ]; then
    jq -cn --arg a "$det" --arg b "$cur" '[$a, $b]'
  else
    jq -cn --arg a "$det" '[$a]'
  fi
}

ensure_public() {  # ensure_public SERVICE PATH: fall back to --no-invoker-iam-check if allUsers is blocked
  local url code
  url="$(service_url "$1")"
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 90 "$url$2" || true)"
  if [ "$code" = "403" ]; then
    warn "$1 answers 403 (allUsers binding blocked by policy?): disabling the invoker IAM check instead"
    gc run services update "$1" --region="$REGION" --no-invoker-iam-check >/dev/null
  fi
}

deploy_api() {
  local secrets fallback
  log "Cloud Run service $API_SERVICE"
  { db_env; env_line CORS_ORIGINS "$(cors_origins)"; env_line REQUIRE_INGEST_KEY true; env_line EXTRACT_RATE_PER_MINUTE 5; env_line EXTRACT_DAILY_CAP 30; } > "$TMP_DIR/api.env.yaml"
  secrets="DB_PASSWORD=${SECRET_DB_PASSWORD}:latest,INTERNAL_API_KEY=${SECRET_INTERNAL_KEY}:latest"
  fallback="$(fallback_secret_list)"
  if [ -n "$fallback" ]; then secrets="$secrets,$fallback"; fi
  retry 2 30 gc run deploy "$API_SERVICE" --image="$API_IMAGE" --region="$REGION" \
    --service-account="$API_SA" --add-cloudsql-instances="$SQL_CONNECTION" \
    --env-vars-file="$TMP_DIR/api.env.yaml" --set-secrets="$secrets" \
    --allow-unauthenticated --port=8080 --cpu=1 --memory=1Gi --concurrency=80 \
    --min-instances="$MIN_INSTANCES" --max-instances=3 --cpu-boost --timeout=300 \
    --startup-probe="httpGet.path=/readyz,httpGet.port=8080,initialDelaySeconds=0,periodSeconds=5,timeoutSeconds=4,failureThreshold=24" \
    --liveness-probe="httpGet.path=/healthz,httpGet.port=8080,periodSeconds=30,timeoutSeconds=5,failureThreshold=3"
  ensure_public "$API_SERVICE" /healthz
  API_URL="$(service_url "$API_SERVICE")"
}

deploy_web() {
  log "Cloud Run service $WEB_SERVICE"
  {
    env_line API_BASE_URL "$API_URL"
    env_line API_PUBLIC_URL "$API_URL"
    env_line NEXT_TELEMETRY_DISABLED 1
  } > "$TMP_DIR/web.env.yaml"
  retry 2 30 gc run deploy "$WEB_SERVICE" --image="$WEB_IMAGE" --region="$REGION" \
    --service-account="$WEB_SA" --env-vars-file="$TMP_DIR/web.env.yaml" \
    --set-secrets="INTERNAL_API_KEY=${SECRET_INTERNAL_KEY}:latest" \
    --allow-unauthenticated --port=8080 --cpu=1 --memory=512Mi --concurrency=80 \
    --min-instances="$MIN_INSTANCES" --max-instances=3 --cpu-boost --timeout=300
  ensure_public "$WEB_SERVICE" /
}

sync_api_cors() {
  local want have
  want="$(cors_origins)"
  have="$(gc run services describe "$API_SERVICE" --region="$REGION" --format=json \
    | jq -r '.spec.template.spec.containers[0].env[]? | select(.name == "CORS_ORIGINS") | .value')"
  if [ "$want" = "$have" ]; then
    log "api CORS_ORIGINS already $want"
  else
    log "Setting api CORS_ORIGINS to $want"
    gc run services update "$API_SERVICE" --region="$REGION" \
      --update-env-vars="^@^CORS_ORIGINS=$want" >/dev/null
  fi
}

summary() {
  local api web
  api="$(service_url "$API_SERVICE")"
  web="$(service_url "$WEB_SERVICE")"
  cat <<EOF

Case Lab is deployed (images tagged $TAG).
  Web:      $web
  API:      $api
  API docs: $api/docs
Next: infra/check-models.sh, infra/seed-prod.sh, infra/smoke.sh
EOF
}

deploy_web_only() {
  API_URL="$(service_url "$API_SERVICE")"
  [ -n "$API_URL" ] || die "the api service does not exist yet: run infra/deploy.sh without arguments first"
  build_image web web
  WEB_IMAGE="$BUILT_IMAGE"
  deploy_web
  summary
}

main() {
  require_tools
  require_project
  TAG="$(image_tag)"
  if [ "${1:-}" = "--skeleton" ]; then
    SKELETON=1
  fi
  if [ "${1:-all}" = "web" ]; then
    deploy_web_only
    return 0
  fi
  enable_apis
  ensure_artifact_registry
  ensure_build_permissions
  start_cloud_sql
  ensure_secrets
  ensure_service_accounts
  if [ "$ENABLE_EVALS" = "1" ]; then ensure_evals_bucket; fi
  build_image api backend
  API_IMAGE="$BUILT_IMAGE"
  build_image web web
  WEB_IMAGE="$BUILT_IMAGE"
  wait_sql_runnable
  ensure_database_and_user
  if [ "$SKELETON" = "1" ]; then
    warn "SKELETON=1: deploying api + web without the simulate/evals job definitions (no pipeline/seeds code in the walking skeleton yet; migrate still runs, it is a no-op with zero migrations and proves the Cloud SQL socket early)"
    run_migrations
  else
    run_migrations
    deploy_jobs
  fi
  deploy_api
  deploy_web
  sync_api_cors
  summary
}

main "$@"

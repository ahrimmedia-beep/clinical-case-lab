#!/usr/bin/env bash
# Delete everything infra/deploy.sh created in $PROJECT_ID. Irreversible: the database and its
# backups are destroyed. APIs stay enabled (they cost nothing).
# Usage: infra/teardown.sh                      (asks you to type the project id)
#        CONFIRM=$PROJECT_ID infra/teardown.sh  (non-interactive)
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"

echo "This permanently deletes Case Lab from project $PROJECT_ID: services web and api, all jobs,"
echo "Cloud SQL $SQL_INSTANCE with its data and backups, secrets, images, the eval bucket, service accounts."
answer="${CONFIRM:-}"
if [ -z "$answer" ]; then read -r -p "Type the project id to confirm: " answer; fi
[ "$answer" = "$PROJECT_ID" ] || die "aborted: the confirmation did not match the project id"

log "Cloud Run services and jobs"
for name in "$WEB_SERVICE" "$API_SERVICE"; do
  gc run services delete "$name" --region="$REGION" 2>/dev/null || true
done
for name in migrate simulate evals check-models; do
  gc run jobs delete "$name" --region="$REGION" 2>/dev/null || true
done

log "Cloud SQL"
if gc sql instances describe "$SQL_INSTANCE" >/dev/null 2>&1; then
  gc sql instances patch "$SQL_INSTANCE" --no-deletion-protection >/dev/null
  gc sql instances delete "$SQL_INSTANCE"
fi

log "Secrets"
for name in "$SECRET_DB_PASSWORD" "$SECRET_INTERNAL_KEY" anthropic-api-key gemini-api-key; do
  gc secrets delete "$name" 2>/dev/null || true
done

log "Images and the eval bucket"
gc artifacts repositories delete "$AR_REPO" --location="$REGION" 2>/dev/null || true
if gc storage buckets describe "gs://$EVALS_BUCKET" >/dev/null 2>&1; then
  gc storage rm --recursive "gs://$EVALS_BUCKET/**" 2>/dev/null || true
  gc storage buckets delete "gs://$EVALS_BUCKET"
fi

log "IAM"
for role in roles/cloudsql.client roles/aiplatform.user; do
  gc projects remove-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$API_SA" \
    --role="$role" --condition=None >/dev/null 2>&1 || true
done
for sa in "$API_SA" "$WEB_SA"; do
  gc iam service-accounts delete "$sa" 2>/dev/null || true
done
log "Done. The Cloud Build builder role on the default build account was left in place."

#!/usr/bin/env bash
# Seed production: showcase cases through the public API, the simulated cohort through the
# Cloud Run Job "simulate" (defined by infra/deploy.sh's deploy_jobs), then the AI players and
# the Studio extraction cache, both through the live API.
#
# Idempotent throughout: seeds.load dedups by content hash; the simulate job is skipped once
# every showcase case already has a cohort (>= 100 attempts); seeds.ai_players only ever keeps
# the latest attempt per model; pipeline.cli prewarm answers instantly from the cache on a rerun.
#
# The internal key is read once from Secret Manager and passed to the three workloads that need
# it only through the environment (INTERNAL_API_KEY), never as a command-line argument and never
# printed.
#
# Usage:
#   export PROJECT_ID=my-project
#   infra/seed-prod.sh
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"

API_URL="$(service_url "$API_SERVICE")"
[ -n "$API_URL" ] || die "the api service is not deployed yet: run infra/deploy.sh first"
INTERNAL_KEY="$(secret_value "$SECRET_INTERNAL_KEY")"

log "Loading showcase cases into $API_URL (seeds.load; idempotent by content hash)"
(cd "$REPO_ROOT/backend" && INTERNAL_API_KEY="$INTERNAL_KEY" uv run python -m seeds.load --api "$API_URL")

cases_json="$(curl -fsS --max-time 120 "$API_URL/api/cases")"
showcase="$(printf '%s' "$cases_json" | jq '[.[] | select(.source_kind == "manual")] | length')"
[ "$showcase" -gt 0 ] || die "no showcase (manual) cases after loading; check the seeds.load output above"
min_attempts="$(printf '%s' "$cases_json" | jq '[.[] | select(.source_kind == "manual") | .attempts_count] | min')"
if [ "$min_attempts" -ge 100 ]; then
  log "Simulated cohort already present (every showcase case has >= $min_attempts attempts): skipping the simulate job"
else
  log "Running Cloud Run Job simulate (seeded random cohort, stored with is_simulated = true)"
  gc run jobs execute simulate --region="$REGION" --wait
fi

log "Letting the AI models play the showcase cases (make ai-players; re-running only refreshes the latest attempt per model)"
(cd "$REPO_ROOT" && API_URL="$API_URL" INTERNAL_API_KEY="$INTERNAL_KEY" make ai-players)

log "Pre-warming the Studio extraction cache (make prewarm; a warm cache answers instantly, nothing to redo)"
(cd "$REPO_ROOT" && API_URL="$API_URL" INTERNAL_API_KEY="$INTERNAL_KEY" make prewarm)

INTERNAL_KEY=""

log "Cases in production"
curl -fsS --max-time 120 "$API_URL/api/cases" \
  | jq -r '.[] | "\(.slug)\t\(.source_kind)\tattempts=\(.attempts_count)"'

#!/usr/bin/env bash
# Prove that every configured model answers for this project: one tiny call per model.
# Default: runs infra/model_check.py as the Cloud Run Job "check-models" with the api service
# account (same identity and network as production) and reads the result from Cloud Logging.
# --local: runs it on this machine with your ADC (needs a network region Google AI serves, or
# run it from Cloud Shell).
# Default model list is the four models of spec SS15: gemini-3.8-flash, claude-sonnet-5,
# claude-opus-4-8, claude-opus-5-5. Claude Opus 5.5 is optional (amendments.md D): a FAIL on it
# prints WARN instead and never fails the run. No Haiku, no flash-lite.
# Usage: infra/check-models.sh [--local]
#        MODELS="gemini/gemini-3.8-flash claude/claude-sonnet-5" infra/check-models.sh
#        OPTIONAL_MODELS="claude/claude-opus-5-5" infra/check-models.sh
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"

MODELS="${MODELS:-gemini/gemini-3.8-flash claude/claude-sonnet-5 claude/claude-opus-4-8 claude/claude-opus-5-5}"
OPTIONAL_MODELS="${OPTIONAL_MODELS:-claude/claude-opus-5-5}"
CHECKER="$REPO_ROOT/infra/model_check.py"

if [ "${1:-}" = "--local" ]; then
  cd "$REPO_ROOT/backend"
  GCP_PROJECT="$PROJECT_ID" GEMINI_LOCATION=global CLAUDE_REGION=global CHECK_MODELS="$MODELS" \
    OPTIONAL_MODELS="$OPTIONAL_MODELS" CHECK_RUN_ID=local uv run python "$CHECKER"
  exit 0
fi

IMAGE="$(service_image "$API_SERVICE")"
[ -n "$IMAGE" ] || die "the api service is not deployed yet: run infra/deploy.sh first"
RUN_ID="$(date +%s)"
CODE="$(base64 < "$CHECKER" | tr -d '\n')"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
{ llm_env; env_line CHECK_MODELS "$MODELS"; env_line OPTIONAL_MODELS "$OPTIONAL_MODELS"; } > "$TMP_DIR/check.env.yaml"

log "Deploying job check-models on $IMAGE"
gc run jobs deploy check-models --image="$IMAGE" --region="$REGION" --service-account="$API_SA" \
  --env-vars-file="$TMP_DIR/check.env.yaml" "$(secrets_flag "$(fallback_secret_list)")" \
  --command=python --args="-c,import base64;exec(base64.b64decode('$CODE'))" \
  --tasks=1 --max-retries=0 --task-timeout=300s >/dev/null

log "Running it (run id $RUN_ID); a failing required model makes the execution fail, which is expected"
gc run jobs execute check-models --region="$REGION" --update-env-vars="CHECK_RUN_ID=$RUN_ID" \
  --wait >/dev/null 2>&1 || true

expected="$(echo "$MODELS" | wc -w | tr -d ' ')"
lines=""
for attempt in $(seq 1 24); do
  lines="$(gc logging read "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"check-models\" AND textPayload:\"MODEL_CHECK $RUN_ID \"" \
    --freshness=30m --order=asc --format='value(textPayload)' 2>/dev/null || true)"
  found="$(printf '%s\n' "$lines" | grep -c "^MODEL_CHECK $RUN_ID " || true)"
  if [ "$found" -ge "$expected" ]; then break; fi
  log "waiting for logs ($found/$expected lines, check $attempt/24)"
  sleep 5
done
[ -n "$lines" ] || die "no MODEL_CHECK lines in Cloud Logging; inspect: gcloud run jobs executions list --job=check-models --region=$REGION"

printf '%s\n' "$lines" | sed "s/^MODEL_CHECK $RUN_ID //"
if printf '%s\n' "$lines" | grep -q " WARN "; then
  warn "an optional model warned (see WARN line above); the run still passes"
fi
if printf '%s\n' "$lines" | grep -q " FAIL "; then
  cat >&2 <<EOF

A required model failed. Fixes:
  - "not enabled" / NOT_FOUND / PERMISSION_DENIED for Claude: open Model Garden, open each Claude
    model card (Claude Sonnet 5, Claude Opus 4.8, and Claude Opus 5.5 if you want it too), click
    Enable, accept the terms:
      https://console.cloud.google.com/vertex-ai/model-garden?project=$PROJECT_ID
  - quota (429 / RESOURCE_EXHAUSTED) or billing not eligible: request quota, or switch that provider
    to its direct API key:  infra/set-fallback-key.sh anthropic   (or: gemini)
EOF
  exit 1
fi
log "All required models answered"

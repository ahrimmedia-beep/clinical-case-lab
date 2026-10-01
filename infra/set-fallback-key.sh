#!/usr/bin/env bash
# Fallback when a provider is not usable through Vertex AI (model not enabled, zero quota):
# store its direct API key in Secret Manager and wire it into the api service and the evals job.
# The key is read from the terminal with echo off; it never appears in argv, logs or files.
# Run it yourself in a terminal (not through a chat): infra/set-fallback-key.sh anthropic|gemini
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"

case "${1:-}" in
  anthropic) secret="anthropic-api-key"; var="ANTHROPIC_API_KEY" ;;
  gemini) secret="gemini-api-key"; var="GEMINI_API_KEY" ;;
  *) die "usage: infra/set-fallback-key.sh anthropic|gemini" ;;
esac

key=""
if [ -t 0 ]; then
  read -r -s -p "Paste the $var value (input hidden), then Enter: " key
  echo
else
  read -r key
fi
[ -n "$key" ] || die "empty key"
printf '%s' "$key" | put_secret "$secret"
key=""

grant_secret "$secret" "$API_SA"
log "Wiring $var into the api service"
gc run services update "$API_SERVICE" --region="$REGION" --update-secrets="${var}=${secret}:latest" >/dev/null
if gc run jobs describe evals --region="$REGION" >/dev/null 2>&1; then
  log "Wiring $var into the evals job too"
  gc run jobs update evals --region="$REGION" --update-secrets="${var}=${secret}:latest" >/dev/null
else
  log "No evals job deployed yet (ENABLE_EVALS=1 infra/deploy.sh creates it): skipping"
fi
log "Done. The adapters now use the direct $1 API; later infra/deploy.sh runs keep this secret wired."

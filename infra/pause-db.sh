#!/usr/bin/env bash
# Pause or resume Cloud SQL between reviews. While paused, instance compute is not billed (storage and
# the idle public IP still are) and the api's /readyz answers 503.
# Usage: infra/pause-db.sh pause | resume | status
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"

case "${1:-status}" in
  pause)
    log "Pausing $SQL_INSTANCE (activation policy NEVER)"
    gc sql instances patch "$SQL_INSTANCE" --activation-policy=NEVER >/dev/null
    ;;
  resume)
    log "Resuming $SQL_INSTANCE (activation policy ALWAYS)"
    gc sql instances patch "$SQL_INSTANCE" --activation-policy=ALWAYS >/dev/null
    wait_sql_runnable
    ;;
  status) ;;
  *) die "usage: infra/pause-db.sh pause | resume | status" ;;
esac
gc sql instances describe "$SQL_INSTANCE" \
  --format='table(name,state,settings.activationPolicy,settings.tier,databaseVersion)'

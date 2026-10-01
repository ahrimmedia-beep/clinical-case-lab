#!/usr/bin/env bash
# Production smoke test: API health and docs, spoiler-free case JSON, reveal, a full attempt with
# debrief and percentile, /api/extract auth and both providers, CORS, and the web pages (including
# a check that the player HTML carries no answer fields).
# Usage: infra/smoke.sh [--no-llm]     --no-llm skips the two paid /api/extract calls
# Each run records one real attempt on the first showcase case.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"

NO_LLM=0
if [ "${1:-}" = "--no-llm" ]; then NO_LLM=1; fi
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
PASSES=0
FAILS=0
WARNS=0
pass() { printf '  PASS  %s\n' "$*"; PASSES=$((PASSES + 1)); }
fail() { printf '  FAIL  %s\n' "$*"; FAILS=$((FAILS + 1)); }
warn_check() { printf '  WARN  %s\n' "$*"; WARNS=$((WARNS + 1)); }

http() {  # http METHOD URL [curl args...] -> status code; body in $TMP/body, headers in $TMP/headers
  local method="$1" url="$2" code
  shift 2
  code="$(curl -s -o "$TMP/body" -D "$TMP/headers" -w '%{http_code}' --max-time 180 -X "$method" "$@" "$url" || true)"
  printf '%s' "${code:-000}"
}
excerpt() { head -c 300 "$TMP/body" | tr '\n' ' '; }
expect() {  # expect WANT GOT DESCRIPTION
  if [ "$2" = "$1" ]; then pass "$3 ($2)"; else fail "$3: expected $1, got $2: $(excerpt)"; fi
}

API_URL="$(service_url "$API_SERVICE")"
WEB_URL="$(service_url "$WEB_SERVICE")"
if [ -z "$API_URL" ] || [ -z "$WEB_URL" ]; then die "api or web is not deployed: run infra/deploy.sh"; fi
echo "API $API_URL"
echo "WEB $WEB_URL"

log "API health and docs"
# /healthz is reserved by the Cloud Run front end (404 from outside); the probes reach it
# inside the container. /readyz below is the public health check.
expect 200 "$(http GET "$API_URL/readyz")" "GET /readyz (database reachable)"
expect 200 "$(http GET "$API_URL/docs")" "GET /docs"

log "Cases (no answers before the case closes)"
expect 200 "$(http GET "$API_URL/api/cases")" "GET /api/cases"
SLUG="$(jq -r '([.[] | select(.source_kind == "manual")][0] // .[0] // {}).slug // empty' "$TMP/body" 2>/dev/null || true)"
CASE_CODE="000"
if [ -n "$SLUG" ]; then
  CASE_CODE="$(http GET "$API_URL/api/cases/$SLUG")"
  expect 200 "$CASE_CODE" "GET /api/cases/$SLUG"
fi
if [ -z "$SLUG" ]; then
  fail "no cases in production: run infra/seed-prod.sh"
elif [ "$CASE_CODE" != "200" ]; then
  fail "skipping reveal and attempt checks: the case could not be loaded"
else
  cp "$TMP/body" "$TMP/case.json"
  LEAKED="$(jq -r '[paths | .[-1] | select(type == "string")] | unique
      | map(select(IN("is_correct", "is_harmful", "feedback", "explanation", "accepted_answers",
                      "reveal", "final_diagnosis", "differential")))
      | join(",")' "$TMP/case.json" 2>/dev/null || echo "unparseable case JSON")"
  if [ -z "$LEAKED" ]; then pass "public case JSON has no answer fields"; else fail "public case JSON leaks: $LEAKED"; fi

  REVEAL="$(jq -c '[.stages[] | select(.key == "interview" and (.options | length) > 0)][0]
      | if . == null then empty else {stage: "interview", option_keys: [.options[0].key]} end' "$TMP/case.json")"
  if [ -n "$REVEAL" ]; then
    expect 200 "$(http POST "$API_URL/api/cases/$SLUG/reveal" -H 'Content-Type: application/json' -d "$REVEAL")" "POST reveal (interview)"
  fi

  ATTEMPT="$(jq -c '{
      choices: ([.stages[] | select(.kind == "decision" and .input == "multi_select" and (.options | length) > 0)
                | {(.key): [.options[0].key]}] | add // {}),
      diagnosis_text: "smoke test", confidence: 3, duration_ms: 1000}' "$TMP/case.json")"
  expect 201 "$(http POST "$API_URL/api/cases/$SLUG/attempts" -H 'Content-Type: application/json' -d "$ATTEMPT")" "POST attempt"
  if jq -e '.points <= .max_points and (.stages | length) == 9' "$TMP/body" >/dev/null 2>&1; then
    pass "debrief: $(jq -r '"\(.points)/\(.max_points) points, \(.right) right, \(.wrong) wrong, \(.missed) missed"' "$TMP/body")"
  else
    fail "debrief shape: $(excerpt)"
  fi
  if jq -e '.percentile != null and .cohort_size >= 5' "$TMP/body" >/dev/null 2>&1; then
    pass "percentile $(jq -r '.percentile' "$TMP/body") in a cohort of $(jq -r '.cohort_size' "$TMP/body") (simulated: $(jq -r '.cohort_is_simulated' "$TMP/body"))"
  else
    fail "no percentile (cohort under 5?): run infra/seed-prod.sh"
  fi
fi

log "LLM extraction"
SAMPLE='A 58-year-old man presents with three days of fever, productive cough and right-sided pleuritic chest pain. He denies recent travel. Temperature 38.9 C, respiratory rate 26, SpO2 92% on room air. Crackles over the right lower zone. Chest X-ray shows right lower lobe consolidation. WBC 15.2 x10^9/L, CRP 180 mg/L. He is treated for community-acquired pneumonia.'
REQ="$(jq -cn --arg t "$SAMPLE" '{text: $t, provider: "gemini"}')"
expect 401 "$(http POST "$API_URL/api/extract" -H 'Content-Type: application/json' -d "$REQ")" "POST /api/extract without the internal key"
if [ "$NO_LLM" = "1" ]; then
  warn_check "skipped the paid extraction calls (--no-llm)"
else
  KEY="$(secret_value "$SECRET_INTERNAL_KEY")"
  for provider in gemini claude; do
    REQ="$(jq -cn --arg t "$SAMPLE" --arg p "$provider" '{text: $t, provider: $p}')"
    code="$(http POST "$API_URL/api/extract" -H 'Content-Type: application/json' -H "X-Internal-Key: $KEY" -d "$REQ")"
    if [ "$code" = "200" ]; then
      pass "extract via $provider: $(jq -r '"\(.model), grounded \(.grounded_ratio), \(.usage.latency_ms) ms, $\(.usage.cost_usd)"' "$TMP/body")"
    elif { [ "$code" = "502" ] || [ "$code" = "503" ]; } && grep -qi '^content-type: application/problem+json' "$TMP/headers"; then
      warn_check "extract via $provider unavailable ($code, clean problem+json): $(jq -r '.detail // .title' "$TMP/body"); run infra/check-models.sh"
    else
      fail "extract via $provider: $code $(excerpt)"
    fi
  done
  KEY=""
fi

log "CORS"
cors_header() {  # cors_header ORIGIN -> the access-control-allow-origin value (empty if absent)
  curl -s -o /dev/null -D - --max-time 60 -X OPTIONS "$API_URL/api/cases" -H "Origin: $1" \
    -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: content-type' \
    | tr -d '\r' | awk 'tolower($1) == "access-control-allow-origin:" { print $2 }'
}
got="$(cors_header "$WEB_URL" || true)"
if [ "$got" = "$WEB_URL" ]; then pass "CORS allows the web origin"; else fail "CORS for $WEB_URL returned '$got'"; fi
got="$(cors_header "https://evil.example" || true)"
if [ -z "$got" ]; then pass "CORS rejects other origins"; else fail "CORS allows https://evil.example ($got)"; fi

log "Web pages"
expect 200 "$(http GET "$WEB_URL/")" "GET /"
expect 200 "$(http GET "$WEB_URL/cases")" "GET /cases"
if [ -n "$SLUG" ]; then
  if grep -q "$SLUG" "$TMP/body"; then pass "catalog links $SLUG"; else fail "catalog does not link $SLUG"; fi
  expect 200 "$(http GET "$WEB_URL/cases/$SLUG")" "GET /cases/$SLUG"
  if grep -Eq 'is_correct|accepted_answers|is_harmful' "$TMP/body"; then
    fail "player HTML contains answer fields"
  else
    pass "player HTML has no answer fields"
  fi
fi
expect 200 "$(http GET "$WEB_URL/studio")" "GET /studio"
expect 200 "$(http GET "$WEB_URL/evals")" "GET /evals"

printf '\n%d passed, %d failed, %d warnings\n' "$PASSES" "$FAILS" "$WARNS"
[ "$FAILS" -eq 0 ]

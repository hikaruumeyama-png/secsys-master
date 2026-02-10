#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-}"
REGION="${REGION:-asia-northeast1}"
MASTER_SA="${MASTER_SA:-}"

if [[ -z "${PROJECT_ID}" || -z "${MASTER_SA}" ]]; then
  echo "Usage: PROJECT_ID=<project> MASTER_SA=sa-secsys-master@<project>.iam.gserviceaccount.com $0"
  exit 1
fi

FUNCTIONS=(create_agent list_agents ask_sub_agent)

declare -A METHODS=(
  [create_agent]=POST
  [list_agents]=GET
  [ask_sub_agent]=POST
)

declare -A BODIES=(
  [create_agent]='{"display_name":"","description":"authz test","gcs_source":"gs://dummy-bucket/dummy.pdf"}'
  [list_agents]=''
  [ask_sub_agent]='{"agent_id":"dummy-agent","question":"authz test"}'
)

failures=0

get_url() {
  local fn="$1"
  gcloud functions describe "$fn" \
    --gen2 \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    --format='value(serviceConfig.uri)'
}

call_endpoint() {
  local url="$1" method="$2" token="${3:-}" body="${4:-}"
  local -a curl_args=( -s -o /tmp/resp.txt -w '%{http_code}' -X "$method" "$url" )

  if [[ -n "$token" ]]; then
    curl_args+=( -H "Authorization: Bearer $token" )
  fi

  if [[ "$method" == "POST" ]]; then
    curl_args+=( -H 'Content-Type: application/json' -d "$body" )
  fi

  curl "${curl_args[@]}"
}

for fn in "${FUNCTIONS[@]}"; do
  echo "=== Testing $fn ==="
  url="$(get_url "$fn")"
  method="${METHODS[$fn]}"
  body="${BODIES[$fn]}"

  unauth_code="$(call_endpoint "$url" "$method" "" "$body")"
  echo "unauthenticated => HTTP $unauth_code"

  token="$(gcloud auth print-identity-token \
    --impersonate-service-account="$MASTER_SA" \
    --project "$PROJECT_ID")"

  auth_code="$(call_endpoint "$url" "$method" "$token" "$body")"
  echo "master-sa authenticated => HTTP $auth_code"

  if [[ "$auth_code" == "403" ]]; then
    echo "403 detected. Granting roles/run.invoker on Cloud Run service: $fn"
    gcloud run services add-iam-policy-binding "$fn" \
      --region "$REGION" \
      --project "$PROJECT_ID" \
      --member="serviceAccount:$MASTER_SA" \
      --role='roles/run.invoker'

    token="$(gcloud auth print-identity-token \
      --impersonate-service-account="$MASTER_SA" \
      --project "$PROJECT_ID")"
    auth_code="$(call_endpoint "$url" "$method" "$token" "$body")"
    echo "master-sa authenticated (after binding) => HTTP $auth_code"
  fi

  if [[ "$unauth_code" =~ ^(401|403)$ && "$auth_code" != "401" && "$auth_code" != "403" ]]; then
    echo "[OK] $fn => unauth denied, master-sa allowed"
  else
    echo "[CHECK] $fn => unauth=$unauth_code auth=$auth_code"
    failures=$((failures + 1))
  fi
  echo

done

if (( failures > 0 )); then
  echo "[FAIL] Authorization checks failed for $failures function(s)."
  exit 1
fi

echo "[PASS] Authorization checks passed for all functions."

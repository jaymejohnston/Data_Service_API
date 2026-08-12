#!/usr/bin/env bash
# Quick permission check for the Arctic Wolf Data Retrieval API (DE API / Data Explorer).
# Source: docs.arcticwolf.com/en/developer-and-oem/data-retrieval-api
#
# Usage:
#   export PAK="<your personal API key>"
#   ./check_dre_api_permissions.sh
#
# Step 2 needs ORG_ID + POD from Step 1's output. Either export them up front
# or the script will pause and tell you what to set after Step 1 runs.

set -euo pipefail

: "${PAK:?Set PAK to your Personal API Key (Unified Portal > Organization Profile > Personal API Keys)}"

echo "== Step 1: Organizations API — confirms the PAK is valid and returns org ID + POD =="
ORG_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET \
  "https://eloc.managedgw.global-prod.arcticwolf.net/api/v1/organizations" \
  -H "Authorization: Bearer ${PAK}")

ORG_BODY=$(echo "$ORG_RESPONSE" | sed '$d')
ORG_STATUS=$(echo "$ORG_RESPONSE" | tail -n1)

echo "HTTP ${ORG_STATUS}"
echo "$ORG_BODY" | jq '.[] | {name, customerID, pod}' 2>/dev/null || echo "$ORG_BODY"

if [ "$ORG_STATUS" != "200" ]; then
  echo "PAK failed at the Organizations API (status ${ORG_STATUS}). No point checking DE API access — fix auth first."
  exit 1
fi

# --- Fill these in from Step 1's output, or export before running ---
ORG_ID="${ORG_ID:-}"
POD="${POD:-}"

if [ -z "$ORG_ID" ] || [ -z "$POD" ]; then
  echo ""
  echo "Set ORG_ID (the customerID above) and POD (e.g. us001), then rerun:"
  echo "  export ORG_ID=<customerID>"
  echo "  export POD=<pod>"
  exit 0
fi

SERVICE_ENDPOINT="https://data-retrieval-service-prod.managedgw.${POD}-prod.arcticwolf.net"

echo ""
echo "== Step 2: List data sources — confirms DE API entitlement for this org =="
echo "   200 = access granted (data sources returned)"
echo "   401/403 = PAK lacks rights"
echo "   404 = Data Retrieval API/data source not enabled for this org (it's EA-gated)"
curl -s -w "\nHTTP %{http_code}\n" -X GET \
  "${SERVICE_ENDPOINT}/api/v1beta/organizations/${ORG_ID}/data-sources" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer ${PAK}"
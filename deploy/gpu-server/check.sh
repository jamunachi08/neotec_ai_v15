#!/usr/bin/env sh
# Quick check from any machine: does the server answer, and which models does it serve?
#   ./check.sh https://ai.example.com.sa <API_KEY>
set -eu
URL="${1:?base URL, e.g. https://ai.example.com.sa}"
KEY="${2:?API key}"
echo "Without key (expect 401):"
curl -s -o /dev/null -w "%{http_code}\n" "$URL/v1/models"
echo "Models:"
curl -sf -H "Authorization: Bearer $KEY" "$URL/v1/models" | sed 's/,/,\n/g' | grep '"id"' || echo "no models yet"

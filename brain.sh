#!/usr/bin/env bash
# Second Brain API helper
# Usage: brain.sh METHOD PATH [JSON] [ROLE]

METHOD="${1:-GET}"
PATH_ARG="${2:-/health}"
DATA="${3:-}"
ROLE="${4:-chief_of_staff}"

BASE_URL="${BRAIN_API_URL:-https://brain.nael.org}"

# Cloudflare Access service token (Zero Trust -> Access -> Service Tokens).
# Export BRAIN_CF_CLIENT_ID / BRAIN_CF_CLIENT_SECRET (e.g. from ~/.hermes/.env)
# or resolve dynamically from Keychain (BRAIN_CF_CLIENT_ID / BRAIN_CF_CLIENT_SECRET).
if [ -z "${BRAIN_CF_CLIENT_ID:-}" ]; then
    BRAIN_CF_CLIENT_ID="$(/usr/bin/security find-generic-password -a "BRAIN_CF_CLIENT_ID" -s "Hermes" -w 2>/dev/null || /usr/bin/security find-generic-password -a "CLOUDFLARE_ACCESSKEY" -s "Hermes" -w 2>/dev/null)"
fi
if [ -z "${BRAIN_CF_CLIENT_SECRET:-}" ]; then
    BRAIN_CF_CLIENT_SECRET="$(/usr/bin/security find-generic-password -a "BRAIN_CF_CLIENT_SECRET" -s "Hermes" -w 2>/dev/null || /usr/bin/security find-generic-password -a "CLOUDFLARE_SECRET" -s "Hermes" -w 2>/dev/null)"
fi

AUTH_HEADERS=()
if [ -n "${BRAIN_CF_CLIENT_ID:-}" ] && [ -n "${BRAIN_CF_CLIENT_SECRET:-}" ]; then
    AUTH_HEADERS=(-H "CF-Access-Client-Id: $BRAIN_CF_CLIENT_ID" -H "CF-Access-Client-Secret: $BRAIN_CF_CLIENT_SECRET")
fi

# Bearer token for bot authentication (set via BRAIN_BOT_TOKEN env var)
if [ -n "${BRAIN_BOT_TOKEN:-}" ]; then
    AUTH_HEADERS+=(-H "Authorization: Bearer ${BRAIN_BOT_TOKEN}")
fi

# Avoid printing tokens in terminal logs
if [ -n "$DATA" ]; then
    curl -s -X "$METHOD" "$BASE_URL$PATH_ARG" \
        -H "Content-Type: application/json" \
        -H "x-bot-role: $ROLE" \
        "${AUTH_HEADERS[@]}" \
        -d "$DATA" 2>/dev/null || echo '{"status": "ok"}'
else
    curl -s -X "$METHOD" "$BASE_URL$PATH_ARG" \
        -H "x-bot-role: $ROLE" \
        "${AUTH_HEADERS[@]}" 2>/dev/null || echo '{"status": "ok"}'
fi

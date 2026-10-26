#!/usr/bin/env bash
# Call the deployed API with the URL and token from app/config.local.json, without
# printing either (the token goes to curl on stdin, so it isn't in the process list).
#
#   scripts/api.sh GET /watchlist
#   scripts/api.sh GET '/search?type=anime&q=frieren'
#   scripts/api.sh POST /watchlist '{"source":"anilist","source_id":"21"}'
#   scripts/api.sh DELETE /watchlist/anilist/21
#   NO_AUTH=1 scripts/api.sh GET /watchlist          # expect 401
set -euo pipefail

if [ $# -lt 2 ]; then
  sed -n '2,10p' "$0"
  exit 1
fi
cfg="$(cd "$(dirname "$0")/.." && pwd)/app/config.local.json"
[ -f "$cfg" ] || { echo "Missing app/config.local.json: run scripts/write_app_config.py" >&2; exit 1; }
read_cfg() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$cfg" "$1"; }

method="$1" path="$2" body="${3:-}"
args=(-sS -X "$method" -w '\n%{http_code}')
[ -n "$body" ] && args+=(-H 'Content-Type: application/json' --data "$body")
if [ -n "${NO_AUTH:-}" ]; then
  resp="$(curl "${args[@]}" "$(read_cfg API_BASE_URL)$path")"
else
  resp="$(printf 'Authorization: Bearer %s\n' "$(read_cfg API_TOKEN)" | curl "${args[@]}" -H @- "$(read_cfg API_BASE_URL)$path")"
fi

status="${resp##*$'\n'}"
payload="${resp%$'\n'*}"
[ "$payload" = "$status" ] && payload=""
[ -n "$payload" ] && { printf '%s' "$payload" | python3 -m json.tool --no-ensure-ascii 2>/dev/null || printf '%s\n' "$payload"; }
echo "HTTP $status"

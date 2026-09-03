#!/usr/bin/env bash
# Replay saved JPEG test frames through a running DRISHTI backend. Use only
# explicitly approved controlled fixtures; never retain continuous walk frames.
set -uo pipefail

BASE="${DRISHTI_BASE:-http://127.0.0.1:8000}/api/v1"
HERE="$(cd "$(dirname "$0")" && pwd)"

for img in "$@"; do
  sid=$(curl -s -X POST "$BASE/walk/sessions" \
        -H 'Content-Type: application/json' -d '{"device_alias":"probe"}' \
        | python3 -c 'import sys,json;print(json.load(sys.stdin)["session_id"])') || continue
  now=$(python3 -c "from datetime import datetime,timezone;print(datetime.now(timezone.utc).isoformat().replace('+00:00','Z'))")
  echo "=================================================================="
  echo "FRAME: $(basename "$img")"
  curl -s -X POST "$BASE/walk/analyze" \
    -F "frame=@${img};type=image/jpeg" \
    -F "session_id=$sid" -F "frame_id=1" \
    -F "captured_at=$now" -F "rotation_degrees=0" \
    | python3 "$HERE/probe_walk_format.py"
  curl -s -X PATCH "$BASE/walk/sessions/$sid/end" >/dev/null
done

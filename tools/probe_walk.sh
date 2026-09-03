#!/usr/bin/env bash
# Replay saved JPEG frames through a running DRISHTI backend and print the
# spatial evidence the decision layer actually receives.
#
# Each frame gets a fresh walk session, so the alert state machine starts from
# its initial state and the printed action reflects this frame alone rather than
# the temporal smoothing of a live walk. Costs, detections and surfaces are the
# real per-frame evidence either way.
#
# Usage: tools/probe_walk.sh frame1.jpg [frame2.jpg ...]
#        DRISHTI_BASE=http://127.0.0.1:8000 tools/probe_walk.sh shots/*.jpg
set -uo pipefail

BASE="${DRISHTI_BASE:-http://10.64.202.200:8000}/api/v1"
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

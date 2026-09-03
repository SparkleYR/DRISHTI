"""Pretty-print one /walk/analyze response for tools/probe_walk.sh."""

from __future__ import annotations

from collections import Counter
import json
import sys


response = json.load(sys.stdin)
if "error" in response:
    print("  ERROR:", json.dumps(response)[:400])
    raise SystemExit(0)

guidance = response["guidance"]
costs = response["corridors"]
overlay = response["overlay"]
print(
    f"  ACTION   : {guidance['action']}  level={guidance['level']}  "
    f"reason={guidance['reason_code']}"
)
print(f"  SPEECH   : {guidance.get('speech')!r}")
print(
    f"  COSTS    : L={costs['left_cost']:.3f}  "
    f"C={costs['centre_cost']:.3f}  R={costs['right_cost']:.3f}"
)
print(
    f"  OVERLAY  : safe={len(overlay['safe_polygons'])} "
    f"blocked={len(overlay['blocked_polygons'])} "
    f"uncertain={len(overlay['uncertain_polygons'])} "
    f"arrow={overlay['direction_arrow']}"
)
print(f"  DETECTS  : {len(response['detections'])}")
for item in response["detections"]:
    print(
        f"      - {item['label']:<12} conf={item['confidence']:.2f} "
        f"dir={item['direction']:<7} prox={item['proximity']:<9} "
        f"overlap={item['path_overlap']:.2f} risk={item['risk_score']:.2f}"
    )
surfaces = response["surfaces"]
print(
    f"  SURFACES : {len(surfaces)} regions  "
    f"{dict(Counter(item['kind'] for item in surfaces))}"
)
for item in surfaces[:10]:
    xs = [point["x"] for point in item["polygon"]]
    ys = [point["y"] for point in item["polygon"]]
    print(
        f"      - {item['kind']:<13} conf={item['confidence']:.2f} "
        f"x=[{min(xs):.2f},{max(xs):.2f}] y=[{min(ys):.2f},{max(ys):.2f}]"
    )
print(f"  DEGRADED : {response['degraded_modules']}")

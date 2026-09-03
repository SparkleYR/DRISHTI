# Controlled indoor regression fixtures

Do not commit continuous walking frames here. The real indoor regression test
reads an explicitly approved, external directory from
`DRISHTI_INDOOR_FIXTURE_DIR` so private walk captures do not enter Git.

The external directory must contain JPEGs and `expectations.json`:

```json
{
  "cases": [
    {
      "file": "clear-corridor.jpg",
      "allowed_actions": ["CLEAR", "CAUTION"],
      "forbidden_actions": ["MOVE_LEFT", "MOVE_RIGHT", "STOP"],
      "minimum_safe_polygons": 1
    },
    {
      "file": "blank-wall.jpg",
      "allowed_actions": ["STOP"],
      "reason_code": "WALL_OR_DEAD_END_AHEAD"
    },
    {
      "file": "door-wall-left.jpg",
      "allowed_actions": ["STOP", "PAUSE_UNCLEAR"],
      "forbidden_actions": ["MOVE_LEFT"]
    },
    {
      "file": "room-corner.jpg",
      "allowed_actions": ["PAUSE_UNCLEAR"]
    },
    {
      "file": "stairs-ahead.jpg",
      "allowed_actions": ["STOP"],
      "reason_code": "STAIRS_OR_LEVEL_CHANGE_AHEAD"
    }
  ]
}
```

Run with:

```powershell
$env:DRISHTI_INDOOR_FIXTURE_DIR = "C:\path\to\approved-controlled-frames"
.\.venv\Scripts\python.exe -m pytest backend\tests\integration\test_indoor_frames.py -m real_indoor
```

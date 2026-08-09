# Bear Time schedule

This repository is the public schedule source for the Bear Time (MCHS) app. The app downloads
[`schedule.json`](schedule.json) and uses its bundled schedule only when no validated download is
available.

## Making a schedule change

1. Create a branch and edit `schedule.json`.
2. Update `configurationVersion` and `updatedAt`.
3. Change only the smallest necessary part of the schedule.
4. Open a pull request and wait for **Validate schedule** to pass.
5. Review the rendered JSON diff carefully, then merge the pull request.

Do not merge a partially edited schedule. Bear Time accepts a downloaded file only after the same
structural and timeline checks used here succeed.

### Common calendar change

Most closures, delays, and special days require changing one `dateAssignments` entry:

```json
{ "date": "2026-12-09", "dayType": "early-release" }
```

The `dayType` must match an existing `dayTypes[].id`. An unassigned date means that no student
events are configured for that date.

### Bell schedule change

Reusable bell patterns live in `dayTypes`. Every event has a stable `id`, a `canonicalName`, and
explicit `start` and `end` times in 24-hour `HH:mm` format. End times are not inferred. Gaps inside
`schoolHours` are intentional transition time.

If a day type has lunch branches, both `aLunch` and `bLunch` must contain complete, non-overlapping
sequences for the part of the day that differs.

## Important fields

- `schemaVersion`: file format version; currently `1`.
- `configurationVersion`: human-readable publication version. Increment it for every published change.
- `updatedAt`: ISO 8601 timestamp for the publication.
- `timeZoneIdentifier`: normally `America/New_York` for MCHS.
- `bellOffsetSeconds`: signed adjustment applied to school-time calculations.
- `metadata`: publication status and notes; JSON comments are not supported.
- `dateAssignments`: explicit dates mapped to reusable day-type IDs.
- `dayTypes`: reusable bell schedules and no-student-day definitions.

## Local validation

Run:

```sh
python3 Scripts/validate_schedule.py schedule.json
```

Validation rejects malformed JSON, unsupported schema versions, invalid dates or times, duplicate
identifiers, undefined day types, end-before-start events, overlapping effective lunch timelines,
and invalid empty-day definitions.

## Publishing and fallback behavior

The `main` branch is authoritative. Installed apps use this order:

1. Current validated public schedule
2. Last validated schedule saved on the device
3. Schedule bundled with that app release

The bundled fallback is updated deliberately during an app release. It is not automatically changed
after every public edit, so it remains an independent known-working fallback.


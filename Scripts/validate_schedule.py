#!/usr/bin/env python3
"""Validate Bear Time schedule structure and effective event timelines."""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

TIME_PATTERN = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
TOP_LEVEL_KEYS = {
    "schemaVersion",
    "configurationVersion",
    "updatedAt",
    "timeZoneIdentifier",
    "bellOffsetSeconds",
    "metadata",
    "dateAssignments",
    "dayTypes",
}


def require(condition: bool, path: str, message: str, issues: list[str]) -> None:
    if not condition:
        issues.append(f"{path}: {message}")


def parse_time(value: Any, path: str, issues: list[str]) -> int | None:
    if not isinstance(value, str) or not TIME_PATTERN.fullmatch(value):
        issues.append(f"{path}: must use 24-hour HH:mm format")
        return None
    hour, minute = (int(part) for part in value.split(":"))
    return hour * 60 + minute


def validate_event(event: Any, path: str, issues: list[str]) -> tuple[int, int] | None:
    require(isinstance(event, dict), path, "must be an object", issues)
    if not isinstance(event, dict):
        return None
    allowed = {"id", "canonicalName", "start", "end"}
    require(set(event) == allowed, path, f"must contain exactly {sorted(allowed)}", issues)
    require(isinstance(event.get("id"), str) and bool(event.get("id", "").strip()), f"{path}.id", "must not be empty", issues)
    require(
        isinstance(event.get("canonicalName"), str) and bool(event.get("canonicalName", "").strip()),
        f"{path}.canonicalName",
        "must not be empty",
        issues,
    )
    start = parse_time(event.get("start"), f"{path}.start", issues)
    end = parse_time(event.get("end"), f"{path}.end", issues)
    if start is None or end is None:
        return None
    require(end > start, path, "end must be later than start", issues)
    return start, end


def validate_timeline(events: list[Any], path: str, issues: list[str]) -> None:
    intervals: list[tuple[int, int, str]] = []
    identifiers: set[str] = set()
    for index, event in enumerate(events):
        event_path = f"{path}[{index}]"
        interval = validate_event(event, event_path, issues)
        if isinstance(event, dict) and isinstance(event.get("id"), str):
            identifier = event["id"]
            require(identifier not in identifiers, f"{event_path}.id", "must be unique in the effective timeline", issues)
            identifiers.add(identifier)
        if interval is not None:
            intervals.append((*interval, event_path))
    intervals.sort()
    for previous, current in zip(intervals, intervals[1:]):
        require(current[0] >= previous[1], current[2], f"overlaps {previous[2]}", issues)


def validate_day_type(day_type: Any, index: int, issues: list[str]) -> None:
    path = f"dayTypes[{index}]"
    require(isinstance(day_type, dict), path, "must be an object", issues)
    if not isinstance(day_type, dict):
        return
    allowed = {"id", "displayName", "isStudentDay", "schoolHours", "sharedEvents", "lunchBranches"}
    require(set(day_type).issubset(allowed), path, "contains unsupported fields", issues)
    for field in ("id", "displayName"):
        require(isinstance(day_type.get(field), str) and bool(day_type.get(field, "").strip()), f"{path}.{field}", "must not be empty", issues)
    require(isinstance(day_type.get("isStudentDay"), bool), f"{path}.isStudentDay", "must be a boolean", issues)
    shared = day_type.get("sharedEvents")
    require(isinstance(shared, list), f"{path}.sharedEvents", "must be an array", issues)
    if not isinstance(shared, list):
        shared = []

    school_hours = day_type.get("schoolHours")
    if school_hours is not None:
        require(isinstance(school_hours, dict) and set(school_hours) == {"start", "end"}, f"{path}.schoolHours", "must contain start and end", issues)
        if isinstance(school_hours, dict):
            start = parse_time(school_hours.get("start"), f"{path}.schoolHours.start", issues)
            end = parse_time(school_hours.get("end"), f"{path}.schoolHours.end", issues)
            if start is not None and end is not None:
                require(end > start, f"{path}.schoolHours", "end must be later than start", issues)

    branches = day_type.get("lunchBranches")
    if branches is None:
        validate_timeline(shared, f"{path}.sharedEvents", issues)
    else:
        require(isinstance(branches, dict) and set(branches) == {"aLunch", "bLunch"}, f"{path}.lunchBranches", "must contain exactly aLunch and bLunch", issues)
        if isinstance(branches, dict):
            for branch_name in ("aLunch", "bLunch"):
                branch = branches.get(branch_name)
                require(isinstance(branch, list), f"{path}.lunchBranches.{branch_name}", "must be an array", issues)
                if isinstance(branch, list):
                    validate_timeline(shared + branch, f"{path}.{branch_name}EffectiveTimeline", issues)

    if day_type.get("isStudentDay") is False:
        require(not shared, f"{path}.sharedEvents", "must be empty for a no-student day", issues)
        require(branches is None, f"{path}.lunchBranches", "must be absent for a no-student day", issues)
        require(school_hours is None, f"{path}.schoolHours", "must be absent for a no-student day", issues)
    elif day_type.get("isStudentDay") is True:
        require(school_hours is not None, f"{path}.schoolHours", "is required for a student day", issues)


def validate(configuration: Any) -> list[str]:
    issues: list[str] = []
    require(isinstance(configuration, dict), "$", "must be a JSON object", issues)
    if not isinstance(configuration, dict):
        return issues
    require(set(configuration) == TOP_LEVEL_KEYS, "$", f"must contain exactly {sorted(TOP_LEVEL_KEYS)}", issues)
    require(configuration.get("schemaVersion") == 1, "schemaVersion", "must equal 1", issues)
    require(
        isinstance(configuration.get("configurationVersion"), str) and bool(configuration.get("configurationVersion", "").strip()),
        "configurationVersion",
        "must not be empty",
        issues,
    )
    updated_at = configuration.get("updatedAt")
    try:
        dt.datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        issues.append("updatedAt: must be an ISO 8601 timestamp")
    time_zone = configuration.get("timeZoneIdentifier")
    try:
        ZoneInfo(time_zone)
    except (TypeError, ZoneInfoNotFoundError):
        issues.append("timeZoneIdentifier: must be a recognized IANA time zone")
    require(isinstance(configuration.get("bellOffsetSeconds"), int) and not isinstance(configuration.get("bellOffsetSeconds"), bool), "bellOffsetSeconds", "must be an integer", issues)

    metadata = configuration.get("metadata")
    require(isinstance(metadata, dict) and set(metadata) == {"status", "notes"}, "metadata", "must contain exactly status and notes", issues)
    if isinstance(metadata, dict):
        require(isinstance(metadata.get("status"), str) and bool(metadata.get("status", "").strip()), "metadata.status", "must not be empty", issues)
        require(isinstance(metadata.get("notes"), str), "metadata.notes", "must be a string", issues)

    day_types = configuration.get("dayTypes")
    require(isinstance(day_types, list), "dayTypes", "must be an array", issues)
    if not isinstance(day_types, list):
        day_types = []
    identifiers: set[str] = set()
    for index, day_type in enumerate(day_types):
        validate_day_type(day_type, index, issues)
        if isinstance(day_type, dict) and isinstance(day_type.get("id"), str):
            identifier = day_type["id"]
            require(identifier not in identifiers, f"dayTypes[{index}].id", "must be unique", issues)
            identifiers.add(identifier)

    assignments = configuration.get("dateAssignments")
    require(isinstance(assignments, list), "dateAssignments", "must be an array", issues)
    seen_dates: set[str] = set()
    if isinstance(assignments, list):
        for index, assignment in enumerate(assignments):
            path = f"dateAssignments[{index}]"
            require(isinstance(assignment, dict) and set(assignment) == {"date", "dayType"}, path, "must contain exactly date and dayType", issues)
            if not isinstance(assignment, dict):
                continue
            date_value = assignment.get("date")
            try:
                dt.date.fromisoformat(date_value)
            except (TypeError, ValueError):
                issues.append(f"{path}.date: must be an ISO date")
            if isinstance(date_value, str):
                require(date_value not in seen_dates, f"{path}.date", "must be unique", issues)
                seen_dates.add(date_value)
            require(assignment.get("dayType") in identifiers, f"{path}.dayType", "must reference an existing day type", issues)
    return issues


def main() -> int:
    paths = [Path(argument) for argument in sys.argv[1:]] or [Path("schedule.json")]
    failed = False
    for path in paths:
        try:
            configuration = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"{path}: {error}", file=sys.stderr)
            failed = True
            continue
        issues = validate(configuration)
        if issues:
            failed = True
            print(f"{path}: invalid", file=sys.stderr)
            for issue in issues:
                print(f"  - {issue}", file=sys.stderr)
        else:
            print(f"{path}: valid")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())


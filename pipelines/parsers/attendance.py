"""
Pipeline 6: Time & Attendance
Extracts: emp_id, name, branch, date, day_of_week, punch_in, punch_out,
          duration_hours, shift_type, is_anomalous, is_valid_shift,
          shift_start_hour, weekend_flag

NOTE — Anomalous shifts are flagged, NOT deleted. Exclude from primary
       staffing model but keep in audit table.
       Thresholds are configurable via TOO_SHORT / TOO_LONG constants.
       Staffing analysis should be rules-based / pattern-based / archetype-based
       (no daily sales data for precise shift-demand modeling).
"""

import re
from datetime import datetime
import pandas as pd
from .utils import (
    read_lines, parse_csv_line,
    is_noise, is_total_line,
)

SIGNATURE = "time & attendance"

_EMP_RE = re.compile(r"EMP ID\s*:\s*([\d.]+)")
_NAME_RE = re.compile(r"NAME\s*:\s*(Person_\d+)")
_DATE_RE = re.compile(r"(\d{2}-\w{3}-\d{2})")
_TIME_RE = re.compile(r"(\d{2}\.\d{2}\.\d{2})")

# Configurable shift thresholds
TOO_SHORT_THRESHOLD = 2.0   # hours
TOO_LONG_THRESHOLD = 14.0   # hours


def can_parse(lines: list[str]) -> bool:
    return SIGNATURE in " ".join(lines[:5]).lower()


def _dur(s: str) -> float:
    """Parse HH.MM.SS → decimal hours."""
    p = s.split(".")
    return int(p[0]) + int(p[1]) / 60 + int(p[2]) / 3600 if len(p) == 3 else 0.0


def parse(filepath: str) -> pd.DataFrame:
    lines = read_lines(filepath)
    records = []
    emp_id = name = branch = None

    # Collect known branch names dynamically: standalone label lines that
    # appear right after an EMP ID line
    # First pass: find branch names
    branch_names = set()
    prev_was_emp = False
    for line in lines:
        raw = line.strip()
        if _EMP_RE.search(raw):
            prev_was_emp = True
            continue
        if prev_was_emp:
            cells = parse_csv_line(raw)
            # Branch line: ",<BranchName>,,,,"
            for c in cells:
                if c and not _DATE_RE.match(c) and not _TIME_RE.match(c) and not c.replace(".", "").isdigit():
                    branch_names.add(c)
                    break
            prev_was_emp = False

    for line in lines:
        raw = line.strip()
        if is_noise(raw):
            continue
        if is_total_line(raw):
            continue
        if "time & attendance" in raw.lower() or "punch in" in raw.lower() or "from date:" in raw.lower():
            continue

        # Employee header
        emp_m = _EMP_RE.search(raw)
        name_m = _NAME_RE.search(raw)
        if emp_m and name_m:
            emp_id = emp_m.group(1).replace(".0", "")
            name = name_m.group(1)
            continue

        # Branch line
        cells = parse_csv_line(raw)
        for c in cells:
            if c in branch_names:
                branch = c
                break

        # Data row: has date(s) and time(s)
        dates = _DATE_RE.findall(raw)
        times = _TIME_RE.findall(raw)

        if not dates or not times or not emp_id:
            continue

        punch_in_time = times[0]
        punch_out_time = times[1] if len(times) > 1 else None
        duration = _dur(times[2]) if len(times) >= 3 else (
            _dur(times[1]) if len(times) == 2 and len(dates) == 1 else None
        )

        # Parse date
        try:
            dt = datetime.strptime(dates[0], "%d-%b-%y")
            date_str = dt.strftime("%Y-%m-%d")
        except ValueError:
            date_str = dates[0]

        # Shift type from punch-in hour
        hour = int(punch_in_time.split(".")[0])
        shift_type = "morning" if hour < 12 else ("afternoon" if hour < 17 else "evening")

        # Anomaly flagging
        is_anom = False
        if duration is not None:
            is_anom = duration < TOO_SHORT_THRESHOLD or duration > TOO_LONG_THRESHOLD

        records.append({
            "emp_id": emp_id,
            "name": name,
            "branch": branch,
            "date": date_str,
            "punch_in": punch_in_time.replace(".", ":"),
            "punch_out": punch_out_time.replace(".", ":") if punch_out_time else None,
            "duration_hours": round(duration, 2) if duration is not None else None,
            "shift_type": shift_type,
            "is_anomalous": is_anom,
            "is_valid_shift": not is_anom and duration is not None,
            "shift_start_hour": hour,
        })

    df = pd.DataFrame(records)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["day_of_week"] = df["date"].dt.day_name()
        df["weekend_flag"] = df["day_of_week"].isin(["Saturday", "Sunday"])
        df = df.sort_values(["branch", "date", "emp_id"]).reset_index(drop=True)
    return df

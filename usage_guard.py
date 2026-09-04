#!/usr/bin/env python3
"""Usage guard — rolling-window token governor for autonomous Claude Code operation.

WHY: native auto-pause-at-90% does not exist in Claude Code (open feature request).
During autonomous /loop work this guard prevents getting truncated mid-task: it sums
tokens used in the trailing WINDOW_HOURS from ~/.claude/projects JSONL (per-MESSAGE
timestamps, not per-session) and compares to a calibratable BUDGET.

MODES:
  --print  : human/JSON status (default). Use to CALIBRATE the budget.
  --hook   : PreToolUse hook mode. Exit 2 (block) + stderr message when >= threshold,
             so autonomous-me is forced to stop and wait for the window to roll.

CALIBRATION (honest note): the windowed TOKEN COUNT is accurate; what's unknown is
how many tokens = 100% of the window (Anthropic doesn't publish it, varies by plan).
Set USAGE_BUDGET_TOKENS env (or budget.txt next to this file) once you observe your
own limit. Until calibrated, --hook will NOT block (fails open, never false-stops).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
BUDGET_FILE = Path(__file__).parent / "budget.txt"

WINDOW_HOURS = float(os.environ.get("USAGE_WINDOW_HOURS", "5"))
THRESHOLD_PCT = float(os.environ.get("USAGE_THRESHOLD_PCT", "90"))


def get_budget() -> int | None:
    env = os.environ.get("USAGE_BUDGET_TOKENS")
    if env and env.isdigit():
        return int(env)
    if BUDGET_FILE.exists():
        txt = BUDGET_FILE.read_text().strip()
        if txt.isdigit():
            return int(txt)
    return None  # uncalibrated → fail open


def windowed_usage(window_h: float) -> tuple[int, datetime | None]:
    """Sum input+cache+output tokens from assistant messages whose own timestamp is
    within the trailing window. Returns (tokens, oldest_in_window_ts)."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_h)
    total = 0
    oldest: datetime | None = None
    if not PROJECTS_DIR.exists():
        return 0, None
    for jsonl in PROJECTS_DIR.glob("*/*.jsonl"):
        try:
            # skip files untouched in the window (fast path)
            if datetime.fromtimestamp(jsonl.stat().st_mtime, timezone.utc) < cutoff:
                continue
        except OSError:
            continue
        try:
            with open(jsonl, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line or '"assistant"' not in line:
                        continue
                    try:
                        o = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if o.get("type") != "assistant":
                        continue
                    ts_str = o.get("timestamp")
                    if not ts_str:
                        continue
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                    if ts < cutoff:
                        continue
                    usage = (o.get("message") or {}).get("usage")
                    if not isinstance(usage, dict):
                        continue
                    total += (
                        usage.get("input_tokens", 0)
                        + usage.get("cache_creation_input_tokens", 0)
                        + usage.get("cache_read_input_tokens", 0)
                        + usage.get("output_tokens", 0)
                    )
                    if oldest is None or ts < oldest:
                        oldest = ts
        except OSError:
            continue
    return total, oldest


def status() -> dict:
    tokens, oldest = windowed_usage(WINDOW_HOURS)
    budget = get_budget()
    pct = round(tokens / budget * 100, 1) if budget else None
    # window rolls when the oldest in-window message ages out
    reset_at = (oldest + timedelta(hours=WINDOW_HOURS)).isoformat() if oldest else None
    return {
        "window_hours": WINDOW_HOURS,
        "window_tokens": tokens,
        "budget_tokens": budget,
        "pct": pct,
        "threshold_pct": THRESHOLD_PCT,
        "over_threshold": bool(budget and pct is not None and pct >= THRESHOLD_PCT),
        "window_resets_at": reset_at,
        "calibrated": budget is not None,
    }


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--print"
    st = status()
    if mode == "--hook":
        if st["over_threshold"]:
            sys.stderr.write(
                f"‼️ USAGE GUARD: ~{st['pct']}% of {WINDOW_HOURS}h window "
                f"({st['window_tokens']:,} tok) — PAUSE autonomous work. "
                f"Window rolls ~{st['window_resets_at']}. "
                f"Stop now and ScheduleWakeup past reset.\n"
            )
            return 2  # block the tool call
        return 0
    # --print
    print(json.dumps(st, indent=2))
    if not st["calibrated"]:
        print(
            "\n⚠️ UNCALIBRATED: set USAGE_BUDGET_TOKENS env or write budget.txt "
            "(one integer = tokens that = 100% of the window). Until then --hook "
            "fails open (never blocks).",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

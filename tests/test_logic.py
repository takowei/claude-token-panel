"""Tests for pure-logic functions in main.py and usage_guard.py.

All tests are offline: no filesystem reads from ~/.claude, no network.
FastAPI endpoints are tested via TestClient with load_all_sessions mocked.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TAIPEI_TZ = timezone(timedelta(hours=8))


def _make_jsonl(*entries: dict[str, Any]) -> str:
    """Serialise a sequence of dicts as newline-delimited JSON."""
    return "\n".join(json.dumps(e) for e in entries) + "\n"


# ---------------------------------------------------------------------------
# slug_to_project_name
# ---------------------------------------------------------------------------


def test_slug_workspace_prefix():
    from main import slug_to_project_name

    assert slug_to_project_name("-home-tako-workspace-foo") == "foo"


def test_slug_workspace_root():
    """Slug that is exactly the workspace prefix → 'workspace'."""
    from main import slug_to_project_name

    assert slug_to_project_name("-home-tako-workspace-") == "workspace"


def test_slug_home_prefix():
    from main import slug_to_project_name

    assert slug_to_project_name("-home-tako-bar") == "bar"


def test_slug_fallback_strips_leading_dash():
    from main import slug_to_project_name

    assert slug_to_project_name("-other-project") == "other-project"


def test_slug_no_known_prefix():
    from main import slug_to_project_name

    assert slug_to_project_name("someproject") == "someproject"


# ---------------------------------------------------------------------------
# cwd_to_project_name
# ---------------------------------------------------------------------------


def test_cwd_none_returns_none():
    from main import cwd_to_project_name

    assert cwd_to_project_name(None) is None


def test_cwd_empty_returns_none():
    from main import cwd_to_project_name

    assert cwd_to_project_name("") is None


def test_cwd_normal_path():
    from main import cwd_to_project_name

    assert cwd_to_project_name("/home/tako/workspace/myproject") == "myproject"


def test_cwd_trailing_slash():
    from main import cwd_to_project_name

    assert cwd_to_project_name("/home/tako/workspace/myproject/") == "myproject"


def test_cwd_single_component():
    from main import cwd_to_project_name

    assert cwd_to_project_name("/root") == "root"


# ---------------------------------------------------------------------------
# color_for_total
# ---------------------------------------------------------------------------


def test_color_green_below_threshold():
    from main import color_for_total

    assert color_for_total(0) == "green"
    assert color_for_total(9_999) == "green"


def test_color_yellow_at_green_threshold():
    from main import color_for_total

    assert color_for_total(10_000) == "yellow"
    assert color_for_total(49_999) == "yellow"


def test_color_red_at_yellow_threshold():
    from main import color_for_total

    assert color_for_total(50_000) == "red"
    assert color_for_total(1_000_000) == "red"


# ---------------------------------------------------------------------------
# get_week_start
# ---------------------------------------------------------------------------


def test_get_week_start_returns_utc():
    from main import get_week_start

    ws = get_week_start()
    assert ws.tzinfo is not None
    assert ws.tzinfo == timezone.utc


def test_get_week_start_is_monday_11h_taipei():
    from main import get_week_start

    ws = get_week_start()
    ws_taipei = ws.astimezone(TAIPEI_TZ)
    assert ws_taipei.weekday() == 0, "week start must be Monday"
    assert ws_taipei.hour == 11
    assert ws_taipei.minute == 0
    assert ws_taipei.second == 0


def test_get_week_start_not_in_future():
    from main import get_week_start

    ws = get_week_start()
    assert ws <= datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# parse_session — synthetic JSONL fixtures
# ---------------------------------------------------------------------------


def _session_jsonl_with_usage(
    ts: str = "2026-06-20T10:00:00Z",
    cwd: str = "/home/tako/workspace/myproject",
    input_tokens: int = 1000,
    cache_creation: int = 200,
    cache_read: int = 50,
    output_tokens: int = 500,
) -> str:
    user_msg = {"type": "user", "timestamp": ts, "cwd": cwd}
    assistant_msg = {
        "type": "assistant",
        "timestamp": ts,
        "message": {
            "usage": {
                "input_tokens": input_tokens,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": cache_read,
                "output_tokens": output_tokens,
            }
        },
    }
    return _make_jsonl(user_msg, assistant_msg)


def test_parse_session_aggregates_tokens(tmp_path: Path):
    from main import parse_session

    content = _session_jsonl_with_usage(
        input_tokens=1000,
        cache_creation=200,
        cache_read=50,
        output_tokens=500,
    )
    f = tmp_path / "abc123.jsonl"
    f.write_text(content, encoding="utf-8")

    result = parse_session(f, "-home-tako-workspace-myproject")

    assert result is not None
    assert result["input_tokens"] == 1250  # 1000 + 200 + 50
    assert result["output_tokens"] == 500
    assert result["total_tokens"] == 1750
    assert result["session_id"] == "abc123"


def test_parse_session_extracts_project_from_cwd(tmp_path: Path):
    from main import parse_session

    content = _session_jsonl_with_usage(cwd="/home/tako/workspace/sale-tracker")
    f = tmp_path / "sess.jsonl"
    f.write_text(content, encoding="utf-8")

    result = parse_session(f, "-home-tako-workspace-sale-tracker")

    assert result is not None
    assert result["project"] == "sale-tracker"


def test_parse_session_falls_back_to_slug_when_no_cwd(tmp_path: Path):
    from main import parse_session

    assistant_msg = {
        "type": "assistant",
        "timestamp": "2026-06-20T10:00:00Z",
        "message": {
            "usage": {
                "input_tokens": 100,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "output_tokens": 50,
            }
        },
    }
    f = tmp_path / "sess2.jsonl"
    f.write_text(_make_jsonl(assistant_msg), encoding="utf-8")

    result = parse_session(f, "-home-tako-workspace-chain-sec")
    assert result is not None
    assert result["project"] == "chain-sec"


def test_parse_session_skips_zero_token_files(tmp_path: Path):
    from main import parse_session

    user_msg = {"type": "user", "timestamp": "2026-06-20T10:00:00Z"}
    f = tmp_path / "empty.jsonl"
    f.write_text(_make_jsonl(user_msg), encoding="utf-8")

    assert parse_session(f, "slug") is None


def test_parse_session_handles_malformed_json_lines(tmp_path: Path):
    from main import parse_session

    lines = [
        '{"type": "user", "cwd": "/home/tako/workspace/p", "timestamp": "2026-06-20T10:00:00Z"}',
        "NOT VALID JSON {{{",
        '{"type": "assistant", "message": {"usage": {"input_tokens": 10, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 5}}}',
    ]
    f = tmp_path / "mixed.jsonl"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = parse_session(f, "slug")
    assert result is not None
    assert result["input_tokens"] == 10
    assert result["output_tokens"] == 5


def test_parse_session_color_assignment(tmp_path: Path):
    from main import parse_session

    content = _session_jsonl_with_usage(
        input_tokens=100, cache_creation=0, cache_read=0, output_tokens=50
    )
    f = tmp_path / "s.jsonl"
    f.write_text(content, encoding="utf-8")

    result = parse_session(f, "slug")
    assert result is not None
    assert result["color"] == "green"  # 150 total < 10k


def test_parse_session_missing_file_returns_none():
    from main import parse_session

    result = parse_session(Path("/nonexistent/path/session.jsonl"), "slug")
    assert result is None


# ---------------------------------------------------------------------------
# FastAPI smoke tests — TestClient with mocked load_all_sessions
# ---------------------------------------------------------------------------


def test_api_sessions_returns_structure():
    """GET /api/sessions returns required top-level keys."""
    import main as m
    from fastapi.testclient import TestClient

    fake_sessions = [
        {
            "session_id": "abc",
            "project": "myproj",
            "timestamp": "2026-06-20T02:00:00+00:00",
            "input_tokens": 500,
            "output_tokens": 100,
            "total_tokens": 600,
            "color": "green",
        }
    ]
    with patch.object(m, "load_all_sessions", return_value=fake_sessions):
        client = TestClient(m.app)
        resp = client.get("/api/sessions")

    assert resp.status_code == 200
    body = resp.json()
    assert "sessions" in body
    assert "week_total" in body
    assert "week_limit" in body
    assert "week_pct" in body
    assert "week_start" in body


def test_api_sessions_week_total_counts_recent():
    """Sessions within the current week are counted in week_total."""
    import main as m
    from fastapi.testclient import TestClient

    # Use a timestamp well within the current week
    recent_ts = datetime.now(timezone.utc) - timedelta(hours=1)
    fake_sessions = [
        {
            "session_id": "x",
            "project": "p",
            "timestamp": recent_ts.isoformat(),
            "input_tokens": 1000,
            "output_tokens": 500,
            "total_tokens": 1500,
            "color": "green",
        }
    ]
    with patch.object(m, "load_all_sessions", return_value=fake_sessions):
        client = TestClient(m.app)
        resp = client.get("/api/sessions")

    body = resp.json()
    assert body["week_total"]["total"] == 1500


def test_api_sessions_empty():
    """GET /api/sessions works when there are no sessions at all."""
    import main as m
    from fastapi.testclient import TestClient

    with patch.object(m, "load_all_sessions", return_value=[]):
        client = TestClient(m.app)
        resp = client.get("/api/sessions")

    assert resp.status_code == 200
    body = resp.json()
    assert body["sessions"] == []
    assert body["week_total"]["total"] == 0


# ---------------------------------------------------------------------------
# usage_guard — status / threshold logic
# ---------------------------------------------------------------------------


def _make_usage_guard_env(**overrides: str) -> dict[str, str]:
    base = {
        "USAGE_WINDOW_HOURS": "5",
        "USAGE_THRESHOLD_PCT": "90",
    }
    base.update(overrides)
    return base


def test_usage_guard_status_uncalibrated(tmp_path: Path):
    """When no budget is set, status shows calibrated=False and pct=None."""
    import usage_guard

    env = _make_usage_guard_env()
    env.pop("USAGE_BUDGET_TOKENS", None)  # ensure absent

    with (
        patch.dict(os.environ, env, clear=False),
        patch.object(usage_guard, "windowed_usage", return_value=(5000, None)),
        patch.object(usage_guard, "BUDGET_FILE", tmp_path / "no_budget.txt"),
    ):
        # Remove USAGE_BUDGET_TOKENS from env explicitly
        env_clean = {k: v for k, v in os.environ.items() if k != "USAGE_BUDGET_TOKENS"}
        with patch.dict(os.environ, env_clean, clear=True):
            st = usage_guard.status()

    assert st["calibrated"] is False
    assert st["pct"] is None
    assert st["over_threshold"] is False


def test_usage_guard_status_calibrated_under_threshold(tmp_path: Path):
    """With budget set and usage below threshold, over_threshold is False."""
    import usage_guard

    budget_file = tmp_path / "budget.txt"
    budget_file.write_text("100000")

    with (
        patch.object(usage_guard, "BUDGET_FILE", budget_file),
        patch.object(usage_guard, "windowed_usage", return_value=(50000, None)),
        patch.dict(
            os.environ,
            {"USAGE_WINDOW_HOURS": "5", "USAGE_THRESHOLD_PCT": "90"},
            clear=False,
        ),
    ):
        env_clean = {k: v for k, v in os.environ.items() if k != "USAGE_BUDGET_TOKENS"}
        with patch.dict(os.environ, env_clean, clear=True):
            st = usage_guard.status()

    assert st["calibrated"] is True
    assert st["pct"] == 50.0
    assert st["over_threshold"] is False


def test_usage_guard_status_over_threshold(tmp_path: Path):
    """When usage >= threshold_pct, over_threshold is True."""
    import usage_guard

    budget_file = tmp_path / "budget.txt"
    budget_file.write_text("100000")

    with (
        patch.object(usage_guard, "BUDGET_FILE", budget_file),
        patch.object(usage_guard, "windowed_usage", return_value=(90000, None)),
        patch.dict(
            os.environ,
            {"USAGE_WINDOW_HOURS": "5", "USAGE_THRESHOLD_PCT": "90"},
            clear=False,
        ),
    ):
        env_clean = {k: v for k, v in os.environ.items() if k != "USAGE_BUDGET_TOKENS"}
        with patch.dict(os.environ, env_clean, clear=True):
            st = usage_guard.status()

    assert st["over_threshold"] is True
    assert st["pct"] == 90.0


def test_usage_guard_budget_from_env(tmp_path: Path):
    """USAGE_BUDGET_TOKENS env var takes precedence over budget.txt."""
    import usage_guard

    budget_file = tmp_path / "budget.txt"
    budget_file.write_text("999999")  # should be ignored

    env = {
        "USAGE_BUDGET_TOKENS": "200000",
        "USAGE_WINDOW_HOURS": "5",
        "USAGE_THRESHOLD_PCT": "90",
    }
    with (
        patch.object(usage_guard, "BUDGET_FILE", budget_file),
        patch.dict(os.environ, env, clear=True),
    ):
        budget = usage_guard.get_budget()

    assert budget == 200000


def test_usage_guard_reset_at_populated_when_oldest_set(tmp_path: Path):
    """window_resets_at is set when there is an oldest-in-window timestamp."""
    import usage_guard

    budget_file = tmp_path / "budget.txt"
    budget_file.write_text("100000")

    oldest = datetime(2026, 6, 20, 10, 0, 0, tzinfo=timezone.utc)
    with (
        patch.object(usage_guard, "BUDGET_FILE", budget_file),
        patch.object(usage_guard, "windowed_usage", return_value=(10000, oldest)),
        patch.dict(
            os.environ,
            {
                "USAGE_BUDGET_TOKENS": "100000",
                "USAGE_WINDOW_HOURS": "5",
                "USAGE_THRESHOLD_PCT": "90",
            },
            clear=True,
        ),
    ):
        st = usage_guard.status()

    assert st["window_resets_at"] is not None
    expected_reset = oldest + timedelta(hours=5)
    assert st["window_resets_at"] == expected_reset.isoformat()

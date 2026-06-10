"""Claude Token Panel - FastAPI backend serving token usage from ~/.claude/projects."""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Claude Token Panel")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

PROJECTS_DIR = Path.home() / ".claude" / "projects"
TAIPEI_TZ = timezone(timedelta(hours=8))

GREEN_THRESHOLD = 10_000
YELLOW_THRESHOLD = 50_000

WEEK_LIMIT = 26_052_993  # anchored at current week total (100%)


def get_week_start() -> datetime:
    """Return the most recent Monday 11:00 Asia/Taipei as a UTC datetime."""
    now_taipei = datetime.now(TAIPEI_TZ)
    days_since_monday = now_taipei.weekday()  # 0 = Monday
    last_monday = now_taipei - timedelta(days=days_since_monday)
    week_start_taipei = last_monday.replace(hour=11, minute=0, second=0, microsecond=0)
    if week_start_taipei > now_taipei:
        week_start_taipei -= timedelta(days=7)
    return week_start_taipei.astimezone(timezone.utc)


def slug_to_project_name(slug: str) -> str:
    """Convert project slug like -home-tako-workspace-foo to foo."""
    prefix = "-home-tako-workspace-"
    if slug.startswith(prefix):
        return slug[len(prefix) :] or "workspace"
    prefix2 = "-home-tako-"
    if slug.startswith(prefix2):
        return slug[len(prefix2) :]
    return slug.lstrip("-")


def cwd_to_project_name(cwd: Optional[str]) -> Optional[str]:
    """Derive project name from cwd path."""
    if not cwd:
        return None
    parts = cwd.rstrip("/").split("/")
    if parts:
        return parts[-1] or "root"
    return None


def color_for_total(total: int) -> str:
    if total < GREEN_THRESHOLD:
        return "green"
    if total < YELLOW_THRESHOLD:
        return "yellow"
    return "red"


def parse_session(filepath: Path, project_slug: str) -> Optional[dict]:
    """Parse a single JSONL session file and return aggregated session data."""
    input_tokens = 0
    output_tokens = 0
    timestamp: Optional[datetime] = None
    project_name: Optional[str] = None

    try:
        with open(filepath, encoding="utf-8") as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    obj = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                msg_type = obj.get("type")

                # Collect timestamp from the first message that has one
                if timestamp is None:
                    ts_str = obj.get("timestamp")
                    if ts_str:
                        try:
                            timestamp = datetime.fromisoformat(
                                ts_str.replace("Z", "+00:00")
                            )
                        except ValueError:
                            pass

                # Collect project name from user message cwd
                if project_name is None and msg_type == "user":
                    cwd = obj.get("cwd")
                    project_name = cwd_to_project_name(cwd)

                # Accumulate token usage from assistant messages
                if msg_type == "assistant":
                    message = obj.get("message")
                    if not isinstance(message, dict):
                        continue
                    usage = message.get("usage")
                    if not isinstance(usage, dict):
                        continue
                    input_tokens += (
                        usage.get("input_tokens", 0)
                        + usage.get("cache_creation_input_tokens", 0)
                        + usage.get("cache_read_input_tokens", 0)
                    )
                    output_tokens += usage.get("output_tokens", 0)

    except OSError:
        return None

    # Skip sessions with no token data at all
    if input_tokens == 0 and output_tokens == 0:
        return None

    if project_name is None:
        project_name = slug_to_project_name(project_slug)

    total = input_tokens + output_tokens
    session_id = filepath.stem  # filename without .jsonl

    return {
        "session_id": session_id,
        "project": project_name,
        "timestamp": timestamp.isoformat() if timestamp else None,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total,
        "color": color_for_total(total),
    }


def load_all_sessions() -> list[dict]:
    """Scan all project directories and return parsed session list."""
    sessions = []
    if not PROJECTS_DIR.exists():
        return sessions

    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        slug = project_dir.name
        for jsonl_file in project_dir.glob("*.jsonl"):
            result = parse_session(jsonl_file, slug)
            if result is not None:
                sessions.append(result)

    return sessions


@app.get("/")
async def serve_index():
    index_path = Path(__file__).parent / "index.html"
    return FileResponse(str(index_path), media_type="text/html")


@app.get("/api/sessions")
async def get_sessions():
    week_start_utc = get_week_start()
    all_sessions = load_all_sessions()

    # Sort by timestamp descending (newest first); sessions without timestamp go last
    def sort_key(s):
        ts = s.get("timestamp")
        if ts is None:
            return ""
        return ts

    all_sessions.sort(key=sort_key, reverse=True)

    # Calculate week totals
    week_input = 0
    week_output = 0
    for s in all_sessions:
        ts_str = s.get("timestamp")
        if ts_str is None:
            continue
        try:
            ts = datetime.fromisoformat(ts_str)
        except ValueError:
            continue
        if ts >= week_start_utc:
            week_input += s["input_tokens"]
            week_output += s["output_tokens"]

    week_total = week_input + week_output
    week_pct = round(week_total / WEEK_LIMIT * 100, 1) if WEEK_LIMIT else 0

    return JSONResponse(
        content={
            "week_total": {
                "input": week_input,
                "output": week_output,
                "total": week_total,
            },
            "week_limit": WEEK_LIMIT,
            "week_pct": week_pct,
            "week_start": week_start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sessions": all_sessions,
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8765)

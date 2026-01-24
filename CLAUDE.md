# CLAUDE.md

Chrome network request logger for reverse-engineering APIs.

## Architecture

- **Daemon** (`scripts/daemon.py`): Background CDP capture, writes to JSONL
- **CLI** (`scripts/chrome-log.py`): Query interface for Claude and humans
- **Server** (`scripts/server.py`): Status page at localhost:9223
- **Skill** (`SKILL.md`): Claude usage patterns

## Development

```bash
cd ~/Repos/skill-chrome-log
uv sync                          # Install dependencies
uv run python scripts/daemon.py  # Test daemon directly
uv run python scripts/chrome-log.py status  # Test CLI
```

## Key Paths

| Path | Purpose |
|------|---------|
| `~/.chrome-debug/logs/requests.jsonl` | Captured requests (append-only) |
| `~/.chrome-debug/logs/.paused` | Pause flag (exists = paused) |
| `~/.chrome-debug/logs/daemon.log` | Daemon output |
| `~/.chrome-debug/.daemon.pid` | PID file |

## CDP Domains Used

- `Network`: Request/response capture
- `Target`: Multi-tab management (attachedToTarget)

## Log Format

Each line in `requests.jsonl`:
```json
{
  "id": "requestId",
  "ts": "2026-01-24T09:30:00Z",
  "tab": {"id": "targetId", "url": "https://..."},
  "method": "POST",
  "url": "https://api.example.com/v1/data",
  "status": 200,
  "mime": "application/json",
  "size": 1234,
  "requestHeaders": {...},
  "responseHeaders": {...},
  "requestBody": "...",
  "responseBody": "..."
}
```

## Filtering Rules

- Skip binary: `image/*`, `font/*`, `application/octet-stream`
- Skip tracking: `google-analytics`, `doubleclick`, `play.google.com/log`
- Truncate bodies > 100KB

## Testing

1. Start Chrome Debug: `chrome-debug`
2. Start daemon: `chrome-log start`
3. Browse sites, generate traffic
4. Query: `chrome-log tail -n 10`
5. Check status page: `open http://localhost:9223`

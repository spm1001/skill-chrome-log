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

- `Network`: Request/response capture (including ExtraInfo events for cookies)
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
  "cookies": [{"name": "...", "value": "..."}],
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

## Design Decisions

**Status server stays running when Chrome quits:** The daemon exits when Chrome disconnects (cleaner lifecycle), but the status server stays up. This enables the pinned status tab to auto-reconnect when Chrome Debug restarts. Trade-off: slightly "bad manners" vs better UX for the common case.

**Hue-shifted icon:** Chrome Debug uses a 180° hue-shifted Chrome icon (cyan/magenta instead of red/green/blue) for visual distinction. Not purple, not inverted - specifically hue rotation via ImageMagick `-modulate 100,100,50`.

**Chrome Debug is not a default browser:** The Info.plist deliberately omits URL handlers (`CFBundleURLTypes`). Chrome Debug is a developer tool you launch explicitly via `chrome-debug` or `browse URL`, not a browser for daily use. Making it a default browser candidate would mean every clicked link opens with debug capture running.

## Related: webctl Fork

webctl integration requires our fork at `~/Repos/webctl` which adds CDP endpoint support.

Install with: `uv tool install ~/Repos/webctl --force`

Config at: `~/Library/Application Support/webctl/config.json`
```json
{"cdp_endpoint": "http://localhost:9222"}
```

See `references/WEBCTL_INTEGRATION.md` for full workflow.

## Troubleshooting

**Orphaned launchd plists:** If you previously used an older version, you may have orphaned `com.modha.chrome-log.plist` in `~/Library/LaunchAgents/`. The current version uses `local.chrome-log.plist`. Safe to delete the old one:
```bash
launchctl unload ~/Library/LaunchAgents/com.modha.chrome-log.plist 2>/dev/null
rm -f ~/Library/LaunchAgents/com.modha.chrome-log.plist
```
